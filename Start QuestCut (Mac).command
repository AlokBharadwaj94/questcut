#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is missing. Install it from https://www.python.org/downloads/ and double-click this file again."
  read -p "Press Enter to close."
  exit 1
fi
python3 run_questcut.py "$@" || read -p "Something went wrong (see above). Press Enter to close."
