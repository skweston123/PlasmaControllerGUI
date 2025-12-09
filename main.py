#!/usr/bin/env python3
"""
Plasma Treatment System HMI
PyQt5 interface for Arduino-based industrial control system
"""

import sys
import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QButtonGroup,
                             QRadioButton, QGroupBox, QGridLayout, QFrame,
                             QMessageBox, QSizePolicy)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QPalette, QColor


class SerialReader(QThread):
    """Background thread for reading serial data"""
    data_received = pyqtSignal(str)
    connection_lost = pyqtSignal()

    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self.running = True

    def run(self):
        buffer = ""
        while self.running:
            try:
                if self.serial_port and self.serial_port.is_open and self.serial_port.in_waiting:
                    data = self.serial_port.read(self.serial_port.in_waiting).decode('utf-8', errors='ignore')
                    buffer += data

                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line:
                            self.data_received.emit(line)
            except Exception as e:
                print(f"Serial read error: {e}")
                self.connection_lost.emit()
                break

    def stop(self):
        self.running = False


class ArduinoInterface:
    """Handles communication with Arduino"""

    def __init__(self):
        self.serial_port = None
        self.connected = False
        self.connect()

    def connect(self):
        """Auto-connect to Arduino on USB port"""
        ports = serial.tools.list_ports.comports()

        for port in ports:
            try:
                # Try to connect to each port
                self.serial_port = serial.Serial(port.device, 9600, timeout=1)
                self.connected = True
                print(f"Connected to Arduino on {port.device}")
                return True
            except Exception as e:
                print(f"Failed to connect to {port.device}: {e}")

        print("No Arduino found")
        self.connected = False
        return False

    def send_command(self, command):
        """Send command to Arduino"""
        if not self.connected or not self.serial_port:
            print(f"Cannot send command '{command}': Not connected")
            return False

        try:
            if self.serial_port.is_open:
                self.serial_port.write(f"{command}\n".encode())
                return True
        except Exception as e:
            print(f"Send error: {e}")
            self.connected = False
            return False
        return False

    def close(self):
        """Close serial connection"""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
        except Exception as e:
            print(f"Error closing serial port: {e}")
        finally:
            self.connected = False


class SystemStatus:
    """Tracks system state"""

    def __init__(self):
        self.process_state = "OFF"
        self.estop_active = False
        self.plasma_on = False

        # Dropout states
        self.dropout_states = ["NONE", "NONE", "NONE", "NONE"]
        self.arm_states = ["UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"]
        self.clamp_states = ["UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"]

    def update_from_serial(self, line):
        """Parse serial data and update status"""
        line = line.upper().strip()

        # Process state updates
        if line in ["OFF", "LOADING", "READY", "TREATING", "UNLOADING", "DROPPING", "RETURNING"]:
            self.process_state = line

        # E-stop status
        elif "ESTOP ACTIVE" in line:
            self.estop_active = True
        elif "ESTOP NOT ACTIVE" in line:
            self.estop_active = False
        elif "ESTOP" in line:
            self.estop_active = True


