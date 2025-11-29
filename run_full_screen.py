# !/usr/bin/env python3
"""
Fullscreen launcher for Dropout Control GUI
Optimized for dedicated 7" touchscreen displays
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# Import the main GUI class
# Make sure dropout_gui.py is in the same directory or Python path
from main import TouchControlGUI


def main():
    app = QApplication(sys.argv)

    # Configure for touchscreen
    app.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)

    # Create main window
    window = TouchControlGUI()

    # Check for fullscreen argument
    if '--fullscreen' in sys.argv or '-f' in sys.argv:
        window.showFullScreen()
        # Hide mouse cursor for dedicated kiosk mode
        if '--hide-cursor' in sys.argv:
            app.setOverrideCursor(Qt.BlankCursor)
    else:
        window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()