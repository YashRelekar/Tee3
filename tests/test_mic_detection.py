#!/usr/bin/env python3
"""
Unit tests for the microphone auto-detection logic in audio/audio_manager.py.

These tests mock sounddevice so they run without any audio hardware.
"""

import sys
import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock sounddevice at the module level so the import succeeds in environments
# where PortAudio is not installed (e.g. CI runners without audio hardware).
_sd_mock = MagicMock()
sys.modules.setdefault("sounddevice", _sd_mock)

from audio.audio_manager import _resolve_mic_device, _find_device_by_name


def _make_devices(*specs):
    """Helper: build a list of fake sounddevice device dicts.

    Each *spec* is a (name, max_input_channels, max_output_channels) tuple.
    """
    return [
        {
            "name": name,
            "max_input_channels": ins,
            "max_output_channels": outs,
        }
        for name, ins, outs in specs
    ]


class TestFindDeviceByName(unittest.TestCase):

    def test_finds_matching_input_device(self):
        devices = _make_devices(
            ("USB PnP Sound Device", 1, 0),
            ("bcm2835 Headphones", 0, 2),
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _find_device_by_name("USB PnP", "input")
        self.assertEqual(idx, 0)

    def test_case_insensitive_match(self):
        devices = _make_devices(("respeaker usb audio", 4, 0))
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _find_device_by_name("ReSpeaker", "input")
        self.assertEqual(idx, 0)

    def test_raises_when_not_found(self):
        devices = _make_devices(("bcm2835 Headphones", 0, 2))
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            with self.assertRaises(RuntimeError) as cm:
                _find_device_by_name("USB PnP Sound Device", "input")
        self.assertIn("USB PnP Sound Device", str(cm.exception))

    def test_requires_input_channels(self):
        # Device name matches but is output-only
        devices = _make_devices(("USB PnP Sound Device", 0, 2))
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            with self.assertRaises(RuntimeError):
                _find_device_by_name("USB PnP Sound Device", "input")


class TestResolveMicDevice(unittest.TestCase):

    def setUp(self):
        # Remove any mic-related env vars before each test
        for var in ("MIC_NAME", "AUDIO_INPUT_DEVICE", "DISABLE_AUDIO"):
            os.environ.pop(var, None)

    def tearDown(self):
        for var in ("MIC_NAME", "AUDIO_INPUT_DEVICE", "DISABLE_AUDIO"):
            os.environ.pop(var, None)

    # ------------------------------------------------------------------ #
    # Priority 1: MIC_NAME env var
    # ------------------------------------------------------------------ #

    def test_env_mic_name_wins(self):
        os.environ["MIC_NAME"] = "ReSpeaker"
        devices = _make_devices(
            ("ReSpeaker USB Audio", 4, 0),
            ("bcm2835 Headphones", 0, 2),
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _resolve_mic_device()
        self.assertEqual(idx, 0)

    def test_env_audio_input_device_wins(self):
        os.environ["AUDIO_INPUT_DEVICE"] = "ReSpeaker"
        devices = _make_devices(("ReSpeaker USB Audio", 4, 0))
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _resolve_mic_device()
        self.assertEqual(idx, 0)

    def test_mic_name_env_takes_priority_over_preferred(self):
        os.environ["MIC_NAME"] = "ReSpeaker"
        devices = _make_devices(
            ("ReSpeaker USB Audio", 4, 0),
            ("USB PnP Sound Device", 1, 0),
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            # preferred_name points at device 1, env var should win (device 0)
            idx = _resolve_mic_device(preferred_name="USB PnP Sound Device")
        self.assertEqual(idx, 0)

    # ------------------------------------------------------------------ #
    # Priority 2: preferred_name argument
    # ------------------------------------------------------------------ #

    def test_preferred_name_used_when_no_env(self):
        devices = _make_devices(
            ("HDMI Audio", 0, 2),
            ("USB PnP Sound Device", 1, 0),
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _resolve_mic_device(preferred_name="USB PnP Sound Device")
        self.assertEqual(idx, 1)

    # ------------------------------------------------------------------ #
    # Priority 3: ReSpeaker / XVF3800 / seeed auto-detection
    # ------------------------------------------------------------------ #

    def test_respeaker_autodetect(self):
        devices = _make_devices(
            ("vc4-hdmi-0", 0, 2),
            ("ReSpeaker 4-Mic Array (UAC1.0)", 4, 0),
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _resolve_mic_device()
        self.assertEqual(idx, 1)

    def test_xvf3800_autodetect(self):
        devices = _make_devices(
            ("bcm2835 Headphones", 0, 8),
            ("XVF3800 USB Audio", 4, 0),
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _resolve_mic_device()
        self.assertEqual(idx, 1)

    def test_seeed_autodetect(self):
        devices = _make_devices(("seeed-2mic-voicecard", 2, 0))
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _resolve_mic_device()
        self.assertEqual(idx, 0)

    # ------------------------------------------------------------------ #
    # Priority 4: legacy "USB PnP Sound Device" backward-compat
    # ------------------------------------------------------------------ #

    def test_usb_pnp_fallback(self):
        devices = _make_devices(
            ("bcm2835 Headphones", 0, 2),
            ("USB PnP Sound Device", 1, 0),
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _resolve_mic_device()
        self.assertEqual(idx, 1)

    # ------------------------------------------------------------------ #
    # Priority 5: any USB input device
    # ------------------------------------------------------------------ #

    def test_generic_usb_fallback(self):
        devices = _make_devices(
            ("bcm2835 Headphones", 0, 2),
            ("USB Audio Device", 1, 0),
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            idx = _resolve_mic_device()
        self.assertEqual(idx, 1)

    # ------------------------------------------------------------------ #
    # Error cases
    # ------------------------------------------------------------------ #

    def test_raises_when_no_input_devices(self):
        devices = _make_devices(
            ("vc4-hdmi-0 MAI PCM", 0, 2),
            ("bcm2835 Headphones", 0, 8),
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_mic_device()
        self.assertIn("No audio input devices found", str(cm.exception))
        self.assertIn("DISABLE_AUDIO", str(cm.exception))

    def test_raises_with_guidance_when_no_usb_input(self):
        devices = _make_devices(
            ("bcm2835 Headphones", 0, 2),
            ("sysdefault (input)", 1, 0),  # non-USB input device
        )
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_mic_device()
        msg = str(cm.exception)
        self.assertIn("MIC_NAME", msg)
        self.assertIn("DISABLE_AUDIO", msg)

    def test_env_mic_name_not_found_raises_with_name(self):
        os.environ["MIC_NAME"] = "MyNonExistentMic"
        devices = _make_devices(("USB PnP Sound Device", 1, 0))
        with patch("audio.audio_manager.sd.query_devices", return_value=devices):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_mic_device()
        self.assertIn("MyNonExistentMic", str(cm.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
