"""Hardware detection: which GPU / video encoders this computer can use.

CPU path : numpy + OpenCV (always available)
GPU path : CuPy (NVIDIA, optional) for filter maths during export,
           plus hardware video encoders (NVIDIA NVENC, Apple VideoToolbox,
           Intel QuickSync, AMD AMF) through ffmpeg.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field

import numpy as np

_FFMPEG = None


def ffmpeg_exe() -> str:
    """System ffmpeg if installed (usually has GPU encoders), else the copy
    that ships with the imageio-ffmpeg pip package."""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    exe = shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            exe = "ffmpeg"
    _FFMPEG = exe
    return exe


def run_quiet(args, timeout=20):
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, **kw)


ENCODER_LABELS = {
    "h264_nvenc": "NVIDIA GPU (NVENC)",
    "h264_videotoolbox": "Apple hardware (VideoToolbox)",
    "h264_qsv": "Intel QuickSync",
    "h264_amf": "AMD GPU (AMF)",
    "libx264": "CPU (x264)",
}


@dataclass
class HardwareInfo:
    os_name: str = platform.system()
    cpu_cores: int = os.cpu_count() or 1
    gpu_name: str = ""
    cupy_ok: bool = False
    encoders: list = field(default_factory=lambda: ["libx264"])
    checked: bool = False

    @property
    def best_encoder(self) -> str:
        for e in ("h264_nvenc", "h264_videotoolbox", "h264_qsv", "h264_amf"):
            if e in self.encoders:
                return e
        return "libx264"

    @property
    def has_gpu_encoder(self) -> bool:
        return self.best_encoder != "libx264"

    def summary(self) -> str:
        if not self.checked:
            return "Checking hardware…"
        parts = []
        if self.gpu_name:
            parts.append(f"GPU: {self.gpu_name}")
        else:
            parts.append("GPU: none found (CPU mode)")
        parts.append("Export encoder: " + ENCODER_LABELS.get(self.best_encoder, self.best_encoder))
        parts.append("GPU filters: " + ("on (CuPy)" if self.cupy_ok else "off"))
        return "   |   ".join(parts)


HW = HardwareInfo()
_lock = threading.Lock()


def _test_encoder(enc: str) -> bool:
    try:
        r = run_quiet([ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                       "-f", "lavfi", "-i", "color=c=black:s=256x144:d=0.2",
                       "-frames:v", "3", "-c:v", enc, "-f", "null", "-"], timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def detect_hardware() -> HardwareInfo:
    """Slow-ish (1-3 s). Run in a background thread."""
    with _lock:
        if HW.checked:
            return HW
        # NVIDIA name
        smi = shutil.which("nvidia-smi")
        if smi:
            try:
                r = run_quiet([smi, "--query-gpu=name", "--format=csv,noheader"], timeout=5)
                if r.returncode == 0:
                    HW.gpu_name = r.stdout.decode(errors="ignore").strip().splitlines()[0]
            except Exception:
                pass
        if sys.platform == "darwin":
            HW.gpu_name = HW.gpu_name or "Apple GPU"
        # CuPy for GPU filters
        try:
            import cupy  # noqa: F401
            if cupy.cuda.runtime.getDeviceCount() > 0:
                _ = cupy.zeros(4) + 1
                HW.cupy_ok = True
        except Exception:
            HW.cupy_ok = False
        # hardware encoders that actually work on this machine
        try:
            r = run_quiet([ffmpeg_exe(), "-hide_banner", "-encoders"], timeout=10)
            listed = r.stdout.decode(errors="ignore")
        except Exception:
            listed = ""
        encs = []
        candidates = ["h264_nvenc", "h264_qsv", "h264_amf"]
        if sys.platform == "darwin":
            candidates = ["h264_videotoolbox"]
        for e in candidates:
            if e in listed and _test_encoder(e):
                encs.append(e)
        encs.append("libx264")
        HW.encoders = encs
        if not HW.gpu_name and any(e in encs for e in ("h264_qsv", "h264_amf")):
            HW.gpu_name = "Integrated GPU"
        HW.checked = True
        return HW


# ---------------------------------------------------------------- sound devices
AUDIO = {"checked": False, "outputs": 0, "inputs": 0}

_AUDIO_PROBE = (
    "from PySide6.QtCore import QCoreApplication\n"
    "app = QCoreApplication([])\n"
    "from PySide6.QtMultimedia import QMediaDevices\n"
    "print(len(QMediaDevices.audioOutputs()), len(QMediaDevices.audioInputs()))\n"
)


def probe_audio_devices():
    """Asks Qt for sound devices in a separate process, because on some Linux
    machines without a sound system Qt crashes when asked."""
    if AUDIO["checked"]:
        return AUDIO
    try:
        r = run_quiet([sys.executable, "-c", _AUDIO_PROBE], timeout=20)
        if r.returncode == 0:
            o, i = r.stdout.decode().strip().split()[-2:]
            AUDIO["outputs"], AUDIO["inputs"] = int(o), int(i)
    except Exception:
        pass
    AUDIO["checked"] = True
    return AUDIO


# ---------------------------------------------------------------- array backend
class ArrayBackend:
    """Tiny wrapper so filter code can run on numpy (CPU) or CuPy (GPU)."""

    def __init__(self, use_gpu: bool = False):
        self.is_gpu = False
        self.xp = np
        if use_gpu:
            try:
                import cupy
                self.xp = cupy
                self.is_gpu = True
            except Exception:
                self.is_gpu = False

    def asarray(self, a):
        return self.xp.asarray(a)

    def to_numpy(self, a):
        if self.is_gpu:
            return self.xp.asnumpy(a)
        return a

    @property
    def name(self):
        return "GPU (CuPy)" if self.is_gpu else "CPU (numpy)"


CPU = ArrayBackend(False)
