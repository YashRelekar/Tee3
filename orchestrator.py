#!/usr/bin/env python3
"""
Main orchestrator - ties all components together.
"""

import sys
import os
import signal
import time
import random
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import Config
from audio.audio_manager import AudioManager
from audio.tts_engine import PiperTTS
from audio.stt_engine import WhisperSTT
from brain.ollama_client import OllamaClient
from brain.router import Router, ToolType
from brain.tools.time_tool import get_current_time
from brain.tools.weather_tool import WeatherTool
from brain.tools.news_tool import NewsTool
from brain.tools.system_tool import get_system_status
from brain.tools.joke_tool import get_joke
from brain.cloud_client import KimiClient
from senses.wake_word_detector import WakeWordDetector

# Pre-generated filler WAVs in assets/fillers/
FILLER_WAVS = {
    "On it!": "assets/fillers/filler_0.wav",
    "Thinking...": "assets/fillers/filler_1.wav",
    "Give me a sec.": "assets/fillers/filler_2.wav",
    "Let me check.": "assets/fillers/filler_3.wav",
    "Working on it.": "assets/fillers/filler_4.wav",
}


class Orchestrator:
    """Main system orchestrator."""

    def __init__(self, config: Config):
        self.config = config
        self._running = False
        self.ui = None

        # Initialize components
        print("Initializing T3 (Pi 4B Edition)...")

        # Audio
        print("  - Audio manager")
        self.audio = AudioManager(
            sample_rate=config.target_sample_rate,
            mic_sample_rate=config.mic_sample_rate,
            mic_name=config.mic_name
        )

        print("  - TTS engine")
        self.tts = PiperTTS(model_path=config.piper_voice)

        print("  - STT engine")
        self.stt = WhisperSTT(
            whisper_path=config.whisper_path,
            model_path=config.whisper_model,
            threads=config.whisper_threads
        )

        # Brain
        print("  - Ollama client")
        self.ollama = OllamaClient(
            model=config.chat_model,
            num_thread=config.ollama_num_thread,
            num_ctx=config.ollama_num_ctx,
            num_predict=config.ollama_num_predict,
            num_batch=config.ollama_num_batch,
        )

        print("  - Router")
        self.router = Router(self.ollama)

        # Tools (optional, may fail if API keys not set)
        self.weather = None
        self.cloud = None
        self.news = None

        if config.openweather_api_key:
            print("  - Weather tool")
            try:
                self.weather = WeatherTool(api_key=config.openweather_api_key)
            except Exception as e:
                print(f"    Warning: Weather tool unavailable: {e}")

        if config.newsapi_key:
            print("  - News tool")
            try:
                self.news = NewsTool(api_key=config.newsapi_key)
            except Exception as e:
                print(f"    Warning: News tool unavailable: {e}")

        if config.moonshot_api_key:
            print("  - Cloud client")
            try:
                self.cloud = KimiClient(
                    api_key=config.moonshot_api_key,
                    soul_path=config.cloud_soul_path
                )
            except Exception as e:
                print(f"    Warning: Cloud client unavailable: {e}")

        print("  - System status tool")
        print("  - Joke tool")

        # Senses
        if config.disable_audio:
            print("  - Wake word detector: DISABLED (DISABLE_AUDIO is set)")
            self.wake_word = None
        else:
            print("  - Wake word detector")
            self.wake_word = WakeWordDetector(
                model_path=config.wake_word_model,
                threshold=config.wake_word_threshold,
                mic_sample_rate=config.mic_sample_rate,
                mic_name=config.mic_name
            )

        # UI (optional)
        if config.enable_ui:
            try:
                from ui.ui_manager import UIManager, UIState
                print("  - UI manager")
                self.ui = UIManager(
                    width=config.display_width,
                    height=config.display_height,
                    assets_path=config.assets_path,
                    use_framebuffer=config.use_framebuffer
                )
                self.UIState = UIState
            except Exception as e:
                print(f"    Warning: UI unavailable: {e}")
                # Clean up pygame if it was partially initialized
                try:
                    import pygame
                    pygame.quit()
                except:
                    pass
                self.ui = None

        # Load pre-generated filler WAVs
        self._filler_wavs = {}
        fillers_dir = os.path.join(config.project_root, "assets", "fillers")
        for phrase, rel_path in FILLER_WAVS.items():
            abs_path = os.path.join(config.project_root, rel_path)
            if os.path.exists(abs_path):
                self._filler_wavs[phrase] = abs_path
            else:
                print(f"    Warning: Filler WAV missing: {rel_path}")
        if self._filler_wavs:
            print(f"  - Loaded {len(self._filler_wavs)} filler phrases")

        print("Initialization complete!")

    def start(self):
        """Start the assistant."""
        self._running = True

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start UI if available
        if self.ui:
            self.ui.start()
            self.ui.set_state(self.UIState.IDLE)

        # Speak startup message BEFORE starting wake word detection
        # (otherwise the speaker saying "Hey Jarvis" triggers the detector)
        self._speak("Hello! I'm Jansky. Say hey Jansky to get my attention.")

        # Start wake word detection after greeting finishes
        if self.wake_word:
            self.wake_word.start(callback=self._on_wake_word)
            print("T3 is running. Say 'Hey Jansky' to activate.")
        else:
            print("T3 is running (audio input disabled — wake word inactive).")
        print("Press Ctrl+C to exit.")

        # Main loop
        while self._running:
            time.sleep(0.1)

        self._cleanup()
        # Force exit to kill any lingering daemon threads (e.g. sounddevice streams)
        os._exit(0)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\nShutting down...")
        self._running = False

    def _cleanup(self):
        """Clean up resources."""
        if self.wake_word:
            self.wake_word.stop()
        if self.ui:
            self.ui.stop()

    def _on_wake_word(self):
        """Called when wake word is detected."""
        if not self._running:
            return

        print("Wake word detected!")

        # Clear conversation history — each wake word is a fresh interaction
        self.router.clear_history()

        # Pause wake word detection
        self.wake_word.pause()

        # Update UI
        if self.ui:
            self.ui.set_state(self.UIState.LISTENING)

        # Record user speech
        print("Listening...")
        audio = self.audio.record_until_silence(
            silence_duration=1.5,
            max_duration=15.0
        )

        if audio is None or len(audio) == 0:
            print("No speech detected")
            if self.ui:
                self.ui.set_state(self.UIState.IDLE)
            self.wake_word.resume()
            return

        # Update UI
        if self.ui:
            self.ui.set_state(self.UIState.THINKING)

        # Transcribe
        print("Transcribing...")
        try:
            text = self.stt.transcribe_audio_array(audio)
            print(f"User said: {text}")
        except Exception as e:
            print(f"Transcription error: {e}")
            self._speak("Sorry, I didn't catch that.")
            if self.ui:
                self.ui.set_state(self.UIState.IDLE)
            self.wake_word.resume()
            return

        if not text.strip():
            self._speak("I didn't hear anything.")
            if self.ui:
                self.ui.set_state(self.UIState.IDLE)
            self.wake_word.resume()
            return

        # Speak a random filler phrase before processing (skip for custom actions)
        text_lower = text.lower()
        if "on camera" not in text_lower:
            self._speak_filler()

        # Route and respond
        try:
            self._process_query(text)
        except Exception as e:
            print(f"Processing error: {e}")
            self._speak("Sorry, something went wrong.")
            if self.ui:
                self.ui.set_state(self.UIState.ERROR)
            time.sleep(1)

        # Return to idle
        if self.ui:
            self.ui.set_state(self.UIState.IDLE)
        self.wake_word.resume()

    def _speak_filler(self):
        """Play a random pre-generated filler phrase."""
        if not self._filler_wavs:
            return
        phrase = random.choice(list(self._filler_wavs.keys()))
        wav_path = self._filler_wavs[phrase]
        print(f"Filler: {phrase}")
        try:
            self.audio.play_wav(wav_path)
        except Exception as e:
            print(f"Filler playback error: {e}")

    def _process_query(self, text: str):
        """Process user query through router."""
        # Custom action: "on camera" introduction
        if "on camera" in text.lower():
            print("[custom] on camera introduction")
            self._speak(
                "Hey all, I am Jansky, Mayukh's personal AI assistant "
                "running 24 7 on the desk helping with all his daily chores! "
                "Its great to meet you all"
            )
            return

        result = self.router.route(text)

        if result.tool == ToolType.NONE:
            print("[local ollama] Direct chat response")
            self._speak(result.response)

        elif result.tool == ToolType.TIME:
            print("[tool] get_current_time")
            response = get_current_time()
            self._speak(response)

        elif result.tool == ToolType.WEATHER:
            if self.weather:
                location = result.arguments.get("location") or self.config.local_location
                print(f"[tool] get_weather → {location}")
                response = self.weather.get_weather(location)
                self._speak(response)
            else:
                self._speak("Sorry, weather lookup is not configured.")

        elif result.tool == ToolType.NEWS:
            if self.news:
                category = result.arguments.get("category", "")
                print(f"[tool] get_news → {category or 'general'}")
                response = self.news.get_news(category)
                self._speak(response)
            else:
                self._speak("Sorry, news lookup is not configured.")

        elif result.tool == ToolType.SYSTEM_STATUS:
            print("[tool] get_system_status")
            response = get_system_status()
            self._speak(response)

        elif result.tool == ToolType.JOKE:
            print("[tool] get_joke")
            response = get_joke()
            self._speak(response)

        elif result.tool == ToolType.CLOUD:
            print("[cloud kimi-k2.5] Handing off to cloud AI")
            query = result.arguments.get("query", text)
            self._handle_cloud_query(query)

    def _handle_cloud_query(self, query: str):
        """Handle cloud API query."""
        if not self.cloud:
            self._speak("Sorry, cloud AI is not configured.")
            return

        try:
            # Non-streaming for simplicity
            response = self.cloud.chat(query, stream=False)
            self._speak(response)
        except Exception as e:
            print(f"Cloud error: {e}")
            self._speak("Sorry, I couldn't reach the cloud AI.")

    def _speak(self, text: str):
        """Speak text through TTS."""
        if not text:
            return

        print(f"Speaking: {text}")
        if self.ui:
            self.ui.set_state(self.UIState.SPEAKING)

        try:
            audio_path = self.tts.synthesize(text)
            self.audio.play_wav(audio_path)
        except Exception as e:
            print(f"TTS error: {e}")

        if self.ui:
            self.ui.set_state(self.UIState.IDLE)


def main():
    """Main entry point."""
    config = Config.load()
    orchestrator = Orchestrator(config)
    orchestrator.start()


if __name__ == "__main__":
    main()
