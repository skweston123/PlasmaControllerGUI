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
                             QRadioButton, QGroupBox, QGridLayout, QFrame)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QPalette, QColor


class SerialReader(QThread):
    """Background thread for reading serial data"""
    data_received = pyqtSignal(str)

    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self.running = True

    def run(self):
        buffer = ""
        while self.running:
            try:
                if self.serial_port.in_waiting:
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

    def stop(self):
        self.running = False


class ArduinoInterface:
    """Handles communication with Arduino"""

    def __init__(self):
        self.serial_port = None
        self.connect()

    def connect(self):
        """Auto-connect to Arduino on USB port"""
        ports = serial.tools.list_ports.comports()

        for port in ports:
            try:
                # Try to connect to each port
                self.serial_port = serial.Serial(port.device, 9600, timeout=1)
                print(f"Connected to Arduino on {port.device}")
                return True
            except Exception as e:
                print(f"Failed to connect to {port.device}: {e}")

        print("No Arduino found")
        return False

    def send_command(self, command):
        """Send command to Arduino"""
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.write(f"{command}\n".encode())
                return True
            except Exception as e:
                print(f"Send error: {e}")
                return False
        return False

    def close(self):
        """Close serial connection"""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()


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

        # Start serial reader thread
        if self.arduino.serial_port:
            self.serial_reader = SerialReader(self.arduino.serial_port)
            self.serial_reader.data_received.connect(self.handle_serial_data)
            self.serial_reader.start()

        # Current mode
        self.current_mode = "AUTO"  # AUTO, MANUAL
        self.selected_dropout = "ALL"  # ALL, 1, 2, 3, 4

        self.init_ui()

        # Status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.request_status_update)
        self.status_timer.start(1000)  # Update every second

    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("Plasma Treatment System")
        self.setGeometry(0, 0, 1280, 800)

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Set background color
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(240, 240, 240))
        self.setPalette(palette)

        # Title bar
        title_layout = QHBoxLayout()
        title_label = QLabel("Plasma Treatment System")
        title_label.setFont(QFont("Arial", 24, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title_label)

        # E-Stop button (always visible)
        self.estop_btn = QPushButton("🛑 EMERGENCY STOP")
        self.estop_btn.setFont(QFont("Arial", 16, QFont.Bold))
        self.estop_btn.setStyleSheet("""
            QPushButton {
                background-color: #cc0000;
                color: white;
                border: 3px solid #990000;
                border-radius: 10px;
                padding: 20px;
                min-width: 200px;
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

        # Control panel (changes based on mode)
        self.control_widget = QWidget()
        self.control_layout = QVBoxLayout()
        self.control_widget.setLayout(self.control_layout)
        main_layout.addWidget(self.control_widget)

        # Initialize in auto mode
        self.update_control_panel()

    def create_status_display(self):
        """Create status display widget"""
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Box | QFrame.Raised)
        status_frame.setLineWidth(2)
        status_layout = QGridLayout()
        status_frame.setLayout(status_layout)

        # Process state
        status_layout.addWidget(QLabel("Process State:"), 0, 0)
        self.process_state_label = QLabel("OFF")
        self.process_state_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.process_state_label.setStyleSheet("color: gray;")
        status_layout.addWidget(self.process_state_label, 0, 1)

        # E-Stop status
        status_layout.addWidget(QLabel("E-Stop:"), 0, 2)
        self.estop_status_label = QLabel("INACTIVE")
        self.estop_status_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.estop_status_label.setStyleSheet("color: green;")
        status_layout.addWidget(self.estop_status_label, 0, 3)

        # Plasma status
        status_layout.addWidget(QLabel("Plasma:"), 0, 4)
        self.plasma_status_label = QLabel("OFF")
        self.plasma_status_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.plasma_status_label.setStyleSheet("color: gray;")
        status_layout.addWidget(self.plasma_status_label, 0, 5)

        # Dropout states
        self.dropout_labels = []
        for i in range(4):
            status_layout.addWidget(QLabel(f"Dropout {i + 1}:"), 1, i)
            label = QLabel("NONE")
            label.setFont(QFont("Arial", 12))
            status_layout.addWidget(label, 2, i)
            self.dropout_labels.append(label)

        return status_frame

    def update_control_panel(self):
        """Update control panel based on mode and state"""
        # Clear existing controls
        for i in reversed(range(self.control_layout.count())):
            widget = self.control_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        if self.current_mode == "AUTO":
            self.create_auto_mode_controls()
        else:
            self.create_manual_mode_controls()

    def create_auto_mode_controls(self):
        """Create controls for auto mode"""
        # Mode selection
        mode_group = QGroupBox("Mode Selection")
        mode_layout = QHBoxLayout()

        self.auto_radio = QRadioButton("Auto Process")
        self.auto_radio.setChecked(True)
        self.auto_radio.setFont(QFont("Arial", 14))
        self.auto_radio.toggled.connect(self.mode_changed)

        self.manual_radio = QRadioButton("Manual Control")
        self.manual_radio.setFont(QFont("Arial", 14))
        self.manual_radio.toggled.connect(self.mode_changed)

        mode_layout.addWidget(self.auto_radio)
        mode_layout.addWidget(self.manual_radio)
        mode_group.setLayout(mode_layout)
        self.control_layout.addWidget(mode_group)

        # Process controls (based on current state)
        process_group = QGroupBox("Process Controls")
        process_layout = QVBoxLayout()

        if self.status.process_state == "OFF":
            btn = QPushButton("▶ Begin Auto Treatment")
            btn.setFont(QFont("Arial", 16, QFont.Bold))
            btn.setMinimumHeight(80)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #0066cc;
                    color: white;
                    border-radius: 10px;
                    padding: 10px;
                }
                QPushButton:pressed {
                    background-color: #004499;
                }
            """)
            btn.clicked.connect(self.begin_auto_treatment)
            process_layout.addWidget(btn)

        elif self.status.process_state == "LOADING":
            btn_loaded = QPushButton("✓ Part Loaded")
            btn_loaded.setFont(QFont("Arial", 16, QFont.Bold))
            btn_loaded.setMinimumHeight(80)
            btn_loaded.setStyleSheet("""
                QPushButton {
                    background-color: #00aa00;
                    color: white;
                    border-radius: 10px;
                }
                QPushButton:pressed {
                    background-color: #008800;
                }
            """)
            btn_loaded.clicked.connect(lambda: self.arduino.send_command("part_loaded"))
            process_layout.addWidget(btn_loaded)

            btn_exit = QPushButton("⏹ Exit Process")
            btn_exit.setFont(QFont("Arial", 16))
            btn_exit.setMinimumHeight(80)
            btn_exit.setStyleSheet("""
                QPushButton {
                    background-color: #666666;
                    color: white;
                    border-radius: 10px;
                }
                QPushButton:pressed {
                    background-color: #444444;
                }
            """)
            btn_exit.clicked.connect(self.exit_process)
            process_layout.addWidget(btn_exit)

        elif self.status.process_state == "READY":
            btn = QPushButton("▶ Start Treatment")
            btn.setFont(QFont("Arial", 16, QFont.Bold))
            btn.setMinimumHeight(80)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #0066cc;
                    color: white;
                    border-radius: 10px;
                }
                QPushButton:pressed {
                    background-color: #004499;
                }
            """)
            btn.clicked.connect(lambda: self.arduino.send_command("start_treatment"))
            process_layout.addWidget(btn)

        elif self.status.process_state == "UNLOADING":
            btn_unloaded = QPushButton("✓ Part Unloaded")
            btn_unloaded.setFont(QFont("Arial", 16, QFont.Bold))
            btn_unloaded.setMinimumHeight(80)
            btn_unloaded.setStyleSheet("""
                QPushButton {
                    background-color: #00aa00;
                    color: white;
                    border-radius: 10px;
                }
                QPushButton:pressed {
                    background-color: #008800;
                }
            """)
            btn_unloaded.clicked.connect(lambda: self.arduino.send_command("part_unloaded"))
            process_layout.addWidget(btn_unloaded)

        else:
            # TREATING, DROPPING, RETURNING - no controls available
            label = QLabel(f"Process Running: {self.status.process_state}")
            label.setFont(QFont("Arial", 16))
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #0066cc; padding: 40px;")
            process_layout.addWidget(label)

        process_group.setLayout(process_layout)
        self.control_layout.addWidget(process_group)

        # Reset button
        reset_btn = QPushButton("🔄 Reset System")
        reset_btn.setFont(QFont("Arial", 14))
        reset_btn.setMinimumHeight(60)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6600;
                color: white;
                border-radius: 10px;
            }
            QPushButton:pressed {
                background-color: #cc5200;
            }
        """)
        reset_btn.clicked.connect(self.reset_system)
        self.control_layout.addWidget(reset_btn)

    def create_manual_mode_controls(self):
        """Create controls for manual mode"""
        # Mode selection
        mode_group = QGroupBox("Mode Selection")
        mode_layout = QHBoxLayout()

        self.auto_radio = QRadioButton("Auto Process")
        self.auto_radio.setFont(QFont("Arial", 14))
        self.auto_radio.toggled.connect(self.mode_changed)

        self.manual_radio = QRadioButton("Manual Control")
        self.manual_radio.setChecked(True)
        self.manual_radio.setFont(QFont("Arial", 14))
        self.manual_radio.toggled.connect(self.mode_changed)

        mode_layout.addWidget(self.auto_radio)
        mode_layout.addWidget(self.manual_radio)
        mode_group.setLayout(mode_layout)
        self.control_layout.addWidget(mode_group)

        # Dropout selection
        dropout_group = QGroupBox("Dropout Selection")
        dropout_layout = QHBoxLayout()

        self.dropout_button_group = QButtonGroup()

        for option in ["ALL", "1", "2", "3", "4"]:
            radio = QRadioButton(f"Dropout {option}" if option != "ALL" else "All Dropouts")
            radio.setFont(QFont("Arial", 12))
            radio.toggled.connect(lambda checked, opt=option: self.dropout_selection_changed(opt, checked))
            self.dropout_button_group.addButton(radio)
            dropout_layout.addWidget(radio)
            if option == "ALL":
                radio.setChecked(True)

        dropout_group.setLayout(dropout_layout)
        self.control_layout.addWidget(dropout_group)

        # Manual controls
        manual_group = QGroupBox("Manual Controls")
        manual_layout = QHBoxLayout()

        btn_up = QPushButton("⬆ Up")
        btn_up.setFont(QFont("Arial", 14, QFont.Bold))
        btn_up.setMinimumHeight(80)
        btn_up.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 10px;")
        btn_up.clicked.connect(self.command_up)

        btn_load = QPushButton("🔄 Load")
        btn_load.setFont(QFont("Arial", 14, QFont.Bold))
        btn_load.setMinimumHeight(80)
        btn_load.setStyleSheet("background-color: #2196F3; color: white; border-radius: 10px;")
        btn_load.clicked.connect(self.command_load)

        btn_down = QPushButton("⬇ Down")
        btn_down.setFont(QFont("Arial", 14, QFont.Bold))
        btn_down.setMinimumHeight(80)
        btn_down.setStyleSheet("background-color: #FF9800; color: white; border-radius: 10px;")
        btn_down.clicked.connect(self.command_down)

        manual_layout.addWidget(btn_up)
        manual_layout.addWidget(btn_load)
        manual_layout.addWidget(btn_down)
        manual_group.setLayout(manual_layout)
        self.control_layout.addWidget(manual_group)

        # Plasma controls
        plasma_group = QGroupBox("Plasma Controls")
        plasma_layout = QHBoxLayout()

        btn_plasma_on = QPushButton("⚡ Plasma ON")
        btn_plasma_on.setFont(QFont("Arial", 14, QFont.Bold))
        btn_plasma_on.setMinimumHeight(60)
        btn_plasma_on.setStyleSheet("background-color: #9C27B0; color: white; border-radius: 10px;")
        btn_plasma_on.clicked.connect(lambda: self.arduino.send_command("plasma_on"))

        btn_plasma_off = QPushButton("Plasma OFF")
        btn_plasma_off.setFont(QFont("Arial", 14))
        btn_plasma_off.setMinimumHeight(60)
        btn_plasma_off.setStyleSheet("background-color: #666; color: white; border-radius: 10px;")
        btn_plasma_off.clicked.connect(lambda: self.arduino.send_command("plasma_off"))

        plasma_layout.addWidget(btn_plasma_on)
        plasma_layout.addWidget(btn_plasma_off)
        plasma_group.setLayout(plasma_layout)
        self.control_layout.addWidget(plasma_group)

        # Reset button
        reset_btn = QPushButton("🔄 Reset System")
        reset_btn.setFont(QFont("Arial", 14))
        reset_btn.setMinimumHeight(60)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6600;
                color: white;
                border-radius: 10px;
            }
            QPushButton:pressed {
                background-color: #cc5200;
            }
        """)
        reset_btn.clicked.connect(self.reset_system)
        self.control_layout.addWidget(reset_btn)

    def mode_changed(self):
        """Handle mode change"""
        if self.auto_radio.isChecked():
            self.current_mode = "AUTO"
        else:
            self.current_mode = "MANUAL"
        self.update_control_panel()

    def dropout_selection_changed(self, option, checked):
        """Handle dropout selection change"""
        if checked:
            self.selected_dropout = option

    def trigger_estop(self):
        """Trigger emergency stop"""
        self.arduino.send_command("e_stop")

    def begin_auto_treatment(self):
        """Begin auto treatment process"""
        self.arduino.send_command("start_process_sm")

    def exit_process(self):
        """Exit process mode"""
        self.arduino.send_command("off")

    def reset_system(self):
        """Reset system"""
        self.arduino.send_command("reset")

    def command_up(self):
        """Command selected dropout(s) up"""
        if self.selected_dropout == "ALL":
            self.arduino.send_command("all_up")
        else:
            self.arduino.send_command(f"{self.selected_dropout}_up")

    def command_load(self):
        """Command selected dropout(s) to load position"""
        if self.selected_dropout == "ALL":
            self.arduino.send_command("all_load")
        else:
            self.arduino.send_command(f"{self.selected_dropout}_load")

    def command_down(self):
        """Command selected dropout(s) down"""
        if self.selected_dropout == "ALL":
            self.arduino.send_command("all_down")
        else:
            self.arduino.send_command(f"{self.selected_dropout}_down")

    def request_status_update(self):
        """Request status update from Arduino"""
        self.arduino.send_command("status")
        self.arduino.send_command("get_states")

    def handle_serial_data(self, line):
        """Handle incoming serial data"""
        self.status.update_from_serial(line)
        self.update_status_display()

        # Update control panel if process state changed
        if line in ["OFF", "LOADING", "READY", "TREATING", "UNLOADING", "DROPPING", "RETURNING"]:
            if self.current_mode == "AUTO":
                self.update_control_panel()

    def update_status_display(self):
        """Update status display"""
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
        self.process_state_label.setStyleSheet(f"color: {state_colors.get(self.status.process_state, 'gray')};")

        # E-Stop status
        if self.status.estop_active:
            self.estop_status_label.setText("ACTIVE")
            self.estop_status_label.setStyleSheet("color: red;")
        else:
            self.estop_status_label.setText("INACTIVE")
            self.estop_status_label.setStyleSheet("color: green;")

        # Plasma status
        if self.status.plasma_on:
            self.plasma_status_label.setText("ON")
            self.plasma_status_label.setStyleSheet("color: #9C27B0;")
        else:
            self.plasma_status_label.setText("OFF")
            self.plasma_status_label.setStyleSheet("color: gray;")

        # Dropout states
        for i, label in enumerate(self.dropout_labels):
            if i < len(self.status.dropout_states):
                label.setText(self.status.dropout_states[i])

    def closeEvent(self, event):
        """Handle window close"""
        if hasattr(self, 'serial_reader'):
            self.serial_reader.stop()
            self.serial_reader.wait()
        self.arduino.close()
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