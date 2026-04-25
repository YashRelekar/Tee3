"""
Wake word detection using openWakeWord.
"""

import numpy as np
import sounddevice as sd
from queue import Queue, Empty
from typing import Callable, Optional
from threading import Thread, Event
from pathlib import Path

try:
    from openwakeword.model import Model
    import openwakeword
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False


MIC_NAME = "USB PnP Sound Device"


def _find_mic_device() -> int:
    """Find the USB mic device index by name."""
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if MIC_NAME.lower() in d["name"].lower() and d["max_input_channels"] > 0:
            return i
    raise RuntimeError(
        "Mic '{}' not found. Available: {}".format(
            MIC_NAME, [(i, d["name"]) for i, d in enumerate(devices)]
        )
    )


def _find_bundled_model(name: str) -> str:
    """Find a bundled openWakeWord model by name."""
    pkg_dir = Path(openwakeword.__file__).parent / "resources" / "models"
    for f in pkg_dir.glob("{}*.onnx".format(name)):
        return str(f)
    raise FileNotFoundError("Bundled model {} not found in {}".format(name, pkg_dir))


class WakeWordDetector:
    """Detects wake word using openWakeWord."""

    def __init__(
        self,
        model_path: str = "",
        threshold: float = 0.5,
        sample_rate: int = 16000,
        mic_sample_rate: int = 48000,
        inference_framework: str = "onnx",
        gain_target_peak: float = 0.9
    ):
        if not OPENWAKEWORD_AVAILABLE:
            raise RuntimeError("openwakeword not installed. Run: pip install openwakeword")

        self.threshold = threshold
        self.sample_rate = sample_rate
        self.mic_sample_rate = 48000
        self.gain_target_peak = gain_target_peak
        self.mic_chunk_size = 3840  # 1280 * 3 (80ms at 48kHz -> 16kHz)

        # Resolve mic device by name (survives USB re-enumeration)
        self.mic_device = _find_mic_device()
        print("    Wake word mic: device {} ({})".format(self.mic_device, MIC_NAME))

        # Use custom model if provided, otherwise fall back to built-in hey_jarvis
        use_custom = (
            model_path
            and Path(model_path).exists()
        )

        if use_custom:
            self.model = Model(wakeword_model_paths=[model_path])
        else:
            jarvis_path = _find_bundled_model("hey_jarvis")
            self.model = Model(wakeword_model_paths=[jarvis_path])

        self._running = False
        self._stop_event = Event()
        self._resume_event = Event()
        self._thread: Optional[Thread] = None
        self._callback: Optional[Callable] = None
        self._paused = False
        self._audio_queue: Queue = Queue()
        self._gain = 4.0

    def start(self, callback: Callable[[], None]):
        """Start listening for wake word."""
        self._callback = callback
        self._running = True
        self._paused = False
        self._stop_event.clear()
        self._resume_event.set()

        self._thread = Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop listening."""
        self._running = False
        self._stop_event.set()
        self._resume_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def pause(self):
        """Pause detection and release the mic stream."""
        self._paused = True
        self._resume_event.clear()

    def resume(self):
        """Resume detection (reopens mic stream)."""
        self._paused = False
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except Empty:
                break
        self._resume_event.set()

    def _normalize(self, audio: np.ndarray) -> np.ndarray:
        """Apply adaptive gain normalization for weak USB mics."""
        peak = np.max(np.abs(audio))
        if peak < 50:
            return audio.astype(np.int16)
        target = self.gain_target_peak * 32767
        desired_gain = target / peak
        # Cap gain to avoid clipping distortion on speech
        desired_gain = min(desired_gain, 15.0)
        self._gain = 0.3 * desired_gain + 0.7 * self._gain
        self._gain = min(self._gain, 15.0)
        gained = np.clip(audio * self._gain, -32768, 32767)
        return gained.astype(np.int16)

    def _listen_loop(self):
        """Main listening loop - reopens stream after each pause/resume cycle."""
        while self._running:
            self._resume_event.wait()
            if not self._running:
                break

            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except Empty:
                    break

            def audio_callback(indata, frames, time_info, status):
                self._audio_queue.put(bytes(indata))

            try:
                stream = sd.RawInputStream(
                    device=self.mic_device,
                    samplerate=self.mic_sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.mic_chunk_size,
                    latency="high",
                    callback=audio_callback
                )
                stream.start()
            except Exception as e:
                print("Wake word stream error: {}".format(e))
                if self._running:
                    self._stop_event.wait(timeout=1.0)
                continue

            detected = False
            while self._running and not self._paused:
                try:
                    raw = self._audio_queue.get(timeout=0.1)
                except Empty:
                    continue

                audio = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
                normalized = self._normalize(audio)
                decimated = normalized[::3]

                predictions = self.model.predict(decimated)

                for model_name, score in predictions.items():
                    if score >= self.threshold:
                        print("Wake word detected! ({}, score: {:.3f})".format(
                            model_name, score))
                        detected = True
                        break

                if detected:
                    break

            # Close stream BEFORE callback to free USB mic for recording
            stream.stop()
            stream.close()

            if detected and self._callback:
                self._paused = True
                self._resume_event.clear()
                self.model.reset()
                self._callback()
