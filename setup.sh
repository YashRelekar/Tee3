#!/usr/bin/env bash
# ==============================================================
#  T3 — Pi 4B Edition: One-Command Installer
#  Target: Raspberry Pi 4B · Raspberry Pi OS Bookworm 64-bit
# ==============================================================
#  Usage:  chmod +x setup.sh && ./setup.sh
#
#  What this script does (in order):
#   1. Installs system packages (apt)
#   2. Creates a Python 3 virtual environment  (venv)
#   3. Installs Python dependencies (pip)
#   4. Installs Ollama and pulls qwen2.5:4b  (~2.5 GB quantised)
#   5. Builds Whisper.cpp from source and downloads the model
#   6. Downloads the Piper TTS voice
#   7. Reminds you to add API keys
#
#  Pi 4B Notes
#  -----------
#  • qwen2.5:4b is used instead of the upstream 1.5b.  It fits in
#    the 4 GB RAM with room for the OS and audio pipeline.
#  • Ollama is configured with conservative defaults:
#      num_thread=4  num_ctx=2048  num_predict=256
#    These are read from config/config.json at runtime.
#  • Pi OS Bookworm ships Python 3.11 — no need to build 3.13.
#  • Cloud fallback (Kimi / Moonshot) is optional; add
#    MOONSHOT_API_KEY to .env to enable it.
# ==============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── colours ───────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${YELLOW}[→]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Guard: must run on a Pi 4B (ARM 64-bit) ──────────────────
ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" ]]; then
  echo -e "${YELLOW}[!]${NC} This installer targets aarch64 (Pi 4B / Pi OS 64-bit)."
  echo "    Detected: $ARCH — proceed anyway? [y/N]"
  read -r ans
  [[ "$ans" =~ ^[Yy]$ ]] || fail "Aborting."
fi

# ── 1. System packages ───────────────────────────────────────
info "Installing system packages …"
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-dev python3-pip \
  build-essential cmake git curl wget \
  libsdl2-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  portaudio19-dev libasound2-dev \
  alsa-utils
ok "System packages installed"

# ── 2. Python virtual environment ────────────────────────────
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
  info "Creating Python virtual environment …"
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
ok "Virtual environment ready ($VENV_DIR)"

# ── 3. Python dependencies ───────────────────────────────────
info "Installing Python packages …"
pip install -q \
  httpx \
  sounddevice \
  numpy \
  piper-tts \
  openwakeword \
  onnxruntime \
  pygame
ok "Python packages installed"

# ── 4. Ollama + model ────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
  info "Installing Ollama …"
  curl -fsSL https://ollama.com/install.sh | sh
fi
ok "Ollama installed"

# Pull the primary 4 GB class model (qwen2.5:4b ≈ 2.5 GB on disk)
# Override by setting CHAT_MODEL env var before running this script,
# or by changing "chat_model" in config/config.json after install.
CHAT_MODEL="${CHAT_MODEL:-qwen2.5:4b}"
info "Pulling ${CHAT_MODEL} (this may take 10–20 minutes on a Pi 4B) …"
ollama pull "${CHAT_MODEL}"
ok "${CHAT_MODEL} ready"

# ── 5. Whisper.cpp ───────────────────────────────────────────
if [ ! -f "/usr/local/bin/whisper-cpp" ]; then
  if [ ! -d "whisper.cpp" ]; then
    info "Cloning Whisper.cpp …"
    git clone https://github.com/ggerganov/whisper.cpp.git
  fi
  info "Building Whisper.cpp (4 threads — all Pi 4B cores) …"
  cd whisper.cpp
  cmake -B build
  cmake --build build --config Release -j4
  sudo cp build/bin/whisper-cli /usr/local/bin/whisper-cpp
  ok "Whisper.cpp built and installed to /usr/local/bin/whisper-cpp"

  info "Downloading Whisper base.en model …"
  bash models/download-ggml-model.sh base.en
  if [ -f build/bin/quantize ]; then
    ./build/bin/quantize models/ggml-base.en.bin models/ggml-base.en-q5_0.bin q5_0
    ok "Whisper model quantised (q5_0)"
  fi
  cd "$SCRIPT_DIR"
else
  ok "Whisper.cpp already installed"
fi

# ── 6. Piper TTS voice ──────────────────────────────────────
VOICE_DIR="piper/voices"
VOICE_FILE="$VOICE_DIR/en_GB-semaine-medium.onnx"
if [ ! -f "$VOICE_FILE" ]; then
  info "Downloading Piper TTS voice …"
  mkdir -p "$VOICE_DIR"
  wget -q -O "$VOICE_FILE" \
    https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx
  wget -q -O "${VOICE_FILE}.json" \
    https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json
  ok "Piper voice downloaded"
else
  ok "Piper voice already present"
fi

# ── 7. config/config.json — patch project_root to actual path ──
CONFIG_FILE="config/config.json"
ACTUAL_ROOT="$SCRIPT_DIR"
if [ -f "$CONFIG_FILE" ]; then
  info "Setting project_root in config/config.json to $ACTUAL_ROOT …"
  python3 - <<PYEOF
import json, sys
with open("$CONFIG_FILE") as f:
    data = json.load(f)
root = "$ACTUAL_ROOT"
data["project_root"]    = root
data["assets_path"]     = root + "/assets/face"
data["piper_voice"]     = root + "/piper/voices/en_GB-semaine-medium.onnx"
data["whisper_model"]   = root + "/whisper.cpp/models/ggml-base.en-q5_0.bin"
data["wake_word_model"] = root + "/models/wake_word/Hey_Jansky.onnx"
data["local_soul_path"] = root + "/config/local_soul.md"
data["cloud_soul_path"] = root + "/config/cloud_soul.md"
with open("$CONFIG_FILE", "w") as f:
    json.dump(data, f, indent=2)
print("config/config.json updated.")
PYEOF
  ok "config/config.json patched"
fi

# ── 8. .env file ─────────────────────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  info "Created .env from template — edit it to add your API keys"
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  T3 (Pi 4B Edition) is installed!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Hardware assumed: Raspberry Pi 4B · Pi OS Bookworm 64-bit"
echo "  Local model:      ${CHAT_MODEL} (change: config/config.json → chat_model)"
echo "  Cloud fallback:   add MOONSHOT_API_KEY to .env"
echo ""
echo "  Next steps:"
echo "    1. (Optional) Add API keys:  nano .env"
echo "    2. Start T3:"
echo "         source venv/bin/activate"
echo "         python orchestrator.py"
echo ""
echo "  Say \"Hey Jansky\" and start talking!"
echo ""
