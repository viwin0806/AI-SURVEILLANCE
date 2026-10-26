"""
Phase 2 — RTSP Multi-Camera Manager
=====================================
Real-time CCTV camera stream manager using RTSP protocol.

This module extends Phase 1 (file/webcam) to support:
- Multiple simultaneous RTSP camera feeds
- Automatic reconnection on stream failure
- Camera status monitoring
- Frame buffering for smooth processing

IMPORTANT: This module requires actual RTSP camera hardware.
For the academic demonstration, Phase 1 (file/webcam) is used.

Architecture:
  RTSP Camera 1 → RTSPReader → Frame Queue → AI Pipeline
  RTSP Camera 2 → RTSPReader → Frame Queue → AI Pipeline
  ...

Usage:
    manager = RTSPManager()
    manager.add_camera("rtsp://192.168.1.100:554/stream1", name="Camera 1")
    manager.add_camera("rtsp://192.168.1.101:554/stream1", name="Camera 2")
    manager.start()
    
    frame, camera_id = manager.get_frame()
"""

import cv2
import time
import logging
import threading
from collections import deque

logger = logging.getLogger(__name__)


class RTSPCamera:
    """Manages a single RTSP camera connection."""
    
    def __init__(self, url, name="Unknown", reconnect_delay=5.0, buffer_size=5):
        """
        Initialize RTSP camera.
        
        Args:
            url:             RTSP stream URL (e.g., rtsp://192.168.1.100/stream)
            name:            Human-readable camera name
            reconnect_delay: Seconds before reconnection attempt
            buffer_size:     Frame buffer size (prevents blocking)
        """
        self.url = url
        self.name = name
        self.reconnect_delay = reconnect_delay
        
        self.cap = None
        self.frame_buffer = deque(maxlen=buffer_size)
        self.is_connected = False
        self.last_frame_time = 0
        self.connect_attempts = 0
        self.total_frames = 0
        self.dropped_frames = 0
        
        self._reader_thread = None
        self._stop_event = threading.Event()
    
    def connect(self):
        """Attempt RTSP connection."""
        try:
            logger.info(f"Connecting to camera '{self.name}': {self.url}")
            self.cap = cv2.VideoCapture(self.url)
            
            # Set RTSP-specific options for lower latency
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            if self.cap.isOpened():
                # Test read
                ret, _ = self.cap.read()
                if ret:
                    self.is_connected = True
                    self.connect_attempts = 0
                    logger.info(f"Camera '{self.name}' connected successfully")
                    return True
            
            logger.warning(f"Camera '{self.name}' connection failed")
            self.is_connected = False
            self.connect_attempts += 1
            return False
            
        except Exception as e:
            logger.error(f"Camera '{self.name}' error: {e}")
            self.is_connected = False
            self.connect_attempts += 1
            return False
    
    def start_reading(self):
        """Start background frame reading thread."""
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reading_loop, daemon=True
        )
        self._reader_thread.start()
    
    def _reading_loop(self):
        """Background loop: continuously read frames from RTSP stream."""
        while not self._stop_event.is_set():
            if not self.is_connected:
                # Attempt reconnection
                time.sleep(self.reconnect_delay)
                self.connect()
                continue
            
            if self.cap is None or not self.cap.isOpened():
                self.is_connected = False
                continue
            
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.frame_buffer.append(frame)
                self.last_frame_time = time.time()
                self.total_frames += 1
            else:
                self.dropped_frames += 1
                # Check for stream loss
                if time.time() - self.last_frame_time > 5.0:
                    logger.warning(f"Camera '{self.name}': Stream lost, reconnecting...")
                    self.is_connected = False
                    if self.cap:
                        self.cap.release()
    
    def get_frame(self):
        """Get latest frame from buffer."""
        if self.frame_buffer:
            return True, self.frame_buffer[-1]
        return False, None
    
    def stop(self):
        """Stop camera."""
        self._stop_event.set()
        if self.cap:
            self.cap.release()
        self.is_connected = False
    
    def get_status(self):
        """Get camera status."""
        return {
            "name": self.name,
            "url": self.url,
            "connected": self.is_connected,
            "total_frames": self.total_frames,
            "dropped_frames": self.dropped_frames,
            "buffer_fill": len(self.frame_buffer),
            "connect_attempts": self.connect_attempts,
            "last_frame_age": round(time.time() - self.last_frame_time, 1)
                              if self.last_frame_time > 0 else -1,
        }


