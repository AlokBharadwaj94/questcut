"""Starts QuestCut. The first time, it makes a private Python environment
(.venv next to this file) and installs what QuestCut needs. That takes a few
minutes once; after that it starts straight away.

Usage:  python run_questcut.py            (normal)
        python run_questcut.py --gpu      (also install NVIDIA GPU support, for the lab Linux PC)
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, ".venv")
PY = os.path.join(VENV, "Scripts", "python.exe") if os.name == "nt" else os.path.join(VENV, "bin", "python")
STAMP = os.path.join(VENV, ".installed")


def sh(cmd):
    print(">", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def ensure_env(gpu=False):
    if sys.version_info < (3, 9):
        sys.exit("QuestCut needs Python 3.9 or newer. Get it from https://www.python.org/downloads/")
    if not os.path.exists(PY):
        print("First start: setting up QuestCut (one time only, a few minutes)…", flush=True)
        sh([sys.executable, "-m", "venv", VENV])
    if not os.path.exists(STAMP):
        sh([PY, "-m", "pip", "install", "--upgrade", "pip"])
        sh([PY, "-m", "pip", "install", "-r", os.path.join(HERE, "requirements.txt")])
        open(STAMP, "w").write("ok")
    if gpu:
        # CuPy for CUDA 12 (most current NVIDIA drivers). Use cupy-cuda11x for older CUDA 11 drivers.
        sh([PY, "-m", "pip", "install", "cupy-cuda12x"])


if __name__ == "__main__":
    gpu = "--gpu" in sys.argv
    ensure_env(gpu)
    args = [a for a in sys.argv[1:] if a != "--gpu"]
    os.chdir(HERE)
    sys.exit(subprocess.call([PY, "-m", "questcut"] + args))
