#!/usr/bin/env python3
"""
Music Network Controller - Client application for Heartbeat Effect.

This application provides a GUI to control multiple Raspberry Pi audio servers
simultaneously. It manages server connections, sends play/stop commands, and
monitors server status through periodic pinging.

The client saves its state across sessions and supports automatic playback
scheduling with configurable intervals and time windows.
"""

import sys
import socket
import json
import logging
import tracemalloc
from datetime import datetime, time as dt_time
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QSpinBox, QTimeEdit, QCheckBox, QDialog, QDialogButtonBox,
    QFormLayout, QMessageBox, QHeaderView
)
from PyQt6.QtCore import QTimer, Qt, QTime
from PyQt6.QtGui import QFont


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('heartbeat_client.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ServerDialog(QDialog):
    """
    Dialog for adding or editing server configuration.
    
    This dialog allows users to input server details including name,
    hostname, and port number.
    """
    
    def __init__(self, parent=None, server_data=None):
        """
        Initialize the server dialog.
        
        Args:
            parent (QWidget): Parent widget
            server_data (dict): Existing server data for editing, None for new
        """
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Server" if not server_data else "Edit Server")
        self.setModal(True)
        
        layout = QFormLayout()
        
        # Server name input
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Living Room")
        layout.addRow("Server Name:", self.name_input)
        
        # Hostname input
        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText("e.g., 192.168.1.100 or raspberrypi.local")
        layout.addRow("Hostname:", self.hostname_input)
        
        # Port input
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(9915)
        layout.addRow("Port:", self.port_input)
        
        # Populate with existing data if editing
        if server_data:
            self.name_input.setText(server_data.get('name', ''))
            self.hostname_input.setText(server_data.get('hostname', ''))
            self.port_input.setValue(server_data.get('port', 9915))
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addRow(button_box)
        self.setLayout(layout)
    
    def get_server_data(self):
        """
        Get the server data from the dialog inputs.
        
        Returns:
            dict: Server configuration data
        """
        return {
            'name': self.name_input.text().strip(),
            'hostname': self.hostname_input.text().strip(),
            'port': self.port_input.value()
        }


class MusicNetworkController(QMainWindow):
    """
    Main application window for the Music Network Controller.
    
    This class manages the GUI, server list, playback controls, and
    automatic scheduling. It handles all communication with the
    Raspberry Pi servers and maintains application state.
    
    Attributes:
        servers (list): List of server configuration dictionaries
        ping_timer (QTimer): Timer for periodic server pinging
        auto_play_timer (QTimer): Timer for automatic playback
        countdown_timer (QTimer): Timer for countdown display updates
        is_auto_playing (bool): Flag for automatic playback state
        last_auto_play_time (datetime): Timestamp of last auto-play trigger
    """
    
    def __init__(self):
        """Initialize the Music Network Controller application."""
        super().__init__()
        self.servers = []
        self.ping_timer = None
        self.auto_play_timer = None
        self.countdown_timer = None
        self.is_auto_playing = False
        self.last_auto_play_time = None
        self.state_file = Path.home() / '.heartbeat_client_state.json'
        
        self.init_ui()
        self.load_state()
        self.start_ping_timer()
        
        logger.info("Music Network Controller initialized")
    
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Music Network Controller")
        self.setGeometry(100, 100, 1000, 600)
        
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Title and subtitle
        title_label = QLabel("Music Network Controller")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle_label = QLabel("Heartbeat Effect")
        subtitle_font = QFont()
        subtitle_font.setPointSize(12)
        subtitle_label.setFont(subtitle_font)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        main_layout.addWidget(title_label)
        main_layout.addWidget(subtitle_label)
        
        # Server table
        self.server_table = QTableWidget(0, 5)
        self.server_table.setHorizontalHeaderLabels([
            "Server Name", "Hostname", "Status", "Playing", "Last Request"
        ])
        self.server_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.server_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        main_layout.addWidget(self.server_table)
        
        # Server management buttons
        server_buttons_layout = QHBoxLayout()
        
        self.add_server_btn = QPushButton("Add Server")
        self.add_server_btn.clicked.connect(self.add_server)
        
        self.edit_server_btn = QPushButton("Edit Server")
        self.edit_server_btn.clicked.connect(self.edit_server)
        
        self.delete_server_btn = QPushButton("Delete Server")
        self.delete_server_btn.clicked.connect(self.delete_server)
        
        server_buttons_layout.addWidget(self.add_server_btn)
        server_buttons_layout.addWidget(self.edit_server_btn)
        server_buttons_layout.addWidget(self.delete_server_btn)
        server_buttons_layout.addStretch()
        
        main_layout.addLayout(server_buttons_layout)
        
        # Playback controls section
        controls_layout = QFormLayout()
        
        # Filename
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("e.g., heartbeat.mp3")
        controls_layout.addRow("Filename:", self.filename_input)
        
        # Volume
        self.volume_input = QSpinBox()
        self.volume_input.setRange(0, 100)
        self.volume_input.setValue(75)
        self.volume_input.setSuffix("%")
        controls_layout.addRow("Volume:", self.volume_input)
        
        # Playcount
        self.playcount_input = QSpinBox()
        self.playcount_input.setRange(1, 1000)
        self.playcount_input.setValue(1)
        controls_layout.addRow("Play Count:", self.playcount_input)
        
        # Interval
        self.interval_input = QSpinBox()
        self.interval_input.setRange(0, 1440)
        self.interval_input.setValue(0)
        self.interval_input.setSuffix(" minutes")
        self.interval_input.setSpecialValueText("Disabled")
        controls_layout.addRow("Interval:", self.interval_input)
        
        # Start time
        self.start_time_input = QTimeEdit()
        self.start_time_input.setTime(QTime(0, 0))
        self.start_time_input.setDisplayFormat("HH:mm")
        controls_layout.addRow("Start Time:", self.start_time_input)
        
        # End time
        self.end_time_input = QTimeEdit()
        self.end_time_input.setTime(QTime(23, 59))
        self.end_time_input.setDisplayFormat("HH:mm")
        controls_layout.addRow("End Time:", self.end_time_input)
        
        main_layout.addLayout(controls_layout)
        
        # Play/Stop buttons
        playback_buttons_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.play_audio)
        self.play_btn.setMinimumHeight(40)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_audio)
        self.stop_btn.setMinimumHeight(40)
        
        self.auto_play_checkbox = QCheckBox("Enable Auto-Play")
        self.auto_play_checkbox.stateChanged.connect(self.toggle_auto_play)
        
        # Countdown timer label
        self.countdown_label = QLabel("")
        countdown_font = QFont()
        countdown_font.setPointSize(10)
        countdown_font.setBold(True)
        self.countdown_label.setFont(countdown_font)
        self.countdown_label.setStyleSheet("color: #0066cc;")
        
        playback_buttons_layout.addWidget(self.play_btn)
        playback_buttons_layout.addWidget(self.stop_btn)
        playback_buttons_layout.addWidget(self.auto_play_checkbox)
        playback_buttons_layout.addWidget(self.countdown_label)
        playback_buttons_layout.addStretch()
        
        main_layout.addLayout(playback_buttons_layout)
    
    def add_server(self):
        """Add a new server to the list."""
        dialog = ServerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            server_data = dialog.get_server_data()
            
            if not server_data['name'] or not server_data['hostname']:
                QMessageBox.warning(
                    self, "Invalid Input",
                    "Server name and hostname are required."
                )
                return
            
            # Initialize server state
            server_data.update({
                'status': 'Unknown',
                'is_playing': False,
                'last_request': 'None'
            })
            
            self.servers.append(server_data)
            self.update_server_table()
            self.save_state()
            logger.info(f"Added server: {server_data['name']}")
    
    def edit_server(self):
        """Edit the selected server."""
        selected_rows = self.server_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(
                self, "No Selection",
                "Please select a server to edit."
            )
            return
        
        row = self.server_table.currentRow()
        if row < 0 or row >= len(self.servers):
            return
        
        server_data = self.servers[row]
        dialog = ServerDialog(self, server_data)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_server_data()
            
            if not new_data['name'] or not new_data['hostname']:
                QMessageBox.warning(
                    self, "Invalid Input",
                    "Server name and hostname are required."
                )
                return
            
            # Preserve status information
            new_data.update({
                'status': server_data.get('status', 'Unknown'),
                'is_playing': server_data.get('is_playing', False),
                'last_request': server_data.get('last_request', 'None')
            })
            
            self.servers[row] = new_data
            self.update_server_table()
            self.save_state()
            
            # Clear selection after edit
            self.server_table.clearSelection()
            logger.info(f"Edited server: {new_data['name']}")
    
    def delete_server(self):
        """Delete the selected server."""
        selected_rows = self.server_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(
                self, "No Selection",
                "Please select a server to delete."
            )
            return
        
        row = self.server_table.currentRow()
        if row < 0 or row >= len(self.servers):
            return
        
        server_name = self.servers[row]['name']
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete server '{server_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.servers[row]
            self.update_server_table()
            self.save_state()
            logger.info(f"Deleted server: {server_name}")
    
    def update_server_table(self):
        """Update the server table display with current server data."""
        self.server_table.setRowCount(len(self.servers))
        
        for row, server in enumerate(self.servers):
            self.server_table.setItem(
                row, 0, QTableWidgetItem(server['name'])
            )
            self.server_table.setItem(
                row, 1, QTableWidgetItem(f"{server['hostname']}:{server['port']}")
            )
            self.server_table.setItem(
                row, 2, QTableWidgetItem(server.get('status', 'Unknown'))
            )
            self.server_table.setItem(
                row, 3, QTableWidgetItem('Yes' if server.get('is_playing', False) else 'No')
            )
            self.server_table.setItem(
                row, 4, QTableWidgetItem(server.get('last_request', 'None'))
            )
    
    def play_audio(self):
        """Send play command to all servers."""
        filename = self.filename_input.text().strip()
        
        if not filename:
            QMessageBox.warning(
                self, "Missing Filename",
                "Please enter a filename to play."
            )
            return
        
        if not self.servers:
            QMessageBox.warning(
                self, "No Servers",
                "Please add at least one server."
            )
            return
        
        volume = self.volume_input.value()
        playcount = self.playcount_input.value()
        
        request = {
            'command': 'PLAY',
            'filename': filename,
            'volume': volume,
            'playcount': playcount
        }
        
        logger.info(f"Sending PLAY command: {filename}, volume={volume}, playcount={playcount}")
        
        # Send to all servers simultaneously
        for server in self.servers:
            self.send_command(server, request, 'PLAY')
        
        # Reset countdown timer if auto-play is active
        if self.is_auto_playing:
            self.last_auto_play_time = datetime.now()
            self.update_countdown()
        
        self.update_server_table()
    
    def stop_audio(self):
        """Send stop command to all servers."""
        if not self.servers:
            return
        
        request = {'command': 'STOP'}
        logger.info("Sending STOP command to all servers")
        
        for server in self.servers:
            self.send_command(server, request, 'STOP')
        
        self.update_server_table()
    
    def send_command(self, server, request, command_name):
        """
        Send a command to a specific server.
        
        Args:
            server (dict): Server configuration
            request (dict): Request payload
            command_name (str): Command name for logging
        """
        try:
            # Create socket connection
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5.0)
            
            # Connect to server
            client_socket.connect((server['hostname'], server['port']))
            
            # Send request
            client_socket.sendall(json.dumps(request).encode('utf-8'))
            
            # Receive response
            response_data = client_socket.recv(4096).decode('utf-8')
            response = json.loads(response_data)
            
            # Update server status
            server['status'] = response.get('status', 'ERROR')
            server['is_playing'] = response.get('is_playing', False)
            server['last_request'] = command_name
            
            logger.info(f"Server {server['name']} response: {response.get('message', 'OK')}")
            
            client_socket.close()
            
        except socket.timeout:
            server['status'] = 'Timeout'
            server['last_request'] = command_name
            logger.error(f"Timeout connecting to {server['name']}")
        except ConnectionRefusedError:
            server['status'] = 'Refused'
            server['last_request'] = command_name
            logger.error(f"Connection refused by {server['name']}")
        except Exception as e:
            server['status'] = 'Error'
            server['last_request'] = command_name
            logger.error(f"Error communicating with {server['name']}: {e}")
    
    def ping_servers(self):
        """Periodically ping all servers to check status."""
        if not self.servers:
            return
        
        request = {'command': 'PING'}
        
        for server in self.servers:
            self.send_command(server, request, 'PING')
        
        self.update_server_table()
    
    def start_ping_timer(self):
        """Start the periodic ping timer."""
        self.ping_timer = QTimer(self)
        self.ping_timer.timeout.connect(self.ping_servers)
        self.ping_timer.start(10000)  # Ping every 10 seconds
        logger.info("Ping timer started")
    
    def toggle_auto_play(self, state):
        """
        Toggle automatic playback on or off.
        
        Args:
            state (int): Checkbox state
        """
        if state == Qt.CheckState.Checked.value:
            interval = self.interval_input.value()
            
            if interval <= 0:
                QMessageBox.warning(
                    self, "Invalid Interval",
                    "Please set an interval greater than 0 minutes for auto-play."
                )
                self.auto_play_checkbox.setChecked(False)
                return
            
            self.is_auto_playing = True
            self.last_auto_play_time = datetime.now()
            
            # Start auto-play timer (check every minute)
            self.auto_play_timer = QTimer(self)
            self.auto_play_timer.timeout.connect(self.auto_play_check)
            self.auto_play_timer.start(60000)  # Check every minute
            
            # Start countdown display timer (update every second)
            self.countdown_timer = QTimer(self)
            self.countdown_timer.timeout.connect(self.update_countdown)
            self.countdown_timer.start(1000)  # Update every second
            
            logger.info(f"Auto-play enabled with {interval} minute interval")
            self.update_countdown()  # Immediate update
        else:
            self.is_auto_playing = False
            if self.auto_play_timer:
                self.auto_play_timer.stop()
            if self.countdown_timer:
                self.countdown_timer.stop()
            self.countdown_label.setText("")
            logger.info("Auto-play disabled")
    
    def auto_play_check(self):
        """Check if auto-play should trigger based on time and interval."""
        if not self.is_auto_playing or not self.last_auto_play_time:
            return
        
        current_time = datetime.now().time()
        start_time = self.start_time_input.time().toPyTime()
        end_time = self.end_time_input.time().toPyTime()
        
        # Check if current time is within the allowed window
        if not (start_time <= current_time <= end_time):
            return
        
        # Calculate time elapsed since last play
        interval_minutes = self.interval_input.value()
        time_elapsed = (datetime.now() - self.last_auto_play_time).total_seconds() / 60.0
        
        # Trigger if enough time has elapsed
        if time_elapsed >= interval_minutes:
            logger.info("Auto-play triggered")
            self.last_auto_play_time = datetime.now()
            self.play_audio()
            self.update_countdown()  # Immediate update after play
    
    def update_countdown(self):
        """Update the countdown timer display."""
        if not self.is_auto_playing or not self.last_auto_play_time:
            self.countdown_label.setText("")
            return
        
        current_time = datetime.now().time()
        start_time = self.start_time_input.time().toPyTime()
        end_time = self.end_time_input.time().toPyTime()
        
        # Check if we're outside the time window
        if not (start_time <= current_time <= end_time):
            self.countdown_label.setText("⏸ Outside time window")
            return
        
        # Calculate time remaining
        interval_minutes = self.interval_input.value()
        time_elapsed = (datetime.now() - self.last_auto_play_time).total_seconds()
        time_remaining_seconds = (interval_minutes * 60) - time_elapsed
        
        # If time remaining is negative or very close to zero, it means we're about to play
        if time_remaining_seconds <= 0:
            self.countdown_label.setText("▶ Playing soon...")
            return
        
        # Format the countdown display
        minutes_remaining = int(time_remaining_seconds // 60)
        seconds_remaining = int(time_remaining_seconds % 60)
        
        if minutes_remaining > 0:
            self.countdown_label.setText(
                f"⏱ Next play in: {minutes_remaining}m {seconds_remaining}s"
            )
        else:
            self.countdown_label.setText(
                f"⏱ Next play in: {seconds_remaining}s"
            )
    
    def save_state(self):
        """Save application state to file."""
        state = {
            'servers': self.servers,
            'filename': self.filename_input.text(),
            'volume': self.volume_input.value(),
            'playcount': self.playcount_input.value(),
            'interval': self.interval_input.value(),
            'start_time': self.start_time_input.time().toString("HH:mm"),
            'end_time': self.end_time_input.time().toString("HH:mm")
        }
        
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.info("State saved successfully")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def load_state(self):
        """Load application state from file."""
        if not self.state_file.exists():
            logger.info("No saved state found")
            return
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            self.servers = state.get('servers', [])
            self.filename_input.setText(state.get('filename', ''))
            self.volume_input.setValue(state.get('volume', 75))
            self.playcount_input.setValue(state.get('playcount', 1))
            self.interval_input.setValue(state.get('interval', 0))
            
            start_time_str = state.get('start_time', '00:00')
            self.start_time_input.setTime(QTime.fromString(start_time_str, "HH:mm"))
            
            end_time_str = state.get('end_time', '23:59')
            self.end_time_input.setTime(QTime.fromString(end_time_str, "HH:mm"))
            
            self.update_server_table()
            logger.info("State loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
    
    def closeEvent(self, event):
        """
        Handle window close event.
        
        Args:
            event (QCloseEvent): Close event
        """
        self.save_state()
        
        # Stop timers
        if self.ping_timer:
            self.ping_timer.stop()
        if self.auto_play_timer:
            self.auto_play_timer.stop()
        if self.countdown_timer:
            self.countdown_timer.stop()
        
        logger.info("Application closing")
        event.accept()


def main():
    """Main entry point for the client application."""
    # Start memory tracking
    tracemalloc.start()
    start_time = datetime.now()
    
    logger.info("=" * 60)
    logger.info("Music Network Controller Starting")
    logger.info(f"Launch time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Music Network Controller")
    
    # Log memory footprint
    current, peak = tracemalloc.get_traced_memory()
    logger.info(f"Initial memory: {current / 1024 / 1024:.2f} MB")
    
    launch_duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"Launch duration: {launch_duration:.3f} seconds")
    
    # Create and show main window
    window = MusicNetworkController()
    window.show()
    
    # Run application
    result = app.exec()
    
    # Log final memory usage
    current, peak = tracemalloc.get_traced_memory()
    logger.info(f"Peak memory usage: {peak / 1024 / 1024:.2f} MB")
    tracemalloc.stop()
    
    # Calculate total runtime
    runtime = (datetime.now() - start_time).total_seconds()
    logger.info(f"Total runtime: {runtime:.2f} seconds")
    logger.info("Application shutdown complete")
    
    return result


if __name__ == "__main__":
    sys.exit(main())
