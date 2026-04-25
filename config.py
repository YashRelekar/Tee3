"""
Configuration management for T3 — Pi 4B edition.

Pi 4B-specific defaults:
  - chat_model: qwen2.5:4b  (~2.5 GB on disk, fits in 4 GB RAM)
  - ollama_num_thread: 4    (Pi 4B has 4 ARM Cortex-A72 cores)
  - ollama_num_ctx: 2048    (conservative context window to keep RAM free)
  - ollama_num_predict: 256 (short responses for latency)
  - ollama_num_batch: 128   (small batch to reduce peak memory)
  - whisper_threads: 4      (all 4 cores for STT)
  - cloud_fallback_enabled: True  (Kimi/Moonshot for complex queries)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json


@dataclass
class Config:
    """Application configuration."""

    # Paths — default to ~/T3; override via config.json or PROJECT_ROOT env var
    project_root: str = field(
        default_factory=lambda: os.getenv(
            "PROJECT_ROOT",
            str(Path.home() / "T3")
        )
    )

    # Audio - Piper TTS (using piper-tts Python package)
    piper_voice: str = ""

    # Whisper.cpp
    whisper_path: str = "/usr/local/bin/whisper-cpp"
    whisper_model: str = ""

    # Pi 4B: use a ~4 GB class model (qwen2.5:4b ≈ 2.5 GB quantised)
    # Change via config.json "chat_model" or env var CHAT_MODEL
    chat_model: str = "qwen2.5:4b"

    # Wake word
    wake_word_model: str = ""
    wake_word_threshold: float = 0.5

    # Microphone settings
    mic_sample_rate: int = 48000
    target_sample_rate: int = 16000

    # Local location default
    local_location: str = "London, UK"

    # API Keys (loaded from environment)
    openweather_api_key: str = ""
    moonshot_api_key: str = ""
    newsapi_key: str = ""

    # Soul/personality files
    local_soul_path: str = ""
    cloud_soul_path: str = ""

    # Display
    assets_path: str = ""
    display_width: int = 800
    display_height: int = 480
    use_framebuffer: bool = True

    # Features
    enable_streaming_tts: bool = False
    enable_ui: bool = True

    # ── Pi 4B performance tuning ───────────────────────────────────────────
    # These are passed to Ollama at inference time to keep RAM usage bounded.
    ollama_num_thread: int = 4    # Pi 4B has 4 cores
    ollama_num_ctx: int = 2048    # Context window (tokens); 4096 risks OOM
    ollama_num_predict: int = 256  # Max output tokens per response
    ollama_num_batch: int = 128   # Prompt eval batch size

    # Whisper threads (4 = all Pi 4B cores)
    whisper_threads: int = 4

    # Cloud fallback — set MOONSHOT_API_KEY in .env to enable
    cloud_fallback_enabled: bool = True

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """Load configuration from file and environment variables.

        Resolution order (highest wins):
          1. Environment variables
          2. config/config.json
          3. Dataclass defaults
        """
        config = cls()
        root = config.project_root

        # Resolve path defaults relative to project_root (can be overridden below)
        config.assets_path = os.path.join(root, "assets", "face")
        config.piper_voice = os.path.join(root, "piper", "voices",
                                           "en_GB-semaine-medium.onnx")
        config.whisper_model = os.path.join(root, "whisper.cpp", "models",
                                             "ggml-base.en-q5_0.bin")
        config.wake_word_model = os.path.join(root, "models", "wake_word",
                                               "Hey_Jansky.onnx")
        config.local_soul_path = os.path.join(root, "config", "local_soul.md")
        config.cloud_soul_path = os.path.join(root, "config", "cloud_soul.md")

        # Load from JSON file if it exists (overrides dataclass defaults)
        if config_path is None:
            config_path = os.path.join(root, "config", "config.json")

        if Path(config_path).exists():
            with open(config_path) as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(config, key):
                        setattr(config, key, value)

        # Load from .env file if present
        env_path = os.path.join(config.project_root, ".env")
        if Path(env_path).exists():
            config._load_env_file(env_path)

        # Override with environment variables (highest priority)
        config.chat_model = os.getenv("CHAT_MODEL", config.chat_model)
        config.openweather_api_key = os.getenv(
            "OPENWEATHER_API_KEY",
            config.openweather_api_key
        )
        config.moonshot_api_key = os.getenv(
            "MOONSHOT_API_KEY",
            config.moonshot_api_key
        )
        config.newsapi_key = os.getenv(
            "NEWSAPI_KEY",
            config.newsapi_key
        )

        # cloud_fallback_enabled is implicitly true when moonshot_api_key is set
        if config.moonshot_api_key:
            config.cloud_fallback_enabled = True

        return config

    def _load_env_file(self, path: str):
        """Load environment variables from .env file."""
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

    def save(self, config_path: Optional[str] = None):
        """Save configuration to file (API keys are never written)."""
        if config_path is None:
            config_path = os.path.join(self.project_root, "config", "config.json")

        Path(config_path).parent.mkdir(parents=True, exist_ok=True)

        # Exclude API keys and internal attributes
        skip = {"openweather_api_key", "moonshot_api_key", "newsapi_key"}
        data = {
            k: v for k, v in self.__dict__.items()
            if k not in skip and not k.startswith("_")
        }

        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
