"""
Audio Manager - Handles microphone input and speaker output with muting.
"""

import re
import sounddevice as sd
import numpy as np
import wave
import subprocess
from threading import Lock
from typing import Optional
import os


def _find_device_by_name(name_substring: str, kind: str) -> int:
    """Find a sounddevice device index by name substring.

    Args:
        name_substring: Partial device name to match (e.g. "USB PnP Sound Device")
        kind: "input" or "output"

    Returns:
        Device index, or raises RuntimeError if not found.
    """
    devices = sd.query_devices()
    channel_key = "max_input_channels" if kind == "input" else "max_output_channels"
    for i, d in enumerate(devices):
        if name_substring.lower() in d["name"].lower() and d[channel_key] > 0:
            return i
    raise RuntimeError(
        "Audio device matching '{}' ({}) not found. Available: {}".format(
            name_substring, kind,
            [(i, d["name"]) for i, d in enumerate(devices)]
        )
    )


def _find_alsa_card_by_name(name_substring: str) -> str:
    """Find ALSA card number by name, returns 'plughw:N,0' string."""
    try:
        result = subprocess.run(
            ["aplay", "-l"], capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            if line.startswith("card ") and name_substring in line:
                card_num = line.split(":")[0].replace("card ", "").strip()
                return "plughw:{},0".format(card_num)
    except Exception:
        pass
    return "plughw:0,0"


# Name fragments used when auto-detecting ReSpeaker / XVF3800 / seeed mic arrays
_RESPEAKER_HINTS = ["respeaker", "xvf3800", "seeed", "2mic", "4mic", "6mic"]

# Device name substring for the speaker (unchanged)
SPEAKER_NAME = "UACDemoV1.0"


def _resolve_mic_device(preferred_name: str = "") -> int:
    """Resolve the microphone device index using a priority chain.

    Priority order (first match wins):
      1. ``MIC_NAME`` or ``AUDIO_INPUT_DEVICE`` environment variable
      2. *preferred_name* argument (e.g. ``mic_name`` from config.json)
      3. Auto-detect: any device containing a ReSpeaker / XVF3800 / seeed hint
      4. Auto-detect: legacy "USB PnP Sound Device" (backward-compat)
      5. Auto-detect: any USB input device

    Raises:
        RuntimeError: with a helpful message listing available devices and
            guidance on how to configure the mic when no device is found.
    """
    # 1. Environment variable override
    env_name = os.getenv("MIC_NAME") or os.getenv("AUDIO_INPUT_DEVICE")
    if env_name:
        return _find_device_by_name(env_name, "input")

    # 2. Caller-supplied preferred name (from config)
    if preferred_name:
        return _find_device_by_name(preferred_name, "input")

    devices = sd.query_devices()
    input_devices = [
        (i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0
    ]

    if not input_devices:
        raise RuntimeError(
            "No audio input devices found.\n"
            "  - Plug in a USB microphone (e.g. ReSpeaker XVF3800) and retry.\n"
            "  - Run 'arecord -l' to list ALSA capture devices.\n"
            "  - Set MIC_NAME=<device name> in your environment or config.\n"
            "  - Or set DISABLE_AUDIO=1 to start without microphone input."
        )

    # 3. Auto-detect ReSpeaker / XVF3800 / seeed mic arrays
    for i, d in input_devices:
        if any(h in d["name"].lower() for h in _RESPEAKER_HINTS):
            print("    Auto-detected mic: device {} ({})".format(i, d["name"]))
            return i

    # 4. Backward compat: original USB PnP Sound Device
    for i, d in input_devices:
        if "usb pnp" in d["name"].lower():
            return i

    # 5. Any USB input device
    for i, d in input_devices:
        if "usb" in d["name"].lower():
            print("    Auto-detected USB mic: device {} ({})".format(i, d["name"]))
            return i

    # No suitable device found — provide actionable guidance
    names = [(i, d["name"]) for i, d in input_devices]
    raise RuntimeError(
        "No suitable microphone found.\n"
        "  Available input devices: {}\n"
        "  Set MIC_NAME=<device name> or AUDIO_INPUT_DEVICE=<device name> in your\n"
        "  environment or config/config.json (key: \"mic_name\").\n"
        "  Run 'arecord -l' for ALSA names or:\n"
        "    python3 -c \"import sounddevice as sd; [print(i, d['name']) "
        "for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]\"\n"
        "  Or set DISABLE_AUDIO=1 to start without microphone input.".format(names)
    )


class AudioManager:
    """Manages microphone input and speaker output with muting."""

    def __init__(
        self,
        sample_rate: int = 16000,
        mic_sample_rate: int = 48000,
        channels: int = 1,
        dtype: str = 'int16',
        mic_name: str = ""
    ):
        self.sample_rate = sample_rate
        self.mic_sample_rate = mic_sample_rate
        self.channels = channels
        self.dtype = dtype
        self.is_muted = False
        self._mute_lock = Lock()
        self._recording = False
        self._audio_buffer = []

        # Resolve device indices at init time
        disable_audio = os.getenv("DISABLE_AUDIO", "").lower() in ("1", "true", "yes")
        if disable_audio:
            self.mic_device = None
            print("    Mic: DISABLED (DISABLE_AUDIO is set)")
        else:
            self.mic_device = _resolve_mic_device(mic_name)
            mic_label = sd.query_devices()[self.mic_device]["name"]
            print("    Mic: device {} ({})".format(self.mic_device, mic_label))

        self.speaker_alsa = _find_alsa_card_by_name(SPEAKER_NAME)
        print("    Speaker: {} ({})".format(self.speaker_alsa, SPEAKER_NAME))

    def mute(self):
        """Mute microphone input (during TTS playback)."""
        with self._mute_lock:
            self.is_muted = True

    def unmute(self):
        """Unmute microphone input."""
        with self._mute_lock:
            self.is_muted = False

    def _normalize(self, audio: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
        """Apply gain normalization for weak USB mics."""
        peak = np.max(np.abs(audio.astype(np.float64)))
        if peak < 50:
            return audio
        gain = (target_peak * 32767) / peak
        return np.clip(audio.astype(np.float64) * gain, -32768, 32767).astype(np.int16)

    def record_until_silence(
        self,
        silence_threshold: float = 0.01,
        silence_duration: float = 1.5,
        max_duration: float = 30.0
    ) -> Optional[np.ndarray]:
        """
        Record audio until silence is detected.
        Records at mic_sample_rate (48kHz), then decimates to target sample_rate (16kHz).
        """
        if self.is_muted or self.mic_device is None:
            return None

        self._audio_buffer = []
        self._recording = True
        silence_samples = 0
        silence_samples_needed = int(silence_duration * self.mic_sample_rate / 4096)
        max_samples = int(max_duration * self.mic_sample_rate / 4096)
        total_samples = 0

        def callback(indata, frames, time, status):
            if status:
                pass  # Ignore non-fatal overflow on USB mic
            if self.is_muted or not self._recording:
                return
            self._audio_buffer.append(indata.copy())

        stream = sd.InputStream(
            device=self.mic_device,
            samplerate=self.mic_sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=4096,
            latency="high",
            callback=callback
        )
        stream.start()

        try:
            while self._recording and total_samples < max_samples:
                sd.sleep(100)
                total_samples += 1

                if len(self._audio_buffer) > 0:
                    recent = self._audio_buffer[-1]
                    rms = np.sqrt(np.mean(recent.astype(np.float32) ** 2)) / 32768
                    if rms < silence_threshold:
                        silence_samples += 1
                        if silence_samples >= silence_samples_needed:
                            break
                    else:
                        silence_samples = 0
        finally:
            stream.stop()
            stream.close()

        self._recording = False

        if len(self._audio_buffer) == 0:
            return None

        raw_audio = np.concatenate(self._audio_buffer, axis=0).flatten()
        normalized = self._normalize(raw_audio)
        # Decimate from 48kHz to 16kHz (exact factor of 3)
        decimated = normalized[::3]
        return decimated

    def save_to_wav(self, audio: np.ndarray, filepath: str):
        """Save audio array to WAV file."""
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio.tobytes())

    def play_wav(self, filepath: str):
        """Play a WAV file through speakers."""
        self.mute()
        try:
            subprocess.run(
                ["aplay", "-D", self.speaker_alsa, filepath],
                check=True,
                capture_output=True
            )
        except FileNotFoundError:
            import wave as wav_mod
            with wav_mod.open(filepath, 'rb') as wf:
                audio_data = np.frombuffer(
                    wf.readframes(wf.getnframes()),
                    dtype=np.int16
                )
                sd.play(audio_data, wf.getframerate())
                sd.wait()
        except Exception as e:
            print("Playback error: {}".format(e))
        finally:
            self.unmute()

    def play_audio(self, audio: np.ndarray):
        """Play audio array through speakers."""
        self.mute()
        try:
            sd.play(audio, self.sample_rate)
            sd.wait()
        finally:
            self.unmute()
