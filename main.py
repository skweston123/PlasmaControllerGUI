#!/usr/bin/env python3
"""
Arduino Dropout System Control GUI - Optimized for 7" Touch Display
Designed for 800x480 horizontal touchscreen
"""

import sys
import serial
import serial.tools.list_ports
import json
import time
import queue
import threading
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QPushButton, QLabel,
                             QComboBox, QFrame, QScrollArea, QSizePolicy, QMessageBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QPalette, QColor, QKeySequence


@dataclass
class DropoutStatus:
    """Status information for a single dropout fixture"""
    state: str = "UNKNOWN"
    arm_state: str = "UNKNOWN"
    clamp_state: str = "UNKNOWN"


@dataclass
class SystemStatus:
    """Overall system status"""
    estop_active: bool = False
    auto_mode: bool = True
    plasma_on: bool = False
    plasma_ok: bool = False
    fanuc_check: bool = False
    dropouts: list = None

    def __post_init__(self):
        if self.dropouts is None:
            self.dropouts = [DropoutStatus() for _ in range(4)]


class SerialInterface(QObject):
    """Handles serial communication with Arduino"""
    status_received = pyqtSignal(dict)

    def __init__(self, port: str = None, baudrate: int = 9600):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_conn: Optional[serial.Serial] = None
        self.connected = False
        self.read_thread: Optional[threading.Thread] = None
        self.running = False

    def connect(self) -> bool:
        """Connect to the Arduino"""
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)
            self.connected = True
            self.running = True
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from Arduino"""
        self.running = False
        if self.read_thread:
            self.read_thread.join(timeout=2)
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.connected = False

    def send_command(self, command: str):
        """Send a command to the Arduino"""
        if self.connected and self.serial_conn:
            try:
                self.serial_conn.write(f"{command}\n".encode())
                self.serial_conn.flush()
            except Exception as e:
                print(f"Send error: {e}")

    def _read_loop(self):
        """Background thread to read status updates from Arduino"""
        while self.running and self.serial_conn:
            try:
                if self.serial_conn.in_waiting:
                    line = self.serial_conn.readline().decode().strip()
                    if line.startswith("STATUS:"):
                        try:
                            status_json = line[7:]
                            status_data = json.loads(status_json)
                            self.status_received.emit(status_data)
                        except json.JSONDecodeError:
                            pass
                time.sleep(0.05)
            except Exception as e:
                print(f"Read error: {e}")
                break

    @staticmethod
    def list_ports():
        """List available serial ports"""
        return [port.device for port in serial.tools.list_ports.comports()]


class TouchButton(QPushButton):
    """Large touch-friendly button"""

    def __init__(self, text, parent=None, height=60):
        super().__init__(text, parent)
        self.setMinimumHeight(height)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.setFont(font)


class StatusLabel(QLabel):
    """Status label with styling"""

    def __init__(self, text="", bold=False, size=12):
        super().__init__(text)
        font = QFont()
        font.setPointSize(size)
        if bold:
            font.setBold(True)
        self.setFont(font)
        self.setAlignment(Qt.AlignCenter)


class DropoutWidget(QFrame):
    """Compact widget for a single dropout fixture"""

    def __init__(self, dropout_num: int, serial_interface: SerialInterface):
        super().__init__()
        self.dropout_num = dropout_num
        self.serial = serial_interface

        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(2)

        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header
        header = StatusLabel(f"Dropout {dropout_num}", bold=True, size=14)
        layout.addWidget(header)

        # State display - larger font
        self.state_label = StatusLabel("UNKNOWN", bold=True, size=13)
        layout.addWidget(self.state_label)

        # Arm/Clamp status - larger fonts
        status_layout = QHBoxLayout()
        status_layout.setSpacing(5)

        arm_container = QVBoxLayout()
        arm_container.setSpacing(2)
        arm_label = QLabel("ARM")
        arm_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        arm_label.setFont(font)
        self.arm_value = StatusLabel("?", size=12)
        self.arm_value.setMinimumHeight(30)
        arm_container.addWidget(arm_label)
        arm_container.addWidget(self.arm_value)

        clamp_container = QVBoxLayout()
        clamp_container.setSpacing(2)
        clamp_label = QLabel("CLAMP")
        clamp_label.setAlignment(Qt.AlignCenter)
        clamp_label.setFont(font)
        self.clamp_value = StatusLabel("?", size=12)
        self.clamp_value.setMinimumHeight(30)
        clamp_container.addWidget(clamp_label)
        clamp_container.addWidget(self.clamp_value)

        status_layout.addLayout(arm_container)
        status_layout.addLayout(clamp_container)
        layout.addLayout(status_layout)

        # Control buttons - taller
        btn_up = TouchButton("UP", height=50)
        btn_up.clicked.connect(self.cmd_up)
        layout.addWidget(btn_up)

        btn_load = TouchButton("LOAD", height=50)
        btn_load.clicked.connect(self.cmd_load)
        layout.addWidget(btn_load)

        btn_down = TouchButton("DOWN", height=50)
        btn_down.clicked.connect(self.cmd_down)
        layout.addWidget(btn_down)

        layout.addStretch()
        self.setLayout(layout)

    def cmd_up(self):
        self.serial.send_command(f"{self.dropout_num}_up")

    def cmd_load(self):
        self.serial.send_command(f"{self.dropout_num}_load")

    def cmd_down(self):
        self.serial.send_command(f"{self.dropout_num}_down")

    def update_status(self, status: DropoutStatus):
        """Update display with new status"""
        self.state_label.setText(status.state)

        # Show full text, not abbreviated
        self.arm_value.setText(status.arm_state)
        self.clamp_value.setText(status.clamp_state)

        # Color code the state
        if "IDLE" in status.state:
            color = "green"
        elif "ERROR" in status.state or status.state == "NONE":
            color = "red"
        else:
            color = "orange"

        self.state_label.setStyleSheet(f"color: {color};")


class TouchControlGUI(QMainWindow):
    """Main GUI optimized for 7-inch touchscreen"""

    def __init__(self):
        super().__init__()
        self.serial = SerialInterface()
        self.system_status = SystemStatus()

        self.setWindowTitle("Dropout Control")
        self.setGeometry(0, 0, 800, 480)

        # Track fullscreen state
        self.is_fullscreen = False

        # Set dark theme for better visibility
        self.set_dark_theme()

        self.setup_ui()

        # Connect serial signal
        self.serial.status_received.connect(self.process_status)

        # Auto-request status
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.request_status)
        self.status_timer.start(2000)  # Request every 2 seconds as backup

    def set_dark_theme(self):
        """Apply dark theme for better contrast"""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(35, 35, 35))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Highlight, QColor(142, 45, 197))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        self.setPalette(palette)

        # Button styling
        self.setStyleSheet("""
            QPushButton {
                background-color: #454545;
                border: 2px solid #666;
                border-radius: 5px;
                padding: 5px;
                color: white;
            }
            QPushButton:pressed {
                background-color: #666;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
            QFrame {
                background-color: #3a3a3a;
                border-radius: 5px;
            }
            QComboBox {
                background-color: #454545;
                border: 2px solid #666;
                padding: 5px;
                min-height: 40px;
                font-size: 11pt;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 6px solid white;
                margin-right: 10px;
            }
        """)

    def setup_ui(self):
        """Create the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # === Top Bar: Connection and Status ===
        top_bar = QHBoxLayout()
        top_bar.setSpacing(5)

        # Connection controls (left side)
        conn_widget = QFrame()
        conn_layout = QHBoxLayout()
        conn_layout.setContentsMargins(5, 5, 5, 5)

        self.port_combo = QComboBox()
        self.port_combo.addItems(SerialInterface.list_ports())
        self.port_combo.setMinimumWidth(150)
        self.port_combo.setMinimumHeight(50)
        conn_layout.addWidget(self.port_combo)

        refresh_btn = TouchButton("↻", height=50)
        refresh_btn.setMaximumWidth(60)
        refresh_btn.clicked.connect(self.refresh_ports)
        conn_layout.addWidget(refresh_btn)

        self.connect_btn = TouchButton("Connect", height=50)
        self.connect_btn.setMinimumWidth(120)
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_btn)

        conn_widget.setLayout(conn_layout)
        top_bar.addWidget(conn_widget)

        # System status display (center)
        status_widget = QFrame()
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(10, 5, 10, 5)
        status_layout.setSpacing(3)

        self.estop_label = StatusLabel("● E-STOP", bold=True, size=14)
        self.estop_label.setStyleSheet("color: red;")
        status_layout.addWidget(self.estop_label)

        bottom_status = QHBoxLayout()
        bottom_status.setSpacing(15)

        self.mode_label = StatusLabel("AUTO", bold=True, size=12)
        bottom_status.addWidget(self.mode_label)

        plasma_container = QHBoxLayout()
        plasma_container.setSpacing(5)
        plasma_label = QLabel("Plasma:")
        plasma_font = QFont("Arial", 11)
        plasma_font.setBold(True)
        plasma_label.setFont(plasma_font)
        self.plasma_indicator = StatusLabel("●", size=14)
        plasma_container.addWidget(plasma_label)
        plasma_container.addWidget(self.plasma_indicator)
        bottom_status.addLayout(plasma_container)

        status_layout.addLayout(bottom_status)
        status_widget.setLayout(status_layout)
        status_widget.setMaximumWidth(220)
        top_bar.addWidget(status_widget)

        # Mode and E-Stop buttons (right side)
        control_widget = QFrame()
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(5)

        mode_btn = TouchButton("AUTO/\nMANUAL", height=50)
        mode_btn.clicked.connect(self.toggle_mode)
        control_layout.addWidget(mode_btn)

        estop_btn = TouchButton("E-STOP", height=50)
        estop_btn.setStyleSheet("""
            QPushButton {
                background-color: #8B0000;
                font-size: 16pt;
                font-weight: bold;
            }
            QPushButton:pressed {
                background-color: #FF0000;
            }
        """)
        estop_btn.clicked.connect(self.trigger_estop)
        control_layout.addWidget(estop_btn)

        reset_btn = TouchButton("RESET", height=50)
        reset_btn.setStyleSheet("background-color: #006400; font-size: 14pt;")
        reset_btn.clicked.connect(self.reset_estop)
        control_layout.addWidget(reset_btn)

        # Exit button (small, in corner)
        exit_btn = QPushButton("✕")
        exit_btn.setMaximumWidth(50)
        exit_btn.setMinimumHeight(50)
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #888;
                font-size: 18pt;
                border: 1px solid #555;
            }
            QPushButton:pressed {
                background-color: #444;
            }
        """)
        exit_btn.clicked.connect(self.confirm_exit)
        control_layout.addWidget(exit_btn)

        control_widget.setLayout(control_layout)
        top_bar.addWidget(control_widget)

        main_layout.addLayout(top_bar)

        # === Middle Section: Dropouts and Plasma Control ===
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(5)

        # Dropout fixtures
        self.dropout_widgets = []
        for i in range(4):
            dropout = DropoutWidget(i + 1, self.serial)
            middle_layout.addWidget(dropout)
            self.dropout_widgets.append(dropout)

        # Plasma control panel
        plasma_panel = QFrame()
        plasma_layout = QVBoxLayout()
        plasma_layout.setContentsMargins(8, 8, 8, 8)
        plasma_layout.setSpacing(8)

        plasma_header = StatusLabel("PLASMA", bold=True, size=14)
        plasma_layout.addWidget(plasma_header)

        plasma_on_btn = TouchButton("ON", height=80)
        plasma_on_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5016;
                font-size: 16pt;
            }
            QPushButton:pressed {
                background-color: #3d7020;
            }
        """)
        plasma_on_btn.clicked.connect(self.plasma_on)
        plasma_layout.addWidget(plasma_on_btn)

        plasma_off_btn = TouchButton("OFF", height=80)
        plasma_off_btn.setStyleSheet("""
            QPushButton {
                background-color: #501616;
                font-size: 16pt;
            }
            QPushButton:pressed {
                background-color: #702020;
            }
        """)
        plasma_off_btn.clicked.connect(self.plasma_off)
        plasma_layout.addWidget(plasma_off_btn)

        plasma_layout.addStretch()
        plasma_panel.setLayout(plasma_layout)
        plasma_panel.setMaximumWidth(140)
        middle_layout.addWidget(plasma_panel)

        main_layout.addLayout(middle_layout, stretch=1)

        central_widget.setLayout(main_layout)

    def refresh_ports(self):
        """Refresh serial port list"""
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = SerialInterface.list_ports()
        self.port_combo.addItems(ports)

        if current in ports:
            self.port_combo.setCurrentText(current)

    def toggle_connection(self):
        """Connect or disconnect"""
        if not self.serial.connected:
            port = self.port_combo.currentText()
            if not port:
                return

            self.serial.port = port
            if self.serial.connect():
                self.connect_btn.setText("Disconnect")
                self.connect_btn.setStyleSheet("background-color: #006400;")
                self.request_status()
        else:
            self.serial.disconnect()
            self.connect_btn.setText("Connect")
            self.connect_btn.setStyleSheet("")

    def toggle_mode(self):
        """Toggle between AUTO and MANUAL mode"""
        if self.system_status.auto_mode:
            self.serial.send_command("manual")
        else:
            self.serial.send_command("auto")

    def trigger_estop(self):
        """Trigger emergency stop"""
        self.serial.send_command("estop")

    def reset_estop(self):
        """Reset emergency stop"""
        self.serial.send_command("reset")

    def plasma_on(self):
        """Turn plasma on"""
        self.serial.send_command("plasma_on")

    def plasma_off(self):
        """Turn plasma off"""
        self.serial.send_command("plasma_off")

    def request_status(self):
        """Request status update"""
        if self.serial.connected:
            self.serial.send_command("getstatus")

    def confirm_exit(self):
        """Confirm before exiting"""
        reply = QMessageBox.question(
            self,
            'Exit Application',
            'Are you sure you want to exit?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.close()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        # ESC key to exit fullscreen or close
        if event.key() == Qt.Key_Escape:
            if self.is_fullscreen:
                self.showNormal()
                self.is_fullscreen = False
            else:
                self.confirm_exit()

        # F11 to toggle fullscreen
        elif event.key() == Qt.Key_F11:
            if self.is_fullscreen:
                self.showNormal()
                self.is_fullscreen = False
            else:
                self.showFullScreen()
                self.is_fullscreen = True

        # Ctrl+Q to quit
        elif event.key() == Qt.Key_Q and event.modifiers() == Qt.ControlModifier:
            self.confirm_exit()

        else:
            super().keyPressEvent(event)

    def process_status(self, data: dict):
        """Process status update from Arduino"""
        try:
            # E-Stop
            if 'estop' in data:
                self.system_status.estop_active = data['estop']
                if data['estop']:
                    self.estop_label.setText("● E-STOP")
                    self.estop_label.setStyleSheet("color: red;")
                else:
                    self.estop_label.setText("✓ CLEAR")
                    self.estop_label.setStyleSheet("color: green;")

            # Mode
            if 'auto_mode' in data:
                self.system_status.auto_mode = data['auto_mode']
                if data['auto_mode']:
                    self.mode_label.setText("AUTO")
                    self.mode_label.setStyleSheet("color: cyan;")
                else:
                    self.mode_label.setText("MANUAL")
                    self.mode_label.setStyleSheet("color: yellow;")

            # Plasma
            if 'plasma_on' in data:
                if data['plasma_on']:
                    self.plasma_indicator.setText("●")
                    self.plasma_indicator.setStyleSheet("color: lime;")
                else:
                    self.plasma_indicator.setText("○")
                    self.plasma_indicator.setStyleSheet("color: gray;")

            # Dropouts
            if 'dropouts' in data:
                for i, dropout_data in enumerate(data['dropouts']):
                    if i < 4:
                        status = DropoutStatus(
                            state=dropout_data.get('state', 'UNKNOWN'),
                            arm_state=dropout_data.get('arm', 'UNKNOWN'),
                            clamp_state=dropout_data.get('clamp', 'UNKNOWN')
                        )
                        self.dropout_widgets[i].update_status(status)

        except Exception as e:
            print(f"Error processing status: {e}")

    def closeEvent(self, event):
        """Clean up on close"""
        if self.serial.connected:
            self.serial.disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)

    # Configure for touchscreen
    app.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)

    window = TouchControlGUI()

    # Check for fullscreen argument
    if '--fullscreen' in sys.argv or '-f' in sys.argv:
        window.showFullScreen()
        window.is_fullscreen = True
        # Hide cursor for kiosk mode
        if '--hide-cursor' in sys.argv:
            app.setOverrideCursor(Qt.BlankCursor)
    else:
        window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()