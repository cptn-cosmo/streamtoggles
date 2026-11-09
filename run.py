#!/usr/bin/env python3
"""Launcher script for StreamToggles."""

import os
import sys

# Ensure streamtoggles package is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from streamtoggles.main import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
