# Heartbeat Effect - Music Network Controller

A client-server application for synchronized audio playback across multiple Raspberry Pi devices.

## Overview

This system consists of:
- **Client**: Windows 11 GUI application (PyQt6) that controls multiple servers
- **Server**: Headless Raspberry Pi application that plays audio files on command

## Features

### Client Features
- Control multiple Raspberry Pi servers simultaneously
- Send play/stop commands to all servers at once
- Monitor server status with periodic pinging
- Automatic playback with configurable intervals
- Time-window scheduling (start/end times)
- Persistent state across application restarts
- User-friendly GUI with server management

### Server Features
- Headless operation on Raspberry Pi 3
- Plays audio files from Documents folder
- Supports MP3, WAV, OGG audio formats
- Configurable volume and repeat count
- TCP/IP communication on port 9915
- Automatic startup at boot (optional)

## Requirements

### Client (Windows 11)
```bash
pip install PyQt6
```

### Server (Raspberry Pi)
```bash
sudo apt-get update
sudo apt-get install python3-pygame
```

## Installation

### Client Setup (Windows 11)

1. Install Python 3.8 or higher
2. Install required packages:
   ```bash
   pip install PyQt6
   ```
3. Place `heartbeat_client.py` in your desired location
4. Run the client:
   ```bash
   python heartbeat_client.py
   ```

### Server Setup (Raspberry Pi)

1. Ensure Python 3.7+ is installed (comes with Raspberry Pi OS)
2. Install pygame for audio playback:
   ```bash
   sudo apt-get install python3-pygame
   ```
3. Copy `heartbeat_server.py` to the Raspberry Pi (e.g., `/home/pi/`)
4. Create Documents folder if it doesn't exist:
   ```bash
   mkdir -p ~/Documents
   ```
5. Copy audio files to `~/Documents/`

### Running the Server Manually
```bash
python3 heartbeat_server.py
```

### Auto-Start Server at Boot (Optional)

1. Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/heartbeat.service
   ```

2. Add the following content:
   ```ini
   [Unit]
   Description=Heartbeat Audio Server
   After=network.target sound.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi
   ExecStart=/usr/bin/python3 /home/pi/heartbeat_server.py
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable heartbeat.service
   sudo systemctl start heartbeat.service
   ```

4. Check status:
   ```bash
   sudo systemctl status heartbeat.service
   ```

## Usage

### Client Usage

1. **Launch the client**: Run `heartbeat_client.py`

2. **Add servers**:
   - Click "Add Server"
   - Enter server name (e.g., "Living Room")
   - Enter hostname (IP address or hostname like `raspberrypi.local`)
   - Port defaults to 9915
   - Click OK

3. **Configure playback**:
   - **Filename**: Name of audio file in server's Documents folder (e.g., `heartbeat.mp3`)
   - **Volume**: 0-100%
   - **Play Count**: Number of times to repeat the file
   - **Interval**: Minutes between automatic plays (0 to disable)
   - **Start Time**: Auto-play start time
   - **End Time**: Auto-play end time

4. **Play audio**:
   - Click "Play" to play on all servers simultaneously
   - Click "Stop" to stop playback on all servers

5. **Enable auto-play**:
   - Set desired interval (in minutes)
   - Set start and end times
   - Check "Enable Auto-Play"

6. **Server management**:
   - Select a row and click "Edit Server" to modify settings
   - Select a row and click "Delete Server" to remove it
   - Server status updates every 10 seconds

### Server Status Indicators

- **Status**: 
  - `OK` - Server responding normally
  - `Timeout` - Server not responding
  - `Refused` - Connection refused (server not running)
  - `Error` - Communication error

- **Playing**: 
  - `Yes` - Currently playing audio
  - `No` - Idle

- **Last Request**: Shows the most recent command sent to the server

## Audio File Requirements

- Place audio files in `~/Documents/` on each Raspberry Pi
- Supported formats: MP3, WAV, OGG, FLAC
- Ensure filenames match exactly (case-sensitive)
- For best results, use consistent audio formats across all servers

## Network Configuration

### Default Port
- Server listens on port **9915**
- Ensure this port is open on your firewall

### Finding Raspberry Pi IP Address
On the Raspberry Pi, run:
```bash
hostname -I
```

Or use hostname resolution:
```bash
ping raspberrypi.local
```

### Testing Connectivity
From Windows, test if server is reachable:
```bash
ping <raspberry-pi-ip>
```

## Troubleshooting

### Server Won't Start
- Check if port 9915 is already in use: `sudo netstat -tulpn | grep 9915`
- Verify pygame is installed: `python3 -c "import pygame"`
- Check logs: `tail -f /tmp/heartbeat_server.log`

### Client Can't Connect
- Verify server is running on Raspberry Pi
- Check firewall settings on both client and server
- Ensure correct IP address/hostname
- Test with `ping` first

### Audio Not Playing
- Verify audio file exists in `~/Documents/`
- Check file permissions: `ls -l ~/Documents/`
- Test audio output: `aplay /usr/share/sounds/alsa/Front_Center.wav`
- Check volume: `alsamixer`

### No Sound from Color Organ
- Ensure color organ is connected to 3.5mm jack (left channel)
- Check pygame audio output configuration
- Test with regular headphones first

## Logging

### Client Logs
- Location: `heartbeat_client.log` (same directory as client)
- Contains: Connection attempts, commands sent, errors

### Server Logs
- Location: `/tmp/heartbeat_server.log`
- Contains: Received commands, playback status, errors
- View live: `tail -f /tmp/heartbeat_server.log`

## State Persistence

The client saves its state to `~/.heartbeat_client_state.json` including:
- Server list
- Playback settings
- Auto-play configuration

This state is automatically restored when the client restarts.

## Performance Metrics

Both client and server log:
- Launch time
- Launch duration
- Memory footprint (initial and peak)
- Total runtime

## Architecture

### Communication Protocol

All messages are JSON over TCP/IP:

**PLAY Request**:
```json
{
  "command": "PLAY",
  "filename": "heartbeat.mp3",
  "volume": 75,
  "playcount": 3
}
```

**STOP Request**:
```json
{
  "command": "STOP"
}
```

**PING Request**:
```json
{
  "command": "PING"
}
```

**Response Format**:
```json
{
  "status": "OK",
  "is_playing": true,
  "current_file": "heartbeat.mp3",
  "message": "Playback started"
}
```

## Safety Features

- Client exits cleanly without affecting server state
- Server waits for playback completion before starting next track
- Automatic reconnection attempts via periodic pinging
- All errors are logged for debugging

## Tips for Best Results

1. **Synchronization**: While the client sends commands simultaneously, network latency may cause slight variations. For tighter sync, ensure all devices are on the same local network with good signal strength.

2. **Audio Files**: Use identical audio files on all servers for consistent playback.

3. **Testing**: Test with a single server first before adding multiple servers.

4. **Network Stability**: Use wired Ethernet for Raspberry Pis when possible for more reliable connections.

5. **Volume Levels**: Start with lower volumes (50-75%) and adjust as needed.

## License

This software is provided as-is for the Heartbeat Effect project.

## Support

For issues or questions:
1. Check the log files for error messages
2. Verify network connectivity
3. Ensure all dependencies are installed
4. Test individual components separately
