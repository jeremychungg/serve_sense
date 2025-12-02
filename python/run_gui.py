#!/usr/bin/env python3
"""
Launcher script for Serve Sense GUI.

This script can be run from anywhere in the repository.
"""

import sys
from pathlib import Path

# Add the gui directory to the path
gui_dir = Path(__file__).parent / "gui"
sys.path.insert(0, str(gui_dir.parent))

# Import and run the GUI
from gui.serve_sense_gui import main

if __name__ == "__main__":
    main()
