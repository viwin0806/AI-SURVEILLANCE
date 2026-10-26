"""
Video Source Manager
=====================
Manages video input sources: uploaded files, webcam, demo videos, and RTSP (Phase 2).
Features threaded, non-blocking capture for webcams and live streams to prevent
freezing, buffer overflow, and dropped-frame disconnects.
"""

import os
import cv2
import time
import logging
import threading

logger = logging.getLogger(__name__)


class VideoSource:
    """
    Video source manager supporting multiple input types.
    
    Supported sources:
    - Uploaded video files (MP4, AVI, MKV, etc.)
    - Webcam (device index, with background threaded frame grabber)
    - Demo videos from data/videos/
    - RTSP streams (Phase 2 — threaded stream ingestion)
    """
    
    def __init__(self, video_dir="data/videos"):
        self.video_dir = video_dir
        self.cap = None
        self.source_type = None
        self.source_name = None
        self.source_path = None
        self.is_open = False
        self.total_frames = 0
        self.current_frame = 0
        self.fps = 30
        self.width = 0
        self.height = 0
        self.loop = False  # Loop video for demo mode
        
        # Threaded capture state for live feeds (webcam, rtsp)
        self._thread = None
        self._stopped = False
        self._lock = threading.Lock()
        self._latest_frame = None
        self._has_frame = False
        self._consecutive_fails = 0
        self._is_live = False
        self._new_frame_event = threading.Event()
    
    def open_file(self, filepath, loop=False):
        """Open a video file."""
        self.close()
        
        if not os.path.exists(filepath):
            logger.error(f"Video file not found: {filepath}")
            return False
        
        self.cap = cv2.VideoCapture(filepath)
        if not self.cap.isOpened():
            logger.error(f"Failed to open video: {filepath}")
            return False
        
        self.source_type = "file"
        self.source_name = os.path.basename(filepath)
        self.source_path = filepath
        self.is_open = True
        self.loop = loop
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.current_frame = 0
        self._is_live = False
        
        logger.info(
            f"Opened video: {self.source_name} "
            f"({self.width}x{self.height}, {self.fps:.0f}fps, "
            f"{self.total_frames} frames)"
        )
        return True
    
    def open_webcam(self, device_index=0):
        """
        Open webcam with threaded continuous capture.
        
        Attempts opening with DirectShow on Windows for low latency,
        with fallback to default backend and device indices.
        Uses a dedicated reader thread to prevent buffer overflows
        and ensure continuous real-time video streaming without freezing.
        """
        self.close()
        
        # Candidate device indices to try (try requested, then fallback)
        try_indices = [device_index]
        for alt_idx in [0, 1, 2]:
            if alt_idx not in try_indices:
                try_indices.append(alt_idx)
        
        cap = None
        chosen_idx = device_index
        
        for dev_idx in try_indices:
            # Try DirectShow first on Windows, then standard
            backends = [cv2.CAP_DSHOW, cv2.CAP_ANY] if os.name == "nt" else [cv2.CAP_ANY]
            for api in backends:
                try:
                    c = cv2.VideoCapture(dev_idx, api)
                    if c.isOpened():
                        # Set buffer size to 1 to eliminate frame lag
                        c.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        # Force MJPG codec — 10x faster frame delivery on Windows
                        c.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                        c.set(cv2.CAP_PROP_FPS, 30)
                        c.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        
                        # Warm up: test reading frames
                        warmed_up = False
                        for _ in range(3):
                            ret, initial_frame = c.read()
                            if ret and initial_frame is not None:
                                warmed_up = True
                                break
                            time.sleep(0.05)
                        
                        if warmed_up:
                            cap = c
                            chosen_idx = dev_idx
                            break
                        else:
                            c.release()
                except Exception as e:
                    logger.debug(f"Failed to open camera index {dev_idx} with API {api}: {e}")
            
            if cap is not None:
                break
        
        if cap is None:
            logger.error(f"Failed to open webcam (tried indices: {try_indices})")
            return False
        
        self.cap = cap
        self.source_type = "webcam"
        self.source_name = f"Webcam {chosen_idx}"
        self.source_path = str(chosen_idx)
        self.is_open = True
        self.loop = False
        self.total_frames = -1  # Continuous live stream
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        if self.fps <= 0 or self.fps > 120:
            self.fps = 30
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        self.current_frame = 0
        self._is_live = True
        
        # Store initial frame
        with self._lock:
            self._latest_frame = initial_frame
            self._has_frame = True
            self._consecutive_fails = 0
            self._stopped = False
        
        # Start background capture thread to continuously drain camera
        self._thread = threading.Thread(
            target=self._capture_worker,
            name=f"WebcamCapture-{chosen_idx}",
            daemon=True,
        )
        self._thread.start()
        
        logger.info(
            f"Opened webcam: {self.source_name} ({self.width}x{self.height}, "
            f"threaded reader active)"
        )
        return True
    
    def open_demo(self, demo_key, video_dir=None):
        """Open a demo video by key."""
        vdir = video_dir or self.video_dir
        
        # Check for demo videos
        demo_files = self.get_available_demos(vdir)
        if demo_key in demo_files:
            filepath = demo_files[demo_key]
            return self.open_file(filepath, loop=True)
        
        logger.error(f"Demo video not found: {demo_key}")
        return False
    
    def open_rtsp(self, url):
        """
        Open RTSP stream (Phase 2) with threaded ingestion.
        """
        self.close()
        
        self.cap = cv2.VideoCapture(url)
        if not self.cap.isOpened():
            logger.error(f"Failed to open RTSP stream: {url}")
            return False
        
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.source_type = "rtsp"
        self.source_name = url
        self.source_path = url
        self.is_open = True
        self.loop = False
        self.total_frames = -1
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        self.current_frame = 0
        self._is_live = True
        
        # Read initial frame
        ret, initial_frame = self.cap.read()
        with self._lock:
            self._latest_frame = initial_frame if ret else None
            self._has_frame = ret
            self._consecutive_fails = 0
            self._stopped = False
        
        self._thread = threading.Thread(
            target=self._capture_worker,
            name="RTSPCapture",
            daemon=True,
        )
        self._thread.start()
        
        logger.info(f"Opened RTSP stream: {url} ({self.width}x{self.height})")
        return True
    
    def _capture_worker(self):
        """
        Background worker thread continuously grabbing frames for live feeds.
        
        This prevents OpenCV's camera buffer from overflowing, ensures
        sub-millisecond frame delivery to the processing pipeline, and
        gracefully handles transient frame drops without stopping the feed.
        """
        logger.info(f"Capture worker started for {self.source_name}")
        while not self._stopped and self.is_open:
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.01)
                continue
            
            try:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self._lock:
                        self._latest_frame = frame
                        self._has_frame = True
                        self._consecutive_fails = 0
                    self._new_frame_event.set()
                else:
                    self._consecutive_fails += 1
                    # Tolerate transient camera hiccups (up to 150 consecutive fails ~ 3-5 sec)
                    if self._consecutive_fails > 150:
                        logger.warning(
                            f"Live feed {self.source_name} disconnected: "
                            f"{self._consecutive_fails} consecutive read failures."
                        )
                        self.is_open = False
                        break
                    time.sleep(0.01)
            except Exception as e:
                logger.error(f"Error in capture worker: {e}")
                time.sleep(0.01)
        
        logger.info(f"Capture worker terminated for {self.source_name}")
    
    def read_frame(self):
        """
        Read next frame from source.
        
        For live sources (webcam, RTSP), returns the latest frame instantly
        from the background capture worker.
        For file sources, synchronously reads the next frame with loop support.
        
        Returns:
            (success, frame) tuple
        """
        if not self.is_open:
            return False, None
        
        # ── Live sources (Webcam / RTSP) ──
        if self._is_live:
            # Wait for fresh frame from camera worker (up to 150ms for 10-15 FPS cameras)
            self._new_frame_event.wait(timeout=0.15)
            self._new_frame_event.clear()
            with self._lock:
                if self._has_frame and self._latest_frame is not None:
                    self.current_frame += 1
                    return True, self._latest_frame.copy()
            return False, None
        
        # ── File sources ──
        if self.cap is None:
            return False, None
        
        ret, frame = self.cap.read()
        
        if not ret:
            if self.loop and self.source_type == "file":
                # Loop back to beginning
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.current_frame = 0
                ret, frame = self.cap.read()
                if not ret:
                    return False, None
            else:
                self.is_open = False
                return False, None
        
        self.current_frame += 1
        return True, frame
    
    def get_progress(self):
        """Get video progress (for file sources)."""
        if self.source_type != "file" or self.total_frames <= 0:
            return {"progress": 0, "current": 0, "total": 0}
        
        return {
            "progress": round(self.current_frame / self.total_frames * 100, 1),
            "current": self.current_frame,
            "total": self.total_frames,
        }
    
    def get_available_demos(self, video_dir=None):
        """Get available demo video files."""
        vdir = video_dir or self.video_dir
        demos = {}
        
        if not os.path.exists(vdir):
            return demos
        
        video_extensions = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm"}
        
        for filename in sorted(os.listdir(vdir)):
            ext = os.path.splitext(filename)[1].lower()
            if ext in video_extensions:
                key = os.path.splitext(filename)[0]
                demos[key] = os.path.join(vdir, filename)
        
        return demos
    
    def close(self):
        """Close current video source cleanly."""
        self._stopped = True
        
        # Wait for worker thread to exit
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
            self._thread = None
        
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        
        with self._lock:
            self._latest_frame = None
            self._has_frame = False
            self._consecutive_fails = 0
        
        self.is_open = False
        self.source_type = None
        self.source_name = None
        self.current_frame = 0
        self._is_live = False
    
    def get_status(self):
        """Get video source status."""
        return {
            "is_open": self.is_open,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "resolution": f"{self.width}x{self.height}" if self.is_open else "N/A",
            "fps": round(self.fps, 1),
            "progress": self.get_progress() if self.source_type == "file" else None,
        }