class RTSPManager:
    """
    Manages multiple RTSP camera feeds for the surveillance system.
    
    In Phase 1: VideoSource handles single file/webcam input
    In Phase 2: RTSPManager handles multiple simultaneous camera feeds
    
    Integration with app.py:
        Replace VideoSource with RTSPManager for multi-camera support.
        The rest of the pipeline (YOLO, violence, threat scoring) 
        processes one camera's frame at a time in round-robin fashion.
    """
    
    def __init__(self):
        self.cameras = {}           # {camera_id: RTSPCamera}
        self.active_camera_id = None
        self._lock = threading.Lock()
    
    def add_camera(self, url, camera_id=None, name=None):
        """
        Add RTSP camera to the manager.
        
        Args:
            url:       RTSP URL
            camera_id: Unique identifier (defaults to camera index)
            name:      Human-readable name
        
        Returns:
            camera_id: Assigned camera ID
        """
        if camera_id is None:
            camera_id = f"cam_{len(self.cameras)}"
        if name is None:
            name = camera_id
        
        with self._lock:
            camera = RTSPCamera(url, name=name)
            self.cameras[camera_id] = camera
        
        logger.info(f"Added camera: {camera_id} ({url})")
        return camera_id
    
    def remove_camera(self, camera_id):
        """Remove and stop a camera."""
        with self._lock:
            if camera_id in self.cameras:
                self.cameras[camera_id].stop()
                del self.cameras[camera_id]
    
    def start_all(self):
        """Start all cameras."""
        for camera_id, camera in self.cameras.items():
            camera.connect()
            camera.start_reading()
        
        if self.cameras:
            self.active_camera_id = list(self.cameras.keys())[0]
    
    def stop_all(self):
        """Stop all cameras."""
        for camera in self.cameras.values():
            camera.stop()
    
    def get_frame(self, camera_id=None):
        """
        Get frame from specified camera (or active camera).
        
        Returns:
            (bool, frame, camera_id): ret, frame array, source camera
        """
        target_id = camera_id or self.active_camera_id
        if target_id and target_id in self.cameras:
            ret, frame = self.cameras[target_id].get_frame()
            return ret, frame, target_id
        return False, None, None
    
    def switch_camera(self, camera_id):
        """Switch active camera."""
        if camera_id in self.cameras:
            self.active_camera_id = camera_id
            logger.info(f"Active camera: {camera_id}")
    
    def get_all_status(self):
        """Get status of all cameras."""
        return {
            cid: cam.get_status()
            for cid, cam in self.cameras.items()
        }
    
    @property
    def camera_count(self):
        return len(self.cameras)
    
    @property
    def connected_count(self):
        return sum(1 for c in self.cameras.values() if c.is_connected)


# ── Example RTSP URLs ──────────────────────────────────────────────
#
# Common RTSP formats:
#   rtsp://192.168.1.100:554/stream       (generic)
#   rtsp://admin:password@192.168.1.100/  (with auth)
#   rtsp://user:pass@192.168.1.100:554/h264/ch1/main/av_stream  (Dahua/Hikvision)
#
# Test with a local video:
#   cv2.VideoCapture("data/videos/demo_fight.mp4")  (Phase 1)
#
# Phase 2 Integration Plan:
#   1. Add camera management UI page at /cameras
#   2. Allow adding/removing cameras from dashboard
#   3. Display multiple camera feeds simultaneously
#   4. Run AI pipeline on each camera with round-robin scheduling
#   5. Per-camera threat scores and alerts
