# T3 — Pi 4B Edition

A **Raspberry Pi 4B** voice assistant forked from
[mayukh4/pibot_local_agent](https://github.com/mayukh4/pibot_local_agent).

> Wake word → local 4 B LLM → cloud fallback for complex questions

All the original features (wake word "Hey Jansky", animated face UI, Piper TTS,
Whisper.cpp STT) are preserved. This fork adjusts defaults, documentation, and
the install script for **Raspberry Pi 4B + Raspberry Pi OS Bookworm 64-bit**.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        RASPBERRY PI 4B                           │
│                                                                  │
│  ┌──────────┐    "Hey Jansky"     ┌──────────────────────────┐  │
│  │ USB Mic  │ ──────────────────► │  Wake Word Detector      │  │
│  │ (48kHz)  │                     │  (openWakeWord + ONNX)   │  │
│  └──────────┘                     └───────────┬──────────────┘  │
│                                               │ wake!           │
│                                               ▼                 │
│                                   ┌──────────────────────────┐  │
│                                   │  Audio Manager           │  │
│                                   │  Record → Silence detect │  │
│                                   └───────────┬──────────────┘  │
│                                               │ raw audio       │
│                                               ▼                 │
│                                   ┌──────────────────────────┐  │
│                                   │  Whisper.cpp (STT)       │  │
│                                   │  48kHz → 16kHz → text    │  │
│                                   │  4 threads (all cores)   │  │
│                                   └───────────┬──────────────┘  │
│                                               │ text            │
│                                               ▼                 │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                    LLM Router (Ollama)                       ││
│  │               qwen2.5:4b  · 4 threads · ctx 2048            ││
│  │                                                              ││
│  │  Simple chat ──► respond directly        (local)            ││
│  │  Time/Date   ──► time_tool               (local)            ││
│  │  Weather     ──► weather_tool            (OpenWeatherMap)   ││
│  │  News        ──► news_tool               (NewsAPI)          ││
│  │  System      ──► system_tool             (CPU/RAM/uptime)   ││
│  │  Jokes       ──► joke_tool               (free API)         ││
│  │  Complex     ──► cloud_handoff ──────►   Kimi K2 / cloud    ││
│  └───────────────────────────────┬──────────────────────────────┘│
│                                  │ response text                 │
│                                  ▼                               │
│                      ┌──────────────────────┐                    │
│                      │  Piper TTS           │                    │
│                      │  text → speech (.wav)│                    │
│                      └──────────┬───────────┘                    │
│                                 │                                │
│              ┌──────────────────┴──────────────┐                 │
│              ▼                                 ▼                 │
│     ┌──────────────┐                  ┌────────────────┐         │
│     │  USB Speaker │                  │  PyGame Face   │         │
│     │  (ALSA)      │                  │  (800×480 LCD) │         │
│     └──────────────┘                  └────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
```

---

## Hardware Requirements

| Component | Requirement |
|-----------|-------------|
| **Board** | Raspberry Pi 4B (4 GB RAM) |
| **OS** | Raspberry Pi OS Bookworm 64-bit (`aarch64`) |
| **Storage** | 32 GB+ microSD |
| **Microphone** | USB microphone |
| **Speaker** | USB speaker |
| **Display** | 800×480 HDMI/DSI LCD *(optional — runs headless too)* |

> **Why 4 GB RAM?**  `qwen2.5:4b` quantised to Q4_K_M is ~2.5 GB on disk and
> uses roughly 2.8 GB at runtime. The 4 GB Pi 4B leaves ~1 GB for the OS and
> audio pipeline.

---

## Features

| Feature | How it works | API key needed? |
|---------|--------------|-----------------|
| **Wake word** — "Hey Jansky" | Custom openWakeWord ONNX model | No |
| **Local chat** — greetings, Q&A | qwen2.5:4b via Ollama | No |
| **Time & date** | Python `datetime` | No |
| **System status** — CPU temp, RAM, uptime | Reads `/proc` and `/sys` | No |
| **Jokes** | Official Joke API (free) | No |
| **Weather** | OpenWeatherMap | `OPENWEATHER_API_KEY` |
| **News headlines** | NewsAPI | `NEWSAPI_KEY` |
| **Cloud AI answers** — complex / creative | Kimi K2 (Moonshot) | `MOONSHOT_API_KEY` |
| **Animated face UI** | PyGame on Wayland/framebuffer | No |
| **Natural speech** | Piper TTS (British English) | No |
| **Speech recognition** | Whisper.cpp quantised base.en | No |

---

## Quick Start (One-Command Install)

> **Prerequisite:** A fresh **Raspberry Pi OS Bookworm 64-bit** install with
> internet access.

### 1 — Clone this repo

```bash
git clone https://github.com/YashRelekar/Tee3.git ~/T3
cd ~/T3
```

### 2 — Run the installer

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh` automatically:
- Installs system packages via `apt`
- Creates a Python virtual environment (`venv/`)
- Installs Python dependencies
- Installs Ollama and pulls `qwen2.5:4b` (~2.5 GB download)
- Builds Whisper.cpp with 4 threads (all Pi 4B cores)
- Downloads the Piper TTS voice
- Patches `config/config.json` with the correct install path

Expected install time: **20–30 minutes** on a Pi 4B with a decent connection.

### 3 — Add API keys (optional)

```bash
cp .env.example .env
nano .env   # fill in any keys you want
```

| Variable | What it unlocks |
|----------|-----------------|
| `OPENWEATHER_API_KEY` | Live weather — [openweathermap.org/api](https://openweathermap.org/api) |
| `NEWSAPI_KEY` | News headlines — [newsapi.org](https://newsapi.org) |
| `MOONSHOT_API_KEY` | Cloud AI fallback — [platform.moonshot.ai](https://platform.moonshot.ai) |

### 4 — Run T3

```bash
source venv/bin/activate
python orchestrator.py
```

Say **"Hey Jansky"** and start talking.

---

## Configuration

All runtime settings live in `config/config.json`.

### Pi 4B defaults

| Setting | Default | Description |
|---------|---------|-------------|
| `chat_model` | `qwen2.5:4b` | Ollama model — change to any supported model |
| `ollama_num_thread` | `4` | CPU threads (Pi 4B has 4 Cortex-A72 cores) |
| `ollama_num_ctx` | `2048` | Context window (tokens); keep ≤ 2048 on Pi 4B |
| `ollama_num_predict` | `256` | Max output tokens per response |
| `ollama_num_batch` | `128` | Prompt evaluation batch size |
| `whisper_threads` | `4` | Threads for Whisper.cpp STT |
| `wake_word_threshold` | `0.5` | Wake word confidence (0–1) |
| `mic_sample_rate` | `48000` | Native USB mic sample rate |
| `display_width` / `height` | `800` / `480` | UI resolution |
| `enable_ui` | `true` | Set `false` for headless mode |
| `cloud_fallback_enabled` | `true` | Requires `MOONSHOT_API_KEY` in `.env` |

### Changing the local model

Edit `config/config.json`:

```json
{
  "chat_model": "phi3:mini"
}
```

Or set an environment variable before running:

```bash
CHAT_MODEL=phi3:mini python orchestrator.py
```

**Recommended models for Pi 4B (4 GB RAM)**

| Model | Size (Q4) | Quality | Notes |
|-------|-----------|---------|-------|
| `qwen2.5:4b` *(default)* | ~2.5 GB | ★★★★ | Good tool-calling, fits comfortably |
| `phi3:mini` | ~2.3 GB | ★★★ | Faster, slightly less capable |
| `qwen2.5:1.5b` | ~1.0 GB | ★★ | Smallest option, weakest reasoning |

---

## Cloud Fallback

The local model automatically routes **complex queries** to cloud AI via the
`cloud_handoff` tool. This triggers for:

- Creative writing or storytelling
- Complex reasoning / multi-step problems
- Coding questions
- Deep knowledge or nuanced explanations

**To enable cloud fallback:**

1. Get a free/paid key at [platform.moonshot.ai](https://platform.moonshot.ai/)
2. Add it to `.env`:
   ```
   MOONSHOT_API_KEY=sk-xxxxxxxxxxxxxxxx
   ```
3. Restart T3 — cloud handoff is now live.

**Without the key**, T3 responds with *"Sorry, cloud AI is not configured."*
All other features (local chat, tools, wake word) continue to work normally.

---

## Project Structure

```
T3/
├── orchestrator.py              # Main entry point
├── config.py                    # Config dataclass, loads .env + config.json
├── setup.sh                     # One-command installer for Pi 4B
├── .env.example                 # API key template
│
├── audio/
│   ├── audio_manager.py         # Mic recording + speaker playback
│   ├── tts_engine.py            # Piper TTS wrapper
│   └── stt_engine.py            # Whisper.cpp wrapper
│
├── brain/
│   ├── router.py                # Intent routing
│   ├── ollama_client.py         # Ollama HTTP client (Pi 4B options)
│   ├── cloud_client.py          # Kimi K2 / Moonshot HTTP client
│   ├── tool_definitions.py      # Tool schemas + system prompt
│   └── tools/
│       ├── time_tool.py
│       ├── weather_tool.py
│       ├── news_tool.py
│       ├── system_tool.py
│       └── joke_tool.py
│
├── senses/
│   └── wake_word_detector.py    # openWakeWord listener
│
├── ui/
│   └── ui_manager.py            # PyGame animated face
│
├── config/
│   ├── config.json              # Runtime config (Pi 4B defaults)
│   ├── local_soul.md            # Local LLM personality
│   └── cloud_soul.md            # Cloud LLM personality
│
├── assets/
│   ├── face/                    # Face expression PNGs
│   └── fillers/                 # Pre-generated filler audio
│
├── models/
│   └── wake_word/
│       └── Hey_Jansky.onnx      # Wake word model (download separately)
│
├── piper/voices/                # Piper TTS voices (downloaded by setup.sh)
├── whisper.cpp/                 # Whisper.cpp source + binary + model
└── tests/
    ├── test_router.py
    ├── test_wake_word.py
    └── test_audio_pipeline.py
```

---

## Manual Installation

Use this if you prefer step-by-step over `setup.sh`.

### 1 — System packages

```bash
sudo apt update && sudo apt install -y \
  python3 python3-venv python3-dev python3-pip \
  build-essential cmake git curl wget \
  libsdl2-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  portaudio19-dev libasound2-dev \
  alsa-utils
```

### 2 — Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### 3 — Python dependencies

```bash
pip install httpx sounddevice numpy piper-tts openwakeword onnxruntime pygame
```

### 4 — Ollama + qwen2.5:4b

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:4b
```

### 5 — Whisper.cpp (4 threads)

```bash
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
cmake -B build
cmake --build build --config Release -j4
sudo cp build/bin/whisper-cli /usr/local/bin/whisper-cpp

bash models/download-ggml-model.sh base.en
./build/bin/quantize models/ggml-base.en.bin models/ggml-base.en-q5_0.bin q5_0
cd ..
```

### 6 — Piper TTS voice

```bash
mkdir -p piper/voices
wget -O piper/voices/en_GB-semaine-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx
wget -O piper/voices/en_GB-semaine-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json
```

### 7 — API keys

```bash
cp .env.example .env
nano .env
```

### 8 — Run

```bash
source venv/bin/activate
python orchestrator.py
```

---

## Testing Individual Components

```bash
source venv/bin/activate

# Test the LLM router (requires Ollama running)
python tests/test_router.py

# Test wake word detection
python tests/test_wake_word.py

# Test full audio pipeline (mic → STT → TTS → speaker)
python tests/test_audio_pipeline.py
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Mic 'USB PnP Sound Device' not found` | Run `arecord -l`, update `MIC_NAME` in `audio/audio_manager.py` and `senses/wake_word_detector.py` |
| `Speaker 'UACDemoV1.0' not found` | Run `aplay -l`, update `SPEAKER_NAME` in `audio/audio_manager.py` |
| Whisper not found | Run `which whisper-cpp`; update `whisper_path` in `config/config.json` |
| Ollama not running | Run `ollama serve` in another terminal, then `ollama pull qwen2.5:4b` |
| **Out of memory / OOM kill** | Reduce `ollama_num_ctx` to `1024` in `config/config.json` |
| **Slow first response** | Normal — model loads into RAM on first query (~30 s). Faster after |
| No display / PyGame crash | Set `"enable_ui": false` in `config/config.json` to run headless |
| Weather / News unavailable | Add the matching API key to `.env` |
| Cloud AI says "not configured" | Add `MOONSHOT_API_KEY` to `.env` |

---

## Upstream

This project is a Pi 4B edition of
[mayukh4/pibot_local_agent](https://github.com/mayukh4/pibot_local_agent)
(MIT licence). All original functionality is preserved; only defaults, paths,
and documentation have been adjusted for Pi 4B hardware.

---

## Licence

MIT