class HMIMainWindow(QMainWindow):
    """Main HMI Window"""

    def __init__(self):
        super().__init__()

        # Initialize Arduino interface
        self.arduino = ArduinoInterface()
        self.status = SystemStatus()
        self.serial_reader = None

        # Start serial reader thread if connected
        if self.arduino.connected and self.arduino.serial_port:
            self.serial_reader = SerialReader(self.arduino.serial_port)
            self.serial_reader.data_received.connect(self.handle_serial_data)
            self.serial_reader.connection_lost.connect(self.handle_connection_lost)
            self.serial_reader.start()

        # Current mode
        self.current_mode = "AUTO"  # AUTO, MANUAL

        self.init_ui()

        # Status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.request_status_update)
        self.status_timer.start(1000)  # Update every second

    def handle_connection_lost(self):
        """Handle lost connection"""
        self.arduino.connected = False
        QMessageBox.warning(self, "Connection Lost",
                            "Lost connection to Arduino. Please check connection and restart.")

    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("Plasma Treatment System")
        self.setGeometry(0, 0, 1280, 800)

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_widget.setLayout(main_layout)

        # Set background color
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(240, 240, 240))
        self.setPalette(palette)

        # Title bar
        title_layout = QHBoxLayout()
        title_label = QLabel("Plasma Treatment System")
        title_label.setFont(QFont("Arial", 28, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title_label, stretch=1)

        # E-Stop button (always visible)
        self.estop_btn = QPushButton("EMERGENCY STOP")
        self.estop_btn.setFont(QFont("Arial", 18, QFont.Bold))
        self.estop_btn.setFixedSize(280, 100)
        self.estop_btn.setStyleSheet("""
            QPushButton {
                background-color: #cc0000;
                color: white;
                border: 4px solid #990000;
                border-radius: 10px;
            }
            QPushButton:pressed {
                background-color: #990000;
            }
        """)
        self.estop_btn.clicked.connect(self.trigger_estop)
        title_layout.addWidget(self.estop_btn)

        main_layout.addLayout(title_layout)

        # Status display (always visible)
        self.status_widget = self.create_status_display()
        main_layout.addWidget(self.status_widget)

        # Mode selection
        mode_group = QGroupBox("Mode Selection")
        mode_group.setFont(QFont("Arial", 14, QFont.Bold))
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(30)

        self.auto_radio = QRadioButton("Auto Process")
        self.auto_radio.setChecked(True)
        self.auto_radio.setFont(QFont("Arial", 16))
        self.auto_radio.toggled.connect(self.mode_changed)

        self.manual_radio = QRadioButton("Manual Control")
        self.manual_radio.setFont(QFont("Arial", 16))
        self.manual_radio.toggled.connect(self.mode_changed)

        mode_layout.addWidget(self.auto_radio)
        mode_layout.addWidget(self.manual_radio)
        mode_layout.addStretch()
        mode_group.setLayout(mode_layout)
        main_layout.addWidget(mode_group)

        # Create both control sections
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(15)

        # Auto process controls (left side)
        self.create_auto_controls(controls_layout)

        # Manual controls (right side)
        self.create_manual_controls(controls_layout)

        main_layout.addLayout(controls_layout)

        # Reset button at bottom
        reset_btn = QPushButton("Reset System")
        reset_btn.setFont(QFont("Arial", 16, QFont.Bold))
        reset_btn.setFixedHeight(80)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6600;
                color: white;
                border-radius: 10px;
                border: 3px solid #cc5200;
            }
            QPushButton:pressed {
                background-color: #cc5200;
            }
        """)
        reset_btn.clicked.connect(self.reset_system)
        main_layout.addWidget(reset_btn)

        main_layout.addStretch()

        # Update button states based on mode
        self.update_button_states()

        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence

        # ESC key to exit fullscreen
        self.shortcut_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.shortcut_esc.activated.connect(self.showNormal)

        # Ctrl+Q to quit application
        self.shortcut_quit = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.shortcut_quit.activated.connect(QApplication.quit)

        # Alt+F4 also works by default on most systems

    def create_status_display(self):
        """Create status display widget"""
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Box | QFrame.Raised)
        status_frame.setLineWidth(3)
        status_frame.setStyleSheet("background-color: white;")

        status_layout = QGridLayout()
        status_layout.setSpacing(10)
        status_layout.setContentsMargins(20, 20, 20, 20)
        status_frame.setLayout(status_layout)

        label_font = QFont("Arial", 16, QFont.Bold)
        value_font = QFont("Arial", 20, QFont.Bold)

        # Process state
        process_label = QLabel("PROCESS STATE:")
        process_label.setFont(label_font)
        process_label.setStyleSheet("color: #000000;")
        status_layout.addWidget(process_label, 0, 0, Qt.AlignRight)

        self.process_state_label = QLabel("OFF")
        self.process_state_label.setFont(value_font)
        self.process_state_label.setStyleSheet("color: gray; padding: 5px;")
        status_layout.addWidget(self.process_state_label, 0, 1, Qt.AlignLeft)

        # E-Stop status
        estop_label = QLabel("E-STOP:")
        estop_label.setFont(label_font)
        estop_label.setStyleSheet("color: #000000;")
        status_layout.addWidget(estop_label, 0, 2, Qt.AlignRight)

        self.estop_status_label = QLabel("INACTIVE")
        self.estop_status_label.setFont(value_font)
        self.estop_status_label.setStyleSheet("color: green; padding: 5px;")
        status_layout.addWidget(self.estop_status_label, 0, 3, Qt.AlignLeft)

        # Plasma status
        plasma_label = QLabel("PLASMA:")
        plasma_label.setFont(label_font)
        plasma_label.setStyleSheet("color: #000000;")
        status_layout.addWidget(plasma_label, 0, 4, Qt.AlignRight)

        self.plasma_status_label = QLabel("OFF")
        self.plasma_status_label.setFont(value_font)
        self.plasma_status_label.setStyleSheet("color: gray; padding: 5px;")
        status_layout.addWidget(self.plasma_status_label, 0, 5, Qt.AlignLeft)

        # Dropout states
        dropout_header_font = QFont("Arial", 14, QFont.Bold)

        self.dropout_labels = []
        for i in range(4):
            col_offset = i * 2

            dropout_label = QLabel(f"DROPOUT {i + 1}:")
            dropout_label.setFont(dropout_header_font)
            dropout_label.setStyleSheet("color: #000000;")
            status_layout.addWidget(dropout_label, 1, col_offset, Qt.AlignRight)

            label = QLabel("NONE")
            label.setFont(QFont("Arial", 18, QFont.Bold))
            label.setStyleSheet("color: #666666; padding: 5px;")
            status_layout.addWidget(label, 1, col_offset + 1, Qt.AlignLeft)
            self.dropout_labels.append(label)

        # Adjust column stretches
        for col in range(8):
            status_layout.setColumnStretch(col, 1)

        return status_frame

    def create_auto_controls(self, parent_layout):
        """Create auto process controls"""
        auto_group = QGroupBox("Auto Process Controls")
        auto_group.setFont(QFont("Arial", 14, QFont.Bold))
        auto_layout = QVBoxLayout()
        auto_layout.setSpacing(15)

        # Begin Auto Treatment button
        self.btn_begin = QPushButton("Begin Auto Treatment")
        self.btn_begin.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_begin.setFixedHeight(100)
        self.btn_begin.setStyleSheet("""
            QPushButton {
                background-color: #0066cc;
                color: white;
                border-radius: 10px;
                border: 3px solid #004499;
            }
            QPushButton:pressed {
                background-color: #004499;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_begin.clicked.connect(self.begin_auto_treatment)
        auto_layout.addWidget(self.btn_begin)

        # Part Loaded button
        self.btn_part_loaded = QPushButton("Part Loaded")
        self.btn_part_loaded.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_part_loaded.setFixedHeight(100)
        self.btn_part_loaded.setStyleSheet("""
            QPushButton {
                background-color: #00aa00;
                color: white;
                border-radius: 10px;
                border: 3px solid #008800;
            }
            QPushButton:pressed {
                background-color: #008800;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_part_loaded.clicked.connect(lambda: self.arduino.send_command("part_loaded"))
        auto_layout.addWidget(self.btn_part_loaded)

        # Start Treatment button
        self.btn_start_treatment = QPushButton("Start Treatment")
        self.btn_start_treatment.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_start_treatment.setFixedHeight(100)
        self.btn_start_treatment.setStyleSheet("""
            QPushButton {
                background-color: #0066cc;
                color: white;
                border-radius: 10px;
                border: 3px solid #004499;
            }
            QPushButton:pressed {
                background-color: #004499;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_start_treatment.clicked.connect(lambda: self.arduino.send_command("start_treatment"))
        auto_layout.addWidget(self.btn_start_treatment)

        # Part Unloaded button
        self.btn_part_unloaded = QPushButton("Part Unloaded")
        self.btn_part_unloaded.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_part_unloaded.setFixedHeight(100)
        self.btn_part_unloaded.setStyleSheet("""
            QPushButton {
                background-color: #00aa00;
                color: white;
                border-radius: 10px;
                border: 3px solid #008800;
            }
            QPushButton:pressed {
                background-color: #008800;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_part_unloaded.clicked.connect(lambda: self.arduino.send_command("part_unloaded"))
        auto_layout.addWidget(self.btn_part_unloaded)

        # Exit Process button
        self.btn_exit_process = QPushButton("Exit Process")
        self.btn_exit_process.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_exit_process.setFixedHeight(100)
        self.btn_exit_process.setStyleSheet("""
            QPushButton {
                background-color: #666666;
                color: white;
                border-radius: 10px;
                border: 3px solid #444444;
            }
            QPushButton:pressed {
                background-color: #444444;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_exit_process.clicked.connect(self.exit_process)
        auto_layout.addWidget(self.btn_exit_process)

        auto_layout.addStretch()
        auto_group.setLayout(auto_layout)
        parent_layout.addWidget(auto_group)

    def create_manual_controls(self, parent_layout):
        """Create manual controls"""
        manual_group = QGroupBox("Manual Controls")
        manual_group.setFont(QFont("Arial", 14, QFont.Bold))
        manual_layout = QVBoxLayout()
        manual_layout.setSpacing(15)

        # All dropouts controls
        dropout_layout = QHBoxLayout()
        dropout_layout.setSpacing(15)

        self.btn_all_up = QPushButton("All Up")
        self.btn_all_up.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_all_up.setFixedHeight(100)
        self.btn_all_up.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_all_up.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 10px;
                border: 3px solid #388E3C;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_all_up.clicked.connect(lambda: self.arduino.send_command("all_up"))

        self.btn_all_load = QPushButton("All Load")
        self.btn_all_load.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_all_load.setFixedHeight(100)
        self.btn_all_load.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_all_load.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border-radius: 10px;
                border: 3px solid #1976D2;
            }
            QPushButton:pressed {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_all_load.clicked.connect(lambda: self.arduino.send_command("all_load"))

        self.btn_all_down = QPushButton("All Down")
        self.btn_all_down.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_all_down.setFixedHeight(100)
        self.btn_all_down.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_all_down.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border-radius: 10px;
                border: 3px solid #F57C00;
            }
            QPushButton:pressed {
                background-color: #F57C00;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_all_down.clicked.connect(lambda: self.arduino.send_command("all_down"))

        dropout_layout.addWidget(self.btn_all_up)
        dropout_layout.addWidget(self.btn_all_load)
        dropout_layout.addWidget(self.btn_all_down)
        manual_layout.addLayout(dropout_layout)

        # Plasma controls
        plasma_layout = QHBoxLayout()
        plasma_layout.setSpacing(15)

        self.btn_plasma_on = QPushButton("Plasma ON")
        self.btn_plasma_on.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_plasma_on.setFixedHeight(100)
        self.btn_plasma_on.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_plasma_on.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                border-radius: 10px;
                border: 3px solid #7B1FA2;
            }
            QPushButton:pressed {
                background-color: #7B1FA2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_plasma_on.clicked.connect(lambda: self.arduino.send_command("plasma_on"))

        self.btn_plasma_off = QPushButton("Plasma OFF")
        self.btn_plasma_off.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_plasma_off.setFixedHeight(100)
        self.btn_plasma_off.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_plasma_off.setStyleSheet("""
            QPushButton {
                background-color: #666666;
                color: white;
                border-radius: 10px;
                border: 3px solid #444444;
            }
            QPushButton:pressed {
                background-color: #444444;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
                border: 3px solid #aaaaaa;
            }
        """)
        self.btn_plasma_off.clicked.connect(lambda: self.arduino.send_command("plasma_off"))

        plasma_layout.addWidget(self.btn_plasma_on)
        plasma_layout.addWidget(self.btn_plasma_off)
        manual_layout.addLayout(plasma_layout)

        manual_layout.addStretch()
        manual_group.setLayout(manual_layout)
        parent_layout.addWidget(manual_group)

    def mode_changed(self):
        """Handle mode change"""
        try:
            if self.auto_radio.isChecked():
                self.current_mode = "AUTO"
            else:
                self.current_mode = "MANUAL"
            self.update_button_states()
        except Exception as e:
            print(f"Error changing mode: {e}")
            QMessageBox.warning(self, "Error", f"Error changing mode: {e}")

    def update_button_states(self):
        """Update button enabled/disabled states based on mode and process state"""
        # Get current states
        is_auto = self.current_mode == "AUTO"
        process_state = self.status.process_state

        # Auto process buttons - enabled only in auto mode
        if is_auto:
            # Enable buttons based on process state
            self.btn_begin.setEnabled(process_state == "OFF")
            self.btn_part_loaded.setEnabled(process_state == "LOADING")
            self.btn_start_treatment.setEnabled(process_state == "READY")
            self.btn_part_unloaded.setEnabled(process_state == "UNLOADING")
            self.btn_exit_process.setEnabled(process_state == "LOADING")
        else:
            # Disable all auto buttons in manual mode
            self.btn_begin.setEnabled(False)
            self.btn_part_loaded.setEnabled(False)
            self.btn_start_treatment.setEnabled(False)
            self.btn_part_unloaded.setEnabled(False)
            self.btn_exit_process.setEnabled(False)

        # Manual control buttons - enabled only in manual mode
        manual_enabled = not is_auto
        self.btn_all_up.setEnabled(manual_enabled)
        self.btn_all_load.setEnabled(manual_enabled)
        self.btn_all_down.setEnabled(manual_enabled)
        self.btn_plasma_on.setEnabled(manual_enabled)
        self.btn_plasma_off.setEnabled(manual_enabled)

    def trigger_estop(self):
        """Trigger emergency stop"""
        self.arduino.send_command("e_stop")

    def begin_auto_treatment(self):
        """Begin auto treatment process"""
        if not self.arduino.connected:
            QMessageBox.warning(self, "Not Connected", "Arduino not connected. Cannot start treatment.")
            return
        self.arduino.send_command("start_process_sm")

    def exit_process(self):
        """Exit process mode"""
        self.arduino.send_command("off")

    def reset_system(self):
        """Reset system"""
        self.arduino.send_command("reset")

    def request_status_update(self):
        """Request status update from Arduino"""
        if self.arduino.connected:
            self.arduino.send_command("status")
            self.arduino.send_command("get_states")

    def handle_serial_data(self, line):
        """Handle incoming serial data"""
        try:
            self.status.update_from_serial(line)
            self.update_status_display()

            # Update button states if process state changed
            if line in ["OFF", "LOADING", "READY", "TREATING", "UNLOADING", "DROPPING", "RETURNING"]:
                self.update_button_states()
        except Exception as e:
            print(f"Error handling serial data: {e}")

    def update_status_display(self):
        """Update status display"""
        try:
            # Process state
            self.process_state_label.setText(self.status.process_state)
            state_colors = {
                "OFF": "gray",
                "LOADING": "#FF9800",
                "READY": "#2196F3",
                "TREATING": "#9C27B0",
                "UNLOADING": "#FF9800",
                "DROPPING": "#FF5722",
                "RETURNING": "#607D8B"
            }
            self.process_state_label.setStyleSheet(
                f"color: {state_colors.get(self.status.process_state, 'gray')}; padding: 5px;")

            # E-Stop status
            if self.status.estop_active:
                self.estop_status_label.setText("ACTIVE")
                self.estop_status_label.setStyleSheet("color: red; padding: 5px;")
            else:
                self.estop_status_label.setText("INACTIVE")
                self.estop_status_label.setStyleSheet("color: green; padding: 5px;")

            # Plasma status
            if self.status.plasma_on:
                self.plasma_status_label.setText("ON")
                self.plasma_status_label.setStyleSheet("color: #9C27B0; padding: 5px;")
            else:
                self.plasma_status_label.setText("OFF")
                self.plasma_status_label.setStyleSheet("color: gray; padding: 5px;")

            # Dropout states
            for i, label in enumerate(self.dropout_labels):
                if i < len(self.status.dropout_states):
                    label.setText(self.status.dropout_states[i])
        except Exception as e:
            print(f"Error updating status display: {e}")

    def closeEvent(self, event):
        """Handle window close"""
        try:
            if hasattr(self, 'serial_reader') and self.serial_reader:
                self.serial_reader.stop()
                self.serial_reader.wait()
            self.arduino.close()
        except Exception as e:
            print(f"Error closing: {e}")
        finally:
            event.accept()


def main():
    app = QApplication(sys.argv)

    # Set application-wide font
    font = QFont("Arial", 12)
    app.setFont(font)

    window = HMIMainWindow()
    window.showFullScreen()  # Full screen on touch display

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()