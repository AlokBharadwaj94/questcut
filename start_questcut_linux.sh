#!/bin/bash
# Start QuestCut on Linux. Add --gpu the first time on the lab PC to enable NVIDIA GPU filters:
#   ./start_questcut_linux.sh --gpu
cd "$(dirname "$0")"
python3 run_questcut.py "$@"
