# Product Requirements Document: Project "Pi-Genius" (Codename: Jansky)

**Version:** 2.0 (Research-Validated)  
**Last Updated:** February 2025  
**Target Platform:** Raspberry Pi 5 (8GB RAM)  
**Document Purpose:** Complete implementation guide for AI coding agents

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Hardware Specifications](#2-hardware-specifications)
3. [System Architecture](#3-system-architecture)
4. [Technical Stack (Validated)](#4-technical-stack-validated)
5. [Memory Budget](#5-memory-budget)
6. [Implementation Phases](#6-implementation-phases)
7. [File Structure](#7-file-structure)
8. [Configuration Files](#8-configuration-files)
9. [API Contracts](#9-api-contracts)
10. [Testing Criteria](#10-testing-criteria)
11. [Known Risks & Mitigations](#11-known-risks--mitigations)

---

## 1. Executive Summary

### 1.1 Goal
Create a modular, local-first voice AI assistant running on Raspberry Pi 5 (8GB) with voice interaction and cloud fallback for complex queries.

### 1.2 Core Philosophy
**"Local Speed, Cloud Power"** - The system defaults to fast local processing. It seamlessly hands off to Cloud API for complex reasoning, injecting personality context only when necessary.

### 1.3 User Experience
- Animated "Face" on 800x480 DSI display reacting to system states
- Wake word activation: **"Hey Jansky"**
- Natural voice interaction with streaming responses

### 1.4 Key Design Decisions (Research-Validated)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Local LLM | Single Qwen2.5:1.5b for routing AND chat | Native tool-calling, ~3GB RAM, ~10 t/s on Pi 5 |
| STT | Whisper.cpp base.en-q5_0 | Balance of speed (~5-8s) and accuracy (~8% WER) |
| TTS | Piper TTS with streaming | Fast, natural, ~50MB RAM, streaming capable |
| Wake Word | openWakeWord (custom trained) | Open source, trainable, runs on Pi 3 single core |
| Cloud API | Kimi K2 (Moonshot) | $0.15/M input tokens, excellent quality |
| UI | PyGame framebuffer (no X server) | ~50MB RAM, direct display access |

---

## 2. Hardware Specifications

### 2.1 Required Hardware

```yaml
compute:
  board: "Raspberry Pi 5"
  ram: "8GB"
  storage: "32GB+ microSD (Class 10/A2) or NVMe SSD recommended"
  cooling: "Active cooling REQUIRED (fan + heatsink)"

display:
  type: "Raspberry Pi Official 7\" Touchscreen (DSI)"
  resolution: "800x480"
  interface: "DSI"

audio_input:
  type: "USB Microphone"
  recommended: "ReSpeaker USB Mic Array or similar"
  sample_rate: "16000 Hz"
  channels: "1 (mono)"

audio_output:
  type: "USB Speaker or 3.5mm jack"
  recommended: "USB speaker for better quality"

connectivity:
  wifi: "Required for Cloud API and Weather"
  ethernet: "Optional (recommended for stability)"
```

### 2.2 Hardware Setup Commands

```bash
# Test audio devices
arecord -l  # List recording devices
aplay -l    # List playback devices

# Set default audio (adjust card/device numbers)
# Add to ~/.asoundrc or /etc/asound.conf
```

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERACTION                          │
│  [Microphone] ──► [Wake Word] ──► [STT] ──► [Orchestrator]      │
│                                                    │              │
│  [Speaker] ◄── [TTS] ◄── [Response] ◄─────────────┘              │
│                                                                   │
│  [Display/Face] ◄── [UI Manager] ◄───── [State Updates]              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR (Python)                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Tool Router                            │   │
│  │  Input: User text + Tool definitions                      │   │
│  │  Output: Tool call JSON OR direct chat response           │   │
│  └──────────────────────────────────────────────────────────┘   │
│           │              │              │         │
│           ▼              ▼              ▼         │
│      [TIME]       [WEATHER]    [CLOUD_HANDOFF]   │
│           │              │              │         │
│           ▼              ▼              ▼         │
│       Python        OpenWeather     Kimi K2       │
│       datetime          API           API          │
│                                                                  │
│  [LOCAL_CHAT] ◄── No tool call detected ── [Qwen2.5:1.5b]      │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow (Detailed)

```
1. IDLE STATE
   └── openWakeWord listening continuously (CPU: ~5%)
   └── UI showing "Idle" animation
   └── Qwen2.5:1.5b loaded in Ollama (RAM: ~3GB)

2. WAKE WORD DETECTED ("Hey Jansky")
   └── State → LISTENING
   └── UI shows "Listening" animation
   └── Whisper.cpp starts recording (VAD-based end detection)

3. SPEECH CAPTURED
   └── State → THINKING
   └── UI shows "Thinking" animation
   └── Whisper transcribes audio → text

4. ROUTING DECISION (Qwen2.5:1.5b with tools)
   └── Input: User text + tool definitions (JSON)
   └── Output: Structured JSON response
   
   CASE A: {"tool": "TIME"}
      └── Python datetime → formatted string
      └── String → TTS → Audio
      
   CASE B: {"tool": "WEATHER", "location": "..."}
      └── OpenWeatherMap API call
      └── Parse response → natural sentence
      └── Sentence → TTS → Audio
      
   CASE C: {"tool": "CLOUD_HANDOFF", "query": "..."}
      └── Load cloud_soul.md context
      └── Send to Kimi K2 API
      └── Stream response → TTS (streaming)
      
   CASE D: {"response": "..."} (no tool, direct chat)
      └── Response → TTS → Audio

5. RESPONSE DELIVERY
   └── State → SPEAKING
   └── UI shows "Speaking" animation (amplitude-reactive)
   └── Piper TTS generates audio (streaming if enabled)
   └── Audio plays through speaker
   └── Microphone MUTED during playback

6. RETURN TO IDLE
   └── State → IDLE
   └── UI shows "Idle" animation
   └── Resume wake word detection
```

### 3.3 State Machine

```python
# Valid states
class SystemState(Enum):
    IDLE = "idle"           # Listening for wake word
    LISTENING = "listening" # Recording user speech
    THINKING = "thinking"   # Processing/routing
    SPEAKING = "speaking"   # Playing TTS output
    ERROR = "error"         # Error state (auto-recovers)

# Valid transitions
TRANSITIONS = {
    SystemState.IDLE: [SystemState.LISTENING],
    SystemState.LISTENING: [SystemState.THINKING, SystemState.IDLE],
    SystemState.THINKING: [SystemState.SPEAKING, SystemState.ERROR],
    SystemState.SPEAKING: [SystemState.IDLE],
    SystemState.ERROR: [SystemState.IDLE],
}
```

---

## 4. Technical Stack (Validated)

### 4.1 Core Components

| Component | Technology | Version/Model | Installation |
|-----------|------------|---------------|--------------|
| Runtime | Python | 3.11+ | System default |
| Orchestrator | Custom Python | - | Local code |
| Model Runtime | Ollama | Latest | `curl -fsSL https://ollama.com/install.sh \| sh` |
| Local LLM | Qwen2.5:1.5b | `qwen2.5:1.5b` | `ollama pull qwen2.5:1.5b` |
| Wake Word | openWakeWord | 0.6.0+ | `pip install openwakeword` |
| STT | Whisper.cpp | Latest | Build from source (see below) |
| TTS | Piper | 1.2.0+ | Download binary + voice model |
| UI | PyGame | 2.5.0+ | `pip install pygame` |
| HTTP Client | httpx | 0.25+ | `pip install httpx` |
| Audio | sounddevice | 0.4.6+ | `pip install sounddevice` |

### 4.2 Installation Scripts

#### 4.2.1 System Dependencies

```bash
#!/bin/bash
# install_system_deps.sh

# Update system
sudo apt update && sudo apt upgrade -y

# Install build tools
sudo apt install -y build-essential cmake git

# Install audio dependencies
sudo apt install -y portaudio19-dev libsndfile1 libspeexdsp-dev

# Install Python dependencies
sudo apt install -y python3-pip python3-venv python3-dev

# Install SDL2 for PyGame framebuffer
sudo apt install -y libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev

# Disable GUI for headless operation (optional, saves RAM)
# sudo systemctl set-default multi-user.target
```

#### 4.2.2 Ollama Setup

```bash
#!/bin/bash
# install_ollama.sh

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Enable Ollama service
sudo systemctl enable ollama
sudo systemctl start ollama

# Wait for Ollama to be ready
sleep 5

# Pull required model
ollama pull qwen2.5:1.5b

# Verify models
ollama list
```

#### 4.2.3 Whisper.cpp Build

```bash
#!/bin/bash
# install_whisper.sh

cd /home/pi

# Clone whisper.cpp
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp

# Build with optimizations for Pi 5
make clean
WHISPER_NO_METAL=1 make -j4

# Download base.en model (quantized)
bash ./models/download-ggml-model.sh base.en

# Quantize for better performance (optional)
# ./quantize models/ggml-base.en.bin models/ggml-base.en-q5_0.bin q5_0

# Test
./main -m models/ggml-base.en.bin -f samples/jfk.wav

# Create symlink for easy access
sudo ln -sf /home/pi/whisper.cpp/main /usr/local/bin/whisper-cpp
```

#### 4.2.4 Piper TTS Setup

```bash
#!/bin/bash
# install_piper.sh

cd /home/pi

# Download Piper binary for ARM64
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_arm64.tar.gz
tar -xzf piper_arm64.tar.gz
rm piper_arm64.tar.gz

# Create voices directory
mkdir -p /home/pi/piper/voices

# Download a good English voice (lessac medium - natural sounding)
cd /home/pi/piper/voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

# Test Piper
echo "Hello, I am Jansky, your personal assistant." | /home/pi/piper/piper \
  --model /home/pi/piper/voices/en_US-lessac-medium.onnx \
  --output_file /tmp/test.wav

aplay /tmp/test.wav

# Create symlink
sudo ln -sf /home/pi/piper/piper /usr/local/bin/piper
```

#### 4.2.5 Python Environment

```bash
#!/bin/bash
# setup_python_env.sh

cd /home/pi

# Create project directory
mkdir -p jansky
cd jansky

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python packages
pip install \
  openwakeword \
  sounddevice \
  numpy \
  scipy \
  httpx \
  pygame \
  python-dotenv \
  pydantic

# For openWakeWord Speex noise suppression (optional but recommended)
pip install speexdsp-ns || echo "Speex not available, continuing without"

# Save requirements
pip freeze > requirements.txt
```

### 4.3 openWakeWord Custom Model Training

**Note:** Training happens on a separate machine (Colab/Laptop), not on Pi.

#### 4.3.1 Training on Google Colab

```python
# Open: https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb
# This is the official openWakeWord training notebook

# Key parameters for "Hey Jansky":
WAKE_WORD = "hey jansky"
TARGET_FALSE_ACCEPTS_PER_HOUR = 0.5
NUM_SYNTHETIC_SAMPLES = 10000  # More = better but slower

# After training, download:
# - hey_jansky.tflite (or .onnx)
# - hey_jansky_ref.json (optional, for verification)
```

#### 4.3.2 Transfer to Pi

```bash
# On your laptop after training:
scp hey_jansky.tflite pi@<pi-ip>:/home/pi/jansky/models/wake_word/
scp hey_jansky_ref.json pi@<pi-ip>:/home/pi/jansky/models/wake_word/
```

#### 4.3.3 Test Custom Wake Word

```python
# test_wake_word.py
import openwakeword
from openwakeword.model import Model
import sounddevice as sd
import numpy as np

# Load custom model
model = Model(
    wakeword_models=["/home/pi/jansky/models/wake_word/hey_jansky.tflite"],
    inference_framework="tflite"  # or "onnx"
)

# Audio settings
SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # 80ms at 16kHz

def audio_callback(indata, frames, time, status):
    audio = np.squeeze(indata)
    prediction = model.predict(audio)
    
    for model_name, score in prediction.items():
        if score > 0.5:  # Threshold
            print(f"Wake word detected! Score: {score:.3f}")

# Start listening
with sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype='int16',
    blocksize=CHUNK_SIZE,
    callback=audio_callback
):
    print("Listening for 'Hey Jansky'... Press Ctrl+C to stop.")
    while True:
        sd.sleep(100)
```

---

## 5. Memory Budget

### 5.1 RAM Allocation Plan

```
Total Available: 8192 MB
Reserved for OS:  ~500 MB
━━━━━━━━━━━━━━━━━━━━━━━━
Available:       ~7692 MB

NORMAL OPERATION:
├── Ollama + Qwen2.5:1.5b    ~3200 MB
├── Python Orchestrator       ~200 MB
├── openWakeWord              ~150 MB
├── Whisper.cpp (on-demand)   ~500 MB (loaded only during STT)
├── Piper TTS                  ~80 MB
├── PyGame UI                  ~50 MB
├── Audio buffers              ~50 MB
└── Headroom                  ~462 MB
━━━━━━━━━━━━━━━━━━━━━━━━
Total:                       ~4692 MB (57% utilization)
```

### 5.2 Ollama Model Management

```python
# ollama_manager.py

import httpx
import time
from typing import Optional

class OllamaManager:
    """Manages Ollama model loading for the chat model."""
    
    BASE_URL = "http://localhost:11434"
    CHAT_MODEL = "qwen2.5:1.5b"
    
    def __init__(self):
        self.client = httpx.Client(timeout=120.0)
    
    def ensure_loaded(self) -> bool:
        """Ensure the chat model is loaded in memory."""
        try:
            response = self.client.post(
                f"{self.BASE_URL}/api/generate",
                json={
                    "model": self.CHAT_MODEL,
                    "prompt": "hello",
                    "keep_alive": "10m"
                }
            )
            return True
        except Exception as e:
            print(f"Error loading {self.CHAT_MODEL}: {e}")
            return False
    
    def generate(self, prompt: str, stream: bool = False):
        """Generate response from chat model."""
        payload = {
            "model": self.CHAT_MODEL,
            "prompt": prompt,
            "stream": stream
        }
        
        if stream:
            return self._stream_generate(payload)
        else:
            response = self.client.post(
                f"{self.BASE_URL}/api/generate",
                json=payload
            )
            return response.json().get("response", "")
    
    def _stream_generate(self, payload: dict):
        """Stream generate for real-time output."""
        with self.client.stream(
            "POST",
            f"{self.BASE_URL}/api/generate",
            json=payload
        ) as response:
            for line in response.iter_lines():
                if line:
                    import json
                    data = json.loads(line)
                    if "response" in data:
                        yield data["response"]
```

---

## 6. Implementation Phases

### Phase 1: Foundation (Audio Pipeline)

**Goal:** Establish basic audio I/O - speak and transcribe.

**Deliverable:** Terminal app that speaks text and transcribes speech.

#### 1.1 Tasks

```markdown
□ 1.1.1 Run install_system_deps.sh
□ 1.1.2 Run setup_python_env.sh  
□ 1.1.3 Run install_piper.sh
□ 1.1.4 Run install_whisper.sh
□ 1.1.5 Create audio_manager.py (handles mic/speaker)
□ 1.1.6 Create tts_engine.py (Piper wrapper)
□ 1.1.7 Create stt_engine.py (Whisper.cpp wrapper)
□ 1.1.8 Create test_audio_pipeline.py
□ 1.1.9 Verify: "You say something, it transcribes, it speaks back"
```

#### 1.2 Code: audio_manager.py

```python
# jansky/audio/audio_manager.py
"""
Handles audio input/output with self-muting during playback.
"""

import sounddevice as sd
import numpy as np
import wave
import tempfile
import subprocess
from pathlib import Path
from threading import Lock
from typing import Optional, Callable

class AudioManager:
    """Manages microphone input and speaker output with muting."""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = 'int16'
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.is_muted = False
        self._mute_lock = Lock()
        self._recording = False
        self._audio_buffer = []
    
    def mute(self):
        """Mute microphone input (during TTS playback)."""
        with self._mute_lock:
            self.is_muted = True
    
    def unmute(self):
        """Unmute microphone input."""
        with self._mute_lock:
            self.is_muted = False
    
    def record_until_silence(
        self,
        silence_threshold: float = 0.01,
        silence_duration: float = 1.5,
        max_duration: float = 30.0
    ) -> Optional[np.ndarray]:
        """
        Record audio until silence is detected.
        
        Args:
            silence_threshold: RMS threshold for silence detection
            silence_duration: Seconds of silence to stop recording
            max_duration: Maximum recording duration
        
        Returns:
            Audio as numpy array, or None if muted
        """
        if self.is_muted:
            return None
        
        self._audio_buffer = []
        self._recording = True
        silence_samples = 0
        silence_samples_needed = int(silence_duration * self.sample_rate / 1024)
        max_samples = int(max_duration * self.sample_rate / 1024)
        total_samples = 0
        
        def callback(indata, frames, time, status):
            if status:
                print(f"Audio status: {status}")
            
            if self.is_muted or not self._recording:
                return
            
            self._audio_buffer.append(indata.copy())
        
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=1024,
            callback=callback
        ):
            while self._recording and total_samples < max_samples:
                sd.sleep(100)
                total_samples += 1
                
                if len(self._audio_buffer) > 0:
                    # Check for silence
                    recent = self._audio_buffer[-1]
                    rms = np.sqrt(np.mean(recent.astype(np.float32) ** 2)) / 32768
                    
                    if rms < silence_threshold:
                        silence_samples += 1
                        if silence_samples >= silence_samples_needed:
                            break
                    else:
                        silence_samples = 0
        
        self._recording = False
        
        if len(self._audio_buffer) == 0:
            return None
        
        return np.concatenate(self._audio_buffer, axis=0)
    
    def save_to_wav(self, audio: np.ndarray, filepath: str):
        """Save audio array to WAV file."""
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio.tobytes())
    
    def play_wav(self, filepath: str):
        """Play a WAV file through speakers."""
        self.mute()  # Mute mic during playback
        try:
            # Use aplay for reliable playback
            subprocess.run(
                ["aplay", "-D", "default", filepath],
                check=True,
                capture_output=True
            )
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
```

#### 1.3 Code: tts_engine.py

```python
# jansky/audio/tts_engine.py
"""
Piper TTS wrapper with optional streaming support.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Generator
import os

class PiperTTS:
    """Piper TTS engine wrapper."""
    
    def __init__(
        self,
        piper_path: str = "/usr/local/bin/piper",
        model_path: str = "/home/pi/piper/voices/en_US-lessac-medium.onnx",
        speaking_rate: float = 1.0
    ):
        self.piper_path = piper_path
        self.model_path = model_path
        self.speaking_rate = speaking_rate
        
        # Verify paths
        if not Path(piper_path).exists():
            raise FileNotFoundError(f"Piper not found at {piper_path}")
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Voice model not found at {model_path}")
    
    def synthesize(self, text: str, output_path: Optional[str] = None) -> str:
        """
        Synthesize text to speech.
        
        Args:
            text: Text to synthesize
            output_path: Optional output path, generates temp file if None
        
        Returns:
            Path to generated WAV file
        """
        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
        
        # Run Piper
        process = subprocess.run(
            [
                self.piper_path,
                "--model", self.model_path,
                "--output_file", output_path
            ],
            input=text.encode('utf-8'),
            capture_output=True
        )
        
        if process.returncode != 0:
            raise RuntimeError(f"Piper failed: {process.stderr.decode()}")
        
        return output_path
    
    def synthesize_streaming(self, text: str) -> Generator[bytes, None, None]:
        """
        Synthesize with streaming output (for real-time playback).
        
        Yields chunks of raw PCM audio data.
        """
        process = subprocess.Popen(
            [
                self.piper_path,
                "--model", self.model_path,
                "--output-raw"  # Output raw PCM instead of WAV
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Send text
        process.stdin.write(text.encode('utf-8'))
        process.stdin.close()
        
        # Stream output in chunks
        chunk_size = 4096
        while True:
            chunk = process.stdout.read(chunk_size)
            if not chunk:
                break
            yield chunk
        
        process.wait()
```

#### 1.4 Code: stt_engine.py

```python
# jansky/audio/stt_engine.py
"""
Whisper.cpp STT wrapper.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import os

class WhisperSTT:
    """Whisper.cpp speech-to-text engine."""
    
    def __init__(
        self,
        whisper_path: str = "/usr/local/bin/whisper-cpp",
        model_path: str = "/home/pi/whisper.cpp/models/ggml-base.en.bin",
        language: str = "en",
        threads: int = 4
    ):
        self.whisper_path = whisper_path
        self.model_path = model_path
        self.language = language
        self.threads = threads
        
        # Verify paths
        if not Path(whisper_path).exists():
            # Try alternative path
            alt_path = "/home/pi/whisper.cpp/main"
            if Path(alt_path).exists():
                self.whisper_path = alt_path
            else:
                raise FileNotFoundError(f"Whisper not found at {whisper_path}")
        
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model not found at {model_path}")
    
    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe audio file to text.
        
        Args:
            audio_path: Path to WAV file (16kHz, mono, 16-bit)
        
        Returns:
            Transcribed text
        """
        # Run whisper.cpp
        process = subprocess.run(
            [
                self.whisper_path,
                "-m", self.model_path,
                "-f", audio_path,
                "-l", self.language,
                "-t", str(self.threads),
                "--no-timestamps",
                "-otxt"  # Output plain text
            ],
            capture_output=True,
            text=True
        )
        
        if process.returncode != 0:
            raise RuntimeError(f"Whisper failed: {process.stderr}")
        
        # Parse output (whisper outputs to stdout with -otxt)
        text = process.stdout.strip()
        
        # Clean up common artifacts
        text = text.replace("[BLANK_AUDIO]", "").strip()
        
        return text
    
    def transcribe_audio_array(self, audio, sample_rate: int = 16000) -> str:
        """
        Transcribe audio from numpy array.
        
        Args:
            audio: Numpy array of audio samples
            sample_rate: Sample rate of audio
        
        Returns:
            Transcribed text
        """
        import numpy as np
        import wave
        
        # Save to temp file
        fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        
        try:
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio.tobytes())
            
            return self.transcribe(temp_path)
        finally:
            os.unlink(temp_path)
```

#### 1.5 Test Script

```python
# jansky/tests/test_audio_pipeline.py
"""
Test the complete audio pipeline.
"""

import sys
sys.path.insert(0, '/home/pi/jansky')

from audio.audio_manager import AudioManager
from audio.tts_engine import PiperTTS
from audio.stt_engine import WhisperSTT

def test_tts():
    """Test text-to-speech."""
    print("Testing TTS...")
    tts = PiperTTS()
    audio_path = tts.synthesize("Hello! I am Jansky, your personal assistant.")
    
    audio = AudioManager()
    audio.play_wav(audio_path)
    print("✓ TTS working")

def test_stt():
    """Test speech-to-text."""
    print("Testing STT...")
    print("Speak now... (recording for up to 10 seconds)")
    
    audio = AudioManager()
    recording = audio.record_until_silence(max_duration=10.0)
    
    if recording is None or len(recording) == 0:
        print("✗ No audio recorded")
        return
    
    stt = WhisperSTT()
    text = stt.transcribe_audio_array(recording)
    print(f"✓ Transcribed: {text}")

def test_round_trip():
    """Test full round-trip: speak -> transcribe -> speak back."""
    print("\nTesting round-trip...")
    print("Say something, I'll repeat it back...")
    
    audio = AudioManager()
    tts = PiperTTS()
    stt = WhisperSTT()
    
    # Record
    recording = audio.record_until_silence()
    if recording is None:
        print("✗ No audio recorded")
        return
    
    # Transcribe
    text = stt.transcribe_audio_array(recording)
    print(f"You said: {text}")
    
    # Speak back
    response = f"You said: {text}"
    audio_path = tts.synthesize(response)
    audio.play_wav(audio_path)
    
    print("✓ Round-trip complete")

if __name__ == "__main__":
    test_tts()
    test_stt()
    test_round_trip()
```

---

### Phase 2: Brain (LLM Router)

**Goal:** Implement single LLM for routing and chat using Qwen2.5 with tool calling.

**Deliverable:** Text-based chatbot that routes to tools or responds directly.

#### 2.1 Tasks

```markdown
□ 2.1.1 Run install_ollama.sh
□ 2.1.2 Verify Ollama running: curl http://localhost:11434/api/tags
□ 2.1.3 Create ollama_client.py (low-level Ollama API wrapper)
□ 2.1.4 Create tool_definitions.py (JSON schemas for tools)
□ 2.1.5 Create router.py (main routing logic)
□ 2.1.6 Create tools/time_tool.py
□ 2.1.7 Create tools/weather_tool.py
□ 2.1.8 Create cloud_client.py (Kimi K2 API)
□ 2.1.9 Create test_router.py
□ 2.1.10 Verify: Text queries correctly route to tools or local chat
```

#### 2.2 Code: tool_definitions.py

```python
# jansky/brain/tool_definitions.py
"""
Tool definitions for Qwen2.5 function calling.
"""

TOOLS = [
    {
        "type": "function", 
        "function": {
            "name": "get_current_time",
            "description": "Get the current time and date. Use when user asks what time it is, what day it is, or current date.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather information for a location. Use when user asks about weather, temperature, or conditions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or location (e.g., 'London', 'New York', 'Tokyo'). If not specified, use 'current location'."
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cloud_handoff",
            "description": "Hand off complex queries to cloud AI for better answers. Use for: creative writing, complex reasoning, coding questions, detailed explanations, anything requiring deep knowledge or nuanced responses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The full user query to send to cloud AI"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# System prompt for the router
SYSTEM_PROMPT = """You are Jansky, a helpful voice assistant running on a Raspberry Pi. You have access to tools for specific tasks.

IMPORTANT RULES:
1. For simple greetings, casual chat, and basic questions - respond directly without using tools
2. For time/date questions - use get_current_time
3. For weather questions - use get_weather
4. For complex questions requiring detailed knowledge, creative tasks, or coding - use cloud_handoff

Keep responses concise and conversational since they will be spoken aloud. Avoid long lists or complex formatting."""
```

#### 2.3 Code: ollama_client.py

```python
# jansky/brain/ollama_client.py
"""
Ollama API client with tool calling support.
"""

import httpx
import json
from typing import Optional, Dict, Any, List, Generator
from dataclasses import dataclass

@dataclass
class ToolCall:
    """Represents a tool call from the model."""
    name: str
    arguments: Dict[str, Any]

@dataclass
class ChatResponse:
    """Response from chat completion."""
    content: Optional[str]
    tool_calls: List[ToolCall]
    is_tool_call: bool

class OllamaClient:
    """Client for Ollama API with tool calling."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:1.5b",
        timeout: float = 120.0
    ):
        self.base_url = base_url
        self.model = model
        self.client = httpx.Client(timeout=timeout)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        stream: bool = False
    ) -> ChatResponse:
        """
        Send chat completion request with optional tools.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            stream: Whether to stream the response
        
        Returns:
            ChatResponse with content and/or tool calls
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": 0.7,
                "num_predict": 512
            }
        }
        
        if tools:
            payload["tools"] = tools
        
        response = self.client.post(
            f"{self.base_url}/api/chat",
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        message = data.get("message", {})
        
        # Check for tool calls
        tool_calls = []
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                tool_calls.append(ToolCall(
                    name=tc["function"]["name"],
                    arguments=tc["function"].get("arguments", {})
                ))
        
        return ChatResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            is_tool_call=len(tool_calls) > 0
        )
    
    def chat_stream(
        self,
        messages: List[Dict[str, str]]
    ) -> Generator[str, None, None]:
        """
        Stream chat completion response.
        
        Yields content chunks as they arrive.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True
        }
        
        with self.client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload
        ) as response:
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        yield data["message"]["content"]
    
    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except:
            return False
    
```

#### 2.4 Code: router.py

```python
# jansky/brain/router.py
"""
Main routing logic - single LLM for routing and chat.
"""

from typing import Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from .ollama_client import OllamaClient, ChatResponse
from .tool_definitions import TOOLS, SYSTEM_PROMPT

class ToolType(Enum):
    TIME = "get_current_time"
    WEATHER = "get_weather"
    CLOUD = "cloud_handoff"
    NONE = "none"  # Direct chat response

@dataclass
class RouterResult:
    """Result from the router."""
    tool: ToolType
    response: Optional[str]  # Direct response if no tool
    arguments: dict  # Tool arguments if tool called

class Router:
    """Routes user queries to appropriate handlers."""
    
    def __init__(self, ollama_client: OllamaClient):
        self.client = ollama_client
        self.conversation_history = []
    
    def route(self, user_input: str) -> RouterResult:
        """
        Route user input to appropriate handler.
        
        Args:
            user_input: Transcribed user speech
        
        Returns:
            RouterResult indicating what action to take
        """
        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        
        # Add conversation history (keep last 4 exchanges for context)
        messages.extend(self.conversation_history[-8:])
        
        # Add current user message
        messages.append({"role": "user", "content": user_input})
        
        # Get response with tool calling
        response = self.client.chat(messages, tools=TOOLS)
        
        # Process response
        if response.is_tool_call:
            tool_call = response.tool_calls[0]  # Take first tool call
            
            tool_type = ToolType(tool_call.name)
            
            # Add to history
            self.conversation_history.append(
                {"role": "user", "content": user_input}
            )
            
            return RouterResult(
                tool=tool_type,
                response=None,
                arguments=tool_call.arguments
            )
        else:
            # Direct chat response
            self.conversation_history.append(
                {"role": "user", "content": user_input}
            )
            self.conversation_history.append(
                {"role": "assistant", "content": response.content}
            )
            
            return RouterResult(
                tool=ToolType.NONE,
                response=response.content,
                arguments={}
            )
    
    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
```

#### 2.5 Code: tools/time_tool.py

```python
# jansky/brain/tools/time_tool.py
"""
Time tool - returns current time and date.
"""

from datetime import datetime

def get_current_time() -> str:
    """Get current time formatted for speech."""
    now = datetime.now()
    
    # Format for natural speech
    time_str = now.strftime("%-I:%M %p")  # e.g., "3:45 PM"
    date_str = now.strftime("%A, %B %-d")  # e.g., "Monday, January 15"
    
    return f"It's {time_str} on {date_str}."
```

#### 2.6 Code: tools/weather_tool.py

```python
# jansky/brain/tools/weather_tool.py
"""
Weather tool - fetches weather from OpenWeatherMap.
"""

import httpx
from typing import Optional
import os

class WeatherTool:
    """Fetches weather data from OpenWeatherMap."""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenWeatherMap API key required")
        
        self.client = httpx.Client(timeout=10.0)
    
    def get_weather(self, location: str) -> str:
        """
        Get weather for a location.
        
        Args:
            location: City name (e.g., "London", "New York")
        
        Returns:
            Natural language weather description
        """
        try:
            response = self.client.get(
                self.BASE_URL,
                params={
                    "q": location,
                    "appid": self.api_key,
                    "units": "metric"  # Celsius
                }
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract weather info
            temp = round(data["main"]["temp"])
            feels_like = round(data["main"]["feels_like"])
            description = data["weather"][0]["description"]
            humidity = data["main"]["humidity"]
            city = data["name"]
            
            # Format for speech
            return (
                f"In {city}, it's currently {temp} degrees Celsius "
                f"with {description}. "
                f"It feels like {feels_like} degrees, "
                f"and humidity is {humidity} percent."
            )
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"I couldn't find weather data for {location}."
            raise
        except Exception as e:
            return f"Sorry, I couldn't get the weather right now. {str(e)}"
```

#### 2.7 Code: cloud_client.py

```python
# jansky/brain/cloud_client.py
"""
Cloud API client for Kimi K2 (Moonshot).
"""

import httpx
import json
from typing import Generator, Optional
from pathlib import Path
import os

class KimiClient:
    """Client for Kimi K2 (Moonshot) API."""
    
    BASE_URL = "https://api.moonshot.cn/v1"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        soul_path: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("MOONSHOT_API_KEY")
        if not self.api_key:
            raise ValueError("Moonshot API key required")
        
        self.client = httpx.Client(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        
        # Load cloud soul/personality
        self.soul_prompt = ""
        if soul_path and Path(soul_path).exists():
            self.soul_prompt = Path(soul_path).read_text()
    
    def chat(
        self,
        query: str,
        stream: bool = True
    ) -> Generator[str, None, None] | str:
        """
        Send query to Kimi K2.
        
        Args:
            query: User query
            stream: Whether to stream response
        
        Returns:
            Generated response (streamed or complete)
        """
        messages = []
        
        # Add soul/personality if available
        if self.soul_prompt:
            messages.append({
                "role": "system",
                "content": self.soul_prompt
            })
        
        messages.append({
            "role": "user",
            "content": query
        })
        
        payload = {
            "model": "moonshot-v1-8k",  # or "kimi-k2" when available
            "messages": messages,
            "temperature": 0.7,
            "stream": stream
        }
        
        if stream:
            return self._stream_chat(payload)
        else:
            response = self.client.post(
                f"{self.BASE_URL}/chat/completions",
                json=payload
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    
    def _stream_chat(self, payload: dict) -> Generator[str, None, None]:
        """Stream chat response."""
        with self.client.stream(
            "POST",
            f"{self.BASE_URL}/chat/completions",
            json=payload
        ) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
                    except json.JSONDecodeError:
                        continue
```

#### 2.8 Test Script for Router

```python
# jansky/tests/test_router.py
"""
Test the routing logic.
"""

import sys
sys.path.insert(0, '/home/pi/jansky')

from brain.ollama_client import OllamaClient
from brain.router import Router, ToolType

def test_router():
    """Test routing decisions."""
    
    client = OllamaClient(model="qwen2.5:1.5b")
    
    if not client.is_available():
        print("✗ Ollama not running!")
        return
    
    router = Router(client)
    
    test_cases = [
        # (input, expected_tool)
        ("Hello, how are you?", ToolType.NONE),
        ("What time is it?", ToolType.TIME),
        ("What's the weather in London?", ToolType.WEATHER),
        ("Write me a poem about stars", ToolType.CLOUD),
        ("Tell me a joke", ToolType.NONE),  # Simple enough for local
    ]
    
    print("Testing router decisions...\n")
    
    for user_input, expected in test_cases:
        result = router.route(user_input)
        status = "✓" if result.tool == expected else "✗"
        print(f"{status} Input: '{user_input}'")
        print(f"   Expected: {expected.value}, Got: {result.tool.value}")
        if result.response:
            print(f"   Response: {result.response[:100]}...")
        print()
    
    print("Router test complete!")

if __name__ == "__main__":
    test_router()
```

---

### Phase 3: Senses (Wake Word)

**Goal:** Add wake word detection for hands-free activation.

**Deliverable:** System responds to "Hey Jansky" and begins listening.

#### 3.1 Tasks

```markdown
□ 3.1.1 Train "Hey Jansky" wake word model (on Colab/laptop)
□ 3.1.2 Transfer wake word model to Pi
□ 3.1.3 Create wake_word_detector.py
□ 3.1.4 Create test_wake_word.py
□ 3.1.5 Verify: Wake word triggers listening reliably
```

#### 3.2 Code: wake_word_detector.py

```python
# jansky/senses/wake_word_detector.py
"""
Wake word detection using openWakeWord.
"""

import numpy as np
import sounddevice as sd
from openwakeword.model import Model
from typing import Callable, Optional
from threading import Thread, Event
from pathlib import Path

class WakeWordDetector:
    """Detects "Hey Jansky" wake word."""
    
    def __init__(
        self,
        model_path: str = "/home/pi/jansky/models/wake_word/hey_jansky.tflite",
        threshold: float = 0.5,
        sample_rate: int = 16000,
        inference_framework: str = "tflite"
    ):
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.chunk_size = 1280  # 80ms chunks
        
        # Load model
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Wake word model not found: {model_path}")
        
        self.model = Model(
            wakeword_models=[model_path],
            inference_framework=inference_framework
        )
        
        self._running = False
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._callback: Optional[Callable] = None
        self._paused = False
    
    def start(self, callback: Callable[[], None]):
        """
        Start listening for wake word.
        
        Args:
            callback: Function to call when wake word detected
        """
        self._callback = callback
        self._running = True
        self._stop_event.clear()
        
        self._thread = Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop listening."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def pause(self):
        """Temporarily pause detection (during TTS playback)."""
        self._paused = True
    
    def resume(self):
        """Resume detection after pause."""
        self._paused = False
    
    def _listen_loop(self):
        """Main listening loop."""
        
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"Wake word audio status: {status}")
            
            if self._paused or not self._running:
                return
            
            # Convert to correct format
            audio = np.squeeze(indata).astype(np.int16)
            
            # Run detection
            predictions = self.model.predict(audio)
            
            # Check predictions
            for model_name, score in predictions.items():
                if score >= self.threshold:
                    print(f"Wake word detected! Score: {score:.3f}")
                    if self._callback:
                        self._callback()
                    # Reset model state to prevent repeated triggers
                    self.model.reset()
                    break
        
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype='int16',
            blocksize=self.chunk_size,
            callback=audio_callback
        ):
            while self._running:
                self._stop_event.wait(timeout=0.1)
```

---

### Phase 4: Interface (UI Face)

**Goal:** Create animated face display that reflects system state.

**Deliverable:** PyGame UI running on framebuffer showing reactive face.

#### 4.1 Tasks

```markdown
□ 4.1.1 Create face assets (PNG sprites for each state)
□ 4.1.2 Create ui_manager.py (PyGame framebuffer setup)
□ 4.1.3 Create face_animator.py (state-based animation)
□ 4.1.4 Implement IDLE animation (slow blink)
□ 4.1.5 Implement LISTENING animation (responsive to audio level)
□ 4.1.6 Implement THINKING animation (pulsing/spinning)
□ 4.1.7 Implement SPEAKING animation (mouth movement)
□ 4.1.8 Create test_ui.py
□ 4.1.9 Verify: UI responds to state changes smoothly
```

#### 4.2 Code: ui_manager.py

```python
# jansky/ui/ui_manager.py
"""
PyGame-based UI manager for framebuffer display.
"""

import os
import pygame
from enum import Enum
from typing import Optional, Tuple
from pathlib import Path
from threading import Thread, Lock
import time

# Force framebuffer driver for headless operation
os.environ["SDL_VIDEODRIVER"] = "fbcon"
os.environ["SDL_FBDEV"] = "/dev/fb0"

class UIState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"

class UIManager:
    """Manages the animated face display."""
    
    def __init__(
        self,
        width: int = 800,
        height: int = 480,
        assets_path: str = "/home/pi/jansky/assets/face",
        fps: int = 30
    ):
        self.width = width
        self.height = height
        self.assets_path = Path(assets_path)
        self.fps = fps
        
        self._state = UIState.IDLE
        self._state_lock = Lock()
        self._running = False
        self._thread: Optional[Thread] = None
        
        # Audio amplitude for reactive animations
        self._audio_amplitude = 0.0
        
        # Animation frame counters
        self._frame_count = 0
        self._blink_timer = 0
        
        # Initialize PyGame
        pygame.init()
        
        # Try to hide mouse cursor
        pygame.mouse.set_visible(False)
        
        # Set up display
        self.screen = pygame.display.set_mode(
            (width, height),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption("Jansky")
        
        # Load assets
        self._load_assets()
        
        # Colors
        self.bg_color = (10, 10, 20)  # Dark blue-black
        self.accent_color = (0, 200, 255)  # Cyan
    
    def _load_assets(self):
        """Load face sprite assets."""
        self.sprites = {}
        
        # Expected sprite files
        sprite_files = {
            "eye_open": "eye_open.png",
            "eye_closed": "eye_closed.png",
            "eye_listening": "eye_listening.png",
            "mouth_closed": "mouth_closed.png",
            "mouth_open_1": "mouth_open_1.png",
            "mouth_open_2": "mouth_open_2.png",
            "thinking_ring": "thinking_ring.png",
        }
        
        for name, filename in sprite_files.items():
            path = self.assets_path / filename
            if path.exists():
                self.sprites[name] = pygame.image.load(str(path)).convert_alpha()
            else:
                # Create placeholder if asset missing
                self.sprites[name] = self._create_placeholder(name)
    
    def _create_placeholder(self, name: str) -> pygame.Surface:
        """Create placeholder surface for missing assets."""
        if "eye" in name:
            size = (100, 60)
        elif "mouth" in name:
            size = (120, 40)
        else:
            size = (200, 200)
        
        surface = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.ellipse(surface, self.accent_color, surface.get_rect(), 3)
        return surface
    
    def set_state(self, state: UIState):
        """Set the current UI state."""
        with self._state_lock:
            self._state = state
    
    def set_audio_amplitude(self, amplitude: float):
        """Set audio amplitude for reactive animations (0.0 - 1.0)."""
        self._audio_amplitude = max(0.0, min(1.0, amplitude))
    
    def start(self):
        """Start the UI render loop."""
        self._running = True
        self._thread = Thread(target=self._render_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the UI."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        pygame.quit()
    
    def _render_loop(self):
        """Main render loop."""
        clock = pygame.time.Clock()
        
        while self._running:
            # Handle PyGame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                    break
            
            # Clear screen
            self.screen.fill(self.bg_color)
            
            # Render current state
            with self._state_lock:
                state = self._state
            
            if state == UIState.IDLE:
                self._render_idle()
            elif state == UIState.LISTENING:
                self._render_listening()
            elif state == UIState.THINKING:
                self._render_thinking()
            elif state == UIState.SPEAKING:
                self._render_speaking()
            elif state == UIState.ERROR:
                self._render_error()
            
            # Update display
            pygame.display.flip()
            
            self._frame_count += 1
            clock.tick(self.fps)
    
    def _render_idle(self):
        """Render idle state with occasional blinking."""
        # Blink every ~3 seconds
        blink_interval = self.fps * 3
        blink_duration = self.fps // 5  # ~200ms blink
        
        # Determine if blinking
        cycle_pos = self._frame_count % blink_interval
        is_blinking = cycle_pos < blink_duration
        
        # Draw eyes
        eye_sprite = "eye_closed" if is_blinking else "eye_open"
        self._draw_face(eye_sprite, "mouth_closed")
    
    def _render_listening(self):
        """Render listening state with amplitude-reactive eyes."""
        # Eyes get bigger with amplitude
        self._draw_face("eye_listening", "mouth_closed")
        
        # Draw amplitude indicator
        bar_height = int(self._audio_amplitude * 100)
        pygame.draw.rect(
            self.screen,
            self.accent_color,
            (self.width // 2 - 50, self.height - 50 - bar_height, 100, bar_height)
        )
    
    def _render_thinking(self):
        """Render thinking state with spinning indicator."""
        self._draw_face("eye_open", "mouth_closed")
        
        # Draw rotating ring
        if "thinking_ring" in self.sprites:
            angle = (self._frame_count * 5) % 360
            rotated = pygame.transform.rotate(self.sprites["thinking_ring"], angle)
            rect = rotated.get_rect(center=(self.width // 2, self.height // 2 + 100))
            self.screen.blit(rotated, rect)
    
    def _render_speaking(self):
        """Render speaking state with mouth animation."""
        # Alternate mouth based on amplitude
        if self._audio_amplitude > 0.3:
            mouth = "mouth_open_2"
        elif self._audio_amplitude > 0.1:
            mouth = "mouth_open_1"
        else:
            mouth = "mouth_closed"
        
        self._draw_face("eye_open", mouth)
    
    def _render_error(self):
        """Render error state."""
        self._draw_face("eye_closed", "mouth_closed")
        
        # Red tint
        overlay = pygame.Surface((self.width, self.height))
        overlay.fill((255, 0, 0))
        overlay.set_alpha(30)
        self.screen.blit(overlay, (0, 0))
    
    def _draw_face(self, eye_sprite: str, mouth_sprite: str):
        """Draw face with specified sprites."""
        center_x = self.width // 2
        center_y = self.height // 2
        
        # Eye positions
        eye_spacing = 150
        eye_y = center_y - 50
        
        # Draw left eye
        if eye_sprite in self.sprites:
            left_eye = self.sprites[eye_sprite]
            rect = left_eye.get_rect(center=(center_x - eye_spacing, eye_y))
            self.screen.blit(left_eye, rect)
        
        # Draw right eye
        if eye_sprite in self.sprites:
            right_eye = self.sprites[eye_sprite]
            rect = right_eye.get_rect(center=(center_x + eye_spacing, eye_y))
            self.screen.blit(right_eye, rect)
        
        # Draw mouth
        if mouth_sprite in self.sprites:
            mouth = self.sprites[mouth_sprite]
            rect = mouth.get_rect(center=(center_x, center_y + 80))
            self.screen.blit(mouth, rect)
```

---

### Phase 5: Integration (Full System)

**Goal:** Integrate all components into working assistant.

**Deliverable:** Complete "Hey Jansky" voice assistant.

#### 5.1 Tasks

```markdown
□ 5.1.1 Create main orchestrator.py (ties everything together)
□ 5.1.2 Create config.py (loads all configuration)
□ 5.1.3 Create soul files (local_soul.md, cloud_soul.md)
□ 5.1.4 Implement streaming TTS (if performance acceptable)
□ 5.1.5 Create systemd service file for auto-start
□ 5.1.6 Full integration testing
□ 5.1.7 Performance profiling and optimization
□ 5.1.8 Create README.md with usage instructions
```

#### 5.2 Code: orchestrator.py

```python
#!/usr/bin/env python3
# jansky/orchestrator.py
"""
Main orchestrator - ties all components together.
"""

import sys
import signal
import time
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
from brain.cloud_client import KimiClient
from senses.wake_word_detector import WakeWordDetector
from ui.ui_manager import UIManager, UIState

class Orchestrator:
    """Main system orchestrator."""
    
    def __init__(self, config: Config):
        self.config = config
        self._running = False
        
        # Initialize components
        print("Initializing Jansky...")
        
        # Audio
        print("  - Audio manager")
        self.audio = AudioManager()
        
        print("  - TTS engine")
        self.tts = PiperTTS(
            piper_path=config.piper_path,
            model_path=config.piper_voice
        )
        
        print("  - STT engine")
        self.stt = WhisperSTT(
            whisper_path=config.whisper_path,
            model_path=config.whisper_model
        )
        
        # Brain
        print("  - Ollama client")
        self.ollama = OllamaClient(model=config.chat_model)
        
        print("  - Router")
        self.router = Router(self.ollama)
        
        # Tools
        print("  - Weather tool")
        self.weather = WeatherTool(api_key=config.openweather_api_key)
        
        print("  - Cloud client")
        self.cloud = KimiClient(
            api_key=config.moonshot_api_key,
            soul_path=config.cloud_soul_path
        )
        
        # Senses
        print("  - Wake word detector")
        self.wake_word = WakeWordDetector(
            model_path=config.wake_word_model,
            threshold=config.wake_word_threshold
        )
        
        # UI
        print("  - UI manager")
        self.ui = UIManager(
            width=config.display_width,
            height=config.display_height,
            assets_path=config.assets_path
        )
        
        print("Initialization complete!")
    
    def start(self):
        """Start the assistant."""
        self._running = True
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Start UI
        self.ui.start()
        self.ui.set_state(UIState.IDLE)
        
        # Start wake word detection
        self.wake_word.start(callback=self._on_wake_word)
        
        # Speak startup message
        self._speak("Hello! I'm Jansky. Say hey Jansky to get my attention.")
        
        print("Jansky is running. Say 'Hey Jansky' to activate.")
        
        # Main loop
        while self._running:
            time.sleep(0.1)
        
        self._cleanup()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\nShutting down...")
        self._running = False
    
    def _cleanup(self):
        """Clean up resources."""
        self.wake_word.stop()
        self.ui.stop()
    
    def _on_wake_word(self):
        """Called when wake word is detected."""
        if not self._running:
            return
        
        print("Wake word detected!")
        
        # Pause wake word detection
        self.wake_word.pause()
        
        # Update UI
        self.ui.set_state(UIState.LISTENING)
        
        # Play acknowledgment sound (optional)
        # self._play_sound("ding.wav")
        
        # Record user speech
        print("Listening...")
        audio = self.audio.record_until_silence(
            silence_duration=1.5,
            max_duration=15.0
        )
        
        if audio is None or len(audio) == 0:
            print("No speech detected")
            self.ui.set_state(UIState.IDLE)
            self.wake_word.resume()
            return
        
        # Update UI
        self.ui.set_state(UIState.THINKING)
        
        # Transcribe
        print("Transcribing...")
        try:
            text = self.stt.transcribe_audio_array(audio)
            print(f"User said: {text}")
        except Exception as e:
            print(f"Transcription error: {e}")
            self._speak("Sorry, I didn't catch that.")
            self.ui.set_state(UIState.IDLE)
            self.wake_word.resume()
            return
        
        if not text.strip():
            self._speak("I didn't hear anything.")
            self.ui.set_state(UIState.IDLE)
            self.wake_word.resume()
            return
        
        # Route and respond
        try:
            self._process_query(text)
        except Exception as e:
            print(f"Processing error: {e}")
            self._speak("Sorry, something went wrong.")
            self.ui.set_state(UIState.ERROR)
            time.sleep(1)
        
        # Return to idle
        self.ui.set_state(UIState.IDLE)
        self.wake_word.resume()
    
    def _process_query(self, text: str):
        """Process user query through router."""
        result = self.router.route(text)
        
        if result.tool == ToolType.NONE:
            # Direct chat response
            self._speak(result.response)
        
        elif result.tool == ToolType.TIME:
            response = get_current_time()
            self._speak(response)
        
        elif result.tool == ToolType.WEATHER:
            location = result.arguments.get("location", "current location")
            response = self.weather.get_weather(location)
            self._speak(response)
        
        elif result.tool == ToolType.CLOUD:
            query = result.arguments.get("query", text)
            self._handle_cloud_query(query)
    
    def _handle_cloud_query(self, query: str):
        """Handle cloud API query with optional streaming."""
        self._speak("Let me think about that...")
        
        if self.config.enable_streaming_tts:
            # Stream response
            full_response = ""
            for chunk in self.cloud.chat(query, stream=True):
                full_response += chunk
                # Could implement streaming TTS here
            self._speak(full_response)
        else:
            # Non-streaming
            response = self.cloud.chat(query, stream=False)
            self._speak(response)
    
    def _speak(self, text: str):
        """Speak text through TTS."""
        if not text:
            return
        
        print(f"Speaking: {text}")
        self.ui.set_state(UIState.SPEAKING)
        
        try:
            audio_path = self.tts.synthesize(text)
            self.audio.play_wav(audio_path)
        except Exception as e:
            print(f"TTS error: {e}")
        
        self.ui.set_state(UIState.IDLE)


def main():
    """Main entry point."""
    config = Config.load()
    orchestrator = Orchestrator(config)
    orchestrator.start()


if __name__ == "__main__":
    main()
```

#### 5.3 Code: config.py

```python
# jansky/config.py
"""
Configuration management.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json

@dataclass
class Config:
    """Application configuration."""
    
    # Paths
    project_root: str = "/home/pi/jansky"
    assets_path: str = "/home/pi/jansky/assets/face"
    
    # Audio
    piper_path: str = "/usr/local/bin/piper"
    piper_voice: str = "/home/pi/piper/voices/en_US-lessac-medium.onnx"
    whisper_path: str = "/home/pi/whisper.cpp/main"
    whisper_model: str = "/home/pi/whisper.cpp/models/ggml-base.en.bin"
    
    # Models
    chat_model: str = "qwen2.5:1.5b"
    
    # Wake word
    wake_word_model: str = "/home/pi/jansky/models/wake_word/hey_jansky.tflite"
    wake_word_threshold: float = 0.5
    
    # API Keys (loaded from environment)
    openweather_api_key: str = ""
    moonshot_api_key: str = ""
    
    # Soul/personality files
    local_soul_path: str = "/home/pi/jansky/config/local_soul.md"
    cloud_soul_path: str = "/home/pi/jansky/config/cloud_soul.md"
    
    # Display
    display_width: int = 800
    display_height: int = 480
    
    # Features
    enable_streaming_tts: bool = False  # Set True if performance acceptable
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """Load configuration from file and environment."""
        config = cls()
        
        # Load from JSON file if exists
        if config_path is None:
            config_path = os.path.join(config.project_root, "config", "config.json")
        
        if Path(config_path).exists():
            with open(config_path) as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
        
        # Override with environment variables
        config.openweather_api_key = os.getenv(
            "OPENWEATHER_API_KEY",
            config.openweather_api_key
        )
        config.moonshot_api_key = os.getenv(
            "MOONSHOT_API_KEY",
            config.moonshot_api_key
        )
        
        return config
    
    def save(self, config_path: Optional[str] = None):
        """Save configuration to file."""
        if config_path is None:
            config_path = os.path.join(self.project_root, "config", "config.json")
        
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Don't save API keys to file
        data = {
            k: v for k, v in self.__dict__.items()
            if not k.endswith("_api_key")
        }
        
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
```

#### 5.4 Soul Files

```markdown
<!-- /home/pi/jansky/config/local_soul.md -->
You are Jansky, a helpful voice assistant. Keep responses brief and conversational since they will be spoken aloud. Be friendly but concise.
```

```markdown
<!-- /home/pi/jansky/config/cloud_soul.md -->
# Jansky - Personal AI Assistant

You are Jansky, a helpful, knowledgeable AI assistant running on a Raspberry Pi. You were named after Karl Jansky, the pioneer of radio astronomy.

## Personality
- Friendly and approachable
- Curious and eager to help
- Concise in speech (responses will be spoken aloud)
- Occasionally makes gentle jokes or observations
- Humble about limitations

## Guidelines
- Keep responses under 100 words when possible
- Avoid bullet points and complex formatting
- Speak naturally, as in conversation
- If you don't know something, say so
- Be helpful but don't be verbose

## Voice
Warm, clear, and slightly enthusiastic. Like a knowledgeable friend who's happy to help.
```

#### 5.5 Systemd Service

```ini
# /etc/systemd/system/jansky.service
[Unit]
Description=Jansky AI Assistant
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/jansky
Environment=DISPLAY=:0
Environment=SDL_VIDEODRIVER=fbcon
Environment=SDL_FBDEV=/dev/fb0
EnvironmentFile=/home/pi/jansky/.env
ExecStart=/home/pi/jansky/venv/bin/python orchestrator.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable service
sudo systemctl daemon-reload
sudo systemctl enable jansky.service
sudo systemctl start jansky.service

# View logs
sudo journalctl -u jansky.service -f
```

---

## 7. File Structure

```
/home/pi/jansky/
├── venv/                      # Python virtual environment
├── config/
│   ├── config.json            # Main configuration
│   ├── local_soul.md          # Local LLM personality
│   └── cloud_soul.md          # Cloud LLM personality
├── models/
│   └── wake_word/
│       ├── hey_jansky.tflite  # Trained wake word model
│       └── hey_jansky_ref.json
├── assets/
│   └── face/
│       ├── eye_open.png
│       ├── eye_closed.png
│       ├── eye_listening.png
│       ├── mouth_closed.png
│       ├── mouth_open_1.png
│       ├── mouth_open_2.png
│       └── thinking_ring.png
├── audio/
│   ├── __init__.py
│   ├── audio_manager.py
│   ├── tts_engine.py
│   └── stt_engine.py
├── brain/
│   ├── __init__.py
│   ├── ollama_client.py
│   ├── router.py
│   ├── tool_definitions.py
│   ├── cloud_client.py
│   └── tools/
│       ├── __init__.py
│       ├── time_tool.py
│       └── weather_tool.py
├── senses/
│   ├── __init__.py
│   └── wake_word_detector.py
├── ui/
│   ├── __init__.py
│   └── ui_manager.py
├── tests/
│   ├── test_audio_pipeline.py
│   ├── test_router.py
│   ├── test_wake_word.py
│   └── test_integration.py
├── scripts/
│   ├── install_system_deps.sh
│   ├── install_ollama.sh
│   ├── install_whisper.sh
│   ├── install_piper.sh
│   └── setup_python_env.sh
├── orchestrator.py            # Main entry point
├── config.py                  # Configuration loader
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (API keys)
└── README.md
```

---

## 8. Configuration Files

### 8.1 Environment Variables (.env)

```bash
# /home/pi/jansky/.env
OPENWEATHER_API_KEY=your_openweather_api_key_here
MOONSHOT_API_KEY=your_moonshot_api_key_here
```

### 8.2 Main Config (config.json)

```json
{
  "project_root": "/home/pi/jansky",
  "assets_path": "/home/pi/jansky/assets/face",
  "piper_path": "/usr/local/bin/piper",
  "piper_voice": "/home/pi/piper/voices/en_US-lessac-medium.onnx",
  "whisper_path": "/home/pi/whisper.cpp/main",
  "whisper_model": "/home/pi/whisper.cpp/models/ggml-base.en.bin",
  "chat_model": "qwen2.5:1.5b",
  "wake_word_model": "/home/pi/jansky/models/wake_word/hey_jansky.tflite",
  "wake_word_threshold": 0.5,
  "local_soul_path": "/home/pi/jansky/config/local_soul.md",
  "cloud_soul_path": "/home/pi/jansky/config/cloud_soul.md",
  "display_width": 800,
  "display_height": 480,
  "enable_streaming_tts": false
}
```

---

## 9. API Contracts

### 9.1 Ollama Chat API

```json
// Request
POST http://localhost:11434/api/chat
{
  "model": "qwen2.5:1.5b",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "What time is it?"}
  ],
  "tools": [...],
  "stream": false
}

// Response (with tool call)
{
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {
        "function": {
          "name": "get_current_time",
          "arguments": {}
        }
      }
    ]
  }
}

// Response (direct chat)
{
  "message": {
    "role": "assistant",
    "content": "Hello! How can I help you today?"
  }
}
```

### 9.2 OpenWeatherMap API

```json
// Request
GET https://api.openweathermap.org/data/2.5/weather?q=London&appid=KEY&units=metric

// Response
{
  "name": "London",
  "main": {
    "temp": 15.5,
    "feels_like": 14.2,
    "humidity": 72
  },
  "weather": [
    {"description": "light rain"}
  ]
}
```

### 9.3 Kimi/Moonshot API

```json
// Request
POST https://api.moonshot.cn/v1/chat/completions
Headers: Authorization: Bearer <API_KEY>
{
  "model": "moonshot-v1-8k",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "Write a poem about stars"}
  ],
  "temperature": 0.7,
  "stream": true
}

// Streaming Response
data: {"choices": [{"delta": {"content": "The "}}]}
data: {"choices": [{"delta": {"content": "stars"}}]}
...
data: [DONE]
```

---

## 10. Testing Criteria

### 10.1 Phase 1 Tests (Audio)

```markdown
□ TTS synthesizes text and plays audio clearly
□ STT transcribes speech with <15% WER on clear speech
□ Audio muting works during TTS playback
□ Silence detection stops recording appropriately
□ Round-trip (speak → transcribe → speak) works
```

### 10.2 Phase 2 Tests (Brain)

```markdown
□ Ollama responds within 5 seconds for simple queries
□ Tool calling works for time queries
□ Tool calling works for weather queries
□ Cloud handoff triggers for complex queries
□ Direct chat works for simple greetings
□ Conversation history maintains context
```

### 10.3 Phase 3 Tests (Senses)

```markdown
□ Wake word detects "Hey Jansky" reliably (>90% true positive)
□ Wake word false positive rate <1 per hour
```

### 10.4 Phase 4 Tests (UI)

```markdown
□ UI renders on framebuffer without X server
□ State transitions are smooth (no flicker)
□ IDLE animation runs at stable 30fps
□ LISTENING responds to audio amplitude
□ THINKING shows activity indicator
□ SPEAKING animates with TTS audio
```

### 10.5 Phase 5 Tests (Integration)

```markdown
□ Full flow: wake word → listen → process → respond
□ System recovers from errors gracefully
□ Memory usage stays under 6GB during normal operation
□ System runs stable for 1 hour continuous use
□ Auto-start works via systemd service
```

---

## 11. Known Risks & Mitigations

### 11.1 Audio Feedback Loop

**Risk:** Microphone picks up speaker output.

**Mitigation:**
- Implement strict mute flag during TTS playback
- Use `AudioManager.mute()` before any audio output
- Add 200ms buffer after playback before unmuting

### 11.2 RAM Saturation

**Risk:** System exceeds 8GB during heavy use.

**Mitigation:**
- Monitor memory with `psutil` and abort if >7GB
- Keep Whisper as subprocess (loads on-demand, not resident)
- Only one model loaded in Ollama at a time

### 11.3 Router Hallucination

**Risk:** Small LLM fails to output correct tool calls.

**Mitigation:**
- Use Ollama structured outputs (GBNF grammar)
- Provide clear tool descriptions
- Add fallback: if response not parseable, treat as direct chat

### 11.4 Wake Word False Positives

**Risk:** Random speech triggers wake word.

**Mitigation:**
- Train model with diverse negative samples
- Use threshold tuning (start at 0.5, adjust based on testing)
- Add user verification feature if needed

### 11.5 Network Failures

**Risk:** Cloud API or weather API unavailable.

**Mitigation:**
- Timeout all network requests (10s for weather, 60s for cloud)
- Graceful fallback messages ("I can't reach the cloud right now")
- Cache recent weather data (optional)

### 11.6 Thermal Throttling

**Risk:** Pi overheats during sustained inference.

**Mitigation:**
- **Required:** Active cooling (fan + heatsink)
- Monitor temperature via `vcgencmd measure_temp`
- Reduce workload if temp > 80°C

---

## Appendix A: Quick Start Commands

```bash
# Clone and setup (run as pi user)
cd /home/pi
git clone <repo-url> jansky
cd jansky

# Run install scripts
chmod +x scripts/*.sh
./scripts/install_system_deps.sh
./scripts/setup_python_env.sh
./scripts/install_ollama.sh
./scripts/install_whisper.sh
./scripts/install_piper.sh

# Configure API keys
cp .env.example .env
nano .env  # Add your API keys

# Test components
source venv/bin/activate
python tests/test_audio_pipeline.py
python tests/test_router.py

# Run the assistant
python orchestrator.py

# Or install as service
sudo cp scripts/jansky.service /etc/systemd/system/
sudo systemctl enable jansky
sudo systemctl start jansky
```

---

## Appendix B: Troubleshooting

### No audio output
```bash
# Check audio devices
aplay -l
# Set default device
sudo raspi-config  # Advanced > Audio
```

### Ollama not responding
```bash
# Check service
sudo systemctl status ollama
# Restart
sudo systemctl restart ollama
# Check logs
journalctl -u ollama -f
```

### PyGame framebuffer error
```bash
# Ensure no X server running
sudo systemctl stop lightdm
# Check framebuffer
ls /dev/fb0
# Test with simple script
SDL_VIDEODRIVER=fbcon python3 -c "import pygame; pygame.init(); print('OK')"
```

### Wake word not detecting
```bash
# Test microphone
arecord -d 3 test.wav
aplay test.wav
# Check model path
ls /home/pi/jansky/models/wake_word/
```

---

**END OF PRD**

*This document provides complete context for an AI agent to implement the Jansky voice assistant. Work through phases sequentially, running tests after each phase before proceeding.*