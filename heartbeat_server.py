#!/usr/bin/env python3
"""
Heartbeat Server - Audio playback server for Raspberry Pi.

This server listens for commands from the Music Network Controller client
and plays audio files using cvlc (command-line VLC). It runs headless on
Raspberry Pi 3 devices and communicates via TCP/IP on port 9915.

The server responds to:
- PLAY requests: Play an audio file with specified volume and playcount
- STOP requests: Stop current playback
- PING requests: Return current status

Audio is played through the 3.5mm audio jack (left channel for color organ).
"""

import socket
import threading
import json
import logging
import time
import os
import sys
import subprocess
import signal
from pathlib import Path
from datetime import datetime
import tracemalloc


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/heartbeat_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class HeartbeatServer:
    """
    Audio playback server for the Heartbeat Effect system.
    
    This server listens on port 9915 for commands from clients and manages
    audio playback using cvlc (command-line VLC). It maintains state about 
    current playback and responds to status requests.
    
    Attributes:
        host (str): Host address to bind to (default: '0.0.0.0')
        port (int): Port number to listen on (default: 9915)
        is_playing (bool): Current playback status
        current_file (str): Name of currently playing file
        play_thread (threading.Thread): Thread handling playback
        current_process (subprocess.Popen): Current cvlc process
        server_socket (socket.socket): Main server socket
        running (bool): Server running flag
    """
    
    def __init__(self, host='0.0.0.0', port=9915):
        """
        Initialize the Heartbeat Server.
        
        Args:
            host (str): Host address to bind to
            port (int): Port number to listen on
        """
        self.host = host
        self.port = port
        self.is_playing = False
        self.current_file = None
        self.play_thread = None
        self.server_socket = None
        self.running = False
        self.play_lock = threading.Lock()
        self.current_process = None
        
        # Check if cvlc is available
        try:
            result = subprocess.run(
                ['which', 'cvlc'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                logger.info("cvlc found and ready for audio playback")
            else:
                logger.warning("cvlc not found. Install with: sudo apt-get install vlc")
        except Exception as e:
            logger.warning(f"Could not check for cvlc: {e}")
        
        # Get documents folder path
        self.documents_path = Path.home() / 'Documents'
        if not self.documents_path.exists():
            self.documents_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created documents folder: {self.documents_path}")
    
    def start(self):
        """Start the server and begin listening for connections."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            logger.info(f"Server started on {self.host}:{self.port}")
            logger.info(f"Audio files location: {self.documents_path}")
            
            while self.running:
                try:
                    self.server_socket.settimeout(1.0)
                    client_socket, address = self.server_socket.accept()
                    logger.info(f"Connection from {address}")
                    
                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")
        
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
        finally:
            self.cleanup()
    
    def handle_client(self, client_socket):
        """
        Handle communication with a connected client.
        
        Args:
            client_socket (socket.socket): Connected client socket
        """
        try:
            # Receive data from client
            data = client_socket.recv(4096).decode('utf-8')
            
            if not data:
                return
            
            # Parse JSON request
            try:
                request = json.loads(data)
                command = request.get('command', '')
                
                logger.info(f"Received command: {command}")
                
                # Process command
                if command == 'PLAY':
                    response = self.handle_play(request)
                elif command == 'STOP':
                    response = self.handle_stop()
                elif command == 'PING':
                    response = self.handle_ping()
                else:
                    response = {
                        'status': 'ERROR',
                        'message': f'Unknown command: {command}'
                    }
                
                # Send response
                client_socket.sendall(json.dumps(response).encode('utf-8'))
                
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
                response = {'status': 'ERROR', 'message': 'Invalid JSON'}
                client_socket.sendall(json.dumps(response).encode('utf-8'))
        
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            client_socket.close()
    
    def handle_play(self, request):
        """
        Handle PLAY command.
        
        Args:
            request (dict): Request dictionary with filename, volume, playcount
            
        Returns:
            dict: Response dictionary with status
        """
        filename = request.get('filename', '')
        volume = request.get('volume', 100)
        playcount = request.get('playcount', 1)
        
        # Construct full file path
        file_path = self.documents_path / filename
        
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return {
                'status': 'ERROR',
                'message': f'File not found: {filename}'
            }
        
        # Stop any current playback
        self.stop_playback()
        
        # Start new playback in thread
        self.play_thread = threading.Thread(
            target=self.play_audio,
            args=(str(file_path), volume, playcount)
        )
        self.play_thread.daemon = True
        self.play_thread.start()
        
        return {
            'status': 'OK',
            'message': 'Playback started',
            'is_playing': True,
            'current_file': filename
        }
    
    def handle_stop(self):
        """
        Handle STOP command.
        
        Returns:
            dict: Response dictionary with status
        """
        self.stop_playback()
        
        return {
            'status': 'OK',
            'message': 'Playback stopped',
            'is_playing': False,
            'current_file': None
        }
    
    def handle_ping(self):
        """
        Handle PING command and return current status.
        
        Returns:
            dict: Response dictionary with current status
        """
        return {
            'status': 'OK',
            'is_playing': self.is_playing,
            'current_file': self.current_file,
            'hostname': socket.gethostname()
        }
    
    def play_audio(self, file_path, volume, playcount):
        """
        Play audio file the specified number of times using cvlc.
        
        Args:
            file_path (str): Full path to audio file
            volume (int): Volume level (0-100)
            playcount (int): Number of times to play the file
        """
        with self.play_lock:
            try:
                self.is_playing = True
                self.current_file = Path(file_path).name
                
                # Convert volume from 0-100 to VLC scale (0-512, where 256 is 100%)
                # Volume 100 = 256, Volume 50 = 128, etc.
                vlc_volume = int((volume / 100.0) * 256)
                
                logger.info(f"Playing {file_path} {playcount} times at {volume}% volume")
                
                for play_num in range(playcount):
                    if not self.is_playing:
                        break
                    
                    logger.info(f"Playback {play_num + 1}/{playcount}")
                    
                    # Build cvlc command
                    # --play-and-exit: quit after playback
                    # --no-video: disable video output
                    # --quiet: suppress console output
                    # --gain: set volume (0.0 to 8.0, where 1.0 is normal)
                    gain = volume / 100.0  # Convert to 0.0-1.0 range
                    
                    cmd = [
                        'cvlc',
                        '--play-and-exit',
                        '--no-video',
                        '--quiet',
                        '--no-loop',
                        '--gain', str(gain),
                        file_path
                    ]
                    
                    try:
                        # Start cvlc process
                        self.current_process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        
                        # Wait for playback to complete
                        while self.is_playing:
                            # Check if process is still running
                            return_code = self.current_process.poll()
                            if return_code is not None:
                                # Process has finished
                                break
                            time.sleep(0.1)
                        
                        # If we broke out due to stop command, terminate the process
                        if self.current_process and self.current_process.poll() is None:
                            self.current_process.terminate()
                            self.current_process.wait(timeout=2)
                        
                    except Exception as e:
                        logger.error(f"Error running cvlc: {e}")
                        if self.current_process:
                            try:
                                self.current_process.kill()
                            except:
                                pass
                    
                    finally:
                        self.current_process = None
                    
                    # Wait before next playback if not the last one
                    if play_num < playcount - 1 and self.is_playing:
                        time.sleep(0.5)
                
                logger.info("Playback completed")
                
            except Exception as e:
                logger.error(f"Error during playback: {e}")
            finally:
                self.is_playing = False
                self.current_file = None
                self.current_process = None
    
    def stop_playback(self):
        """Stop current audio playback."""
        if self.is_playing:
            logger.info("Stopping playback")
            self.is_playing = False
            
            # Terminate the cvlc process if running
            if self.current_process and self.current_process.poll() is None:
                try:
                    self.current_process.terminate()
                    self.current_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.current_process.kill()
                except Exception as e:
                    logger.error(f"Error stopping process: {e}")
            
            if self.play_thread and self.play_thread.is_alive():
                self.play_thread.join(timeout=2.0)
            
            self.current_file = None
            self.current_process = None
    
    def cleanup(self):
        """Clean up resources and stop the server."""
        logger.info("Shutting down server")
        self.running = False
        self.stop_playback()
        
        if self.server_socket:
            self.server_socket.close()


def main():
    """Main entry point for the server application."""
    # Start memory tracking
    tracemalloc.start()
    start_time = datetime.now()
    
    logger.info("=" * 60)
    logger.info("Heartbeat Server Starting")
    logger.info(f"Launch time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # Create and start server
    server = HeartbeatServer()
    
    try:
        # Log memory footprint
        current, peak = tracemalloc.get_traced_memory()
        logger.info(f"Initial memory: {current / 1024 / 1024:.2f} MB")
        
        launch_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Launch duration: {launch_duration:.3f} seconds")
        
        # Start server (blocking call)
        server.start()
        
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        # Log final memory usage
        current, peak = tracemalloc.get_traced_memory()
        logger.info(f"Peak memory usage: {peak / 1024 / 1024:.2f} MB")
        tracemalloc.stop()
        
        # Calculate total runtime
        runtime = (datetime.now() - start_time).total_seconds()
        logger.info(f"Total runtime: {runtime:.2f} seconds")
        logger.info("Server shutdown complete")
        
        return 0


if __name__ == "__main__":
    sys.exit(main())
