"""
AI-Driven Intelligent Surveillance Framework
=============================================
Main Flask Application with SocketIO for real-time surveillance.

Academic Research Prototype — Not for operational deployment.

Run: python app.py
Dashboard: http://localhost:5000
"""

import os
import sys
import time
import json
import base64
import logging
import threading
from datetime import datetime

import cv2
import numpy as np
from flask import (
    Flask, render_template, request, jsonify, send_from_directory, Response
)
from flask_socketio import SocketIO, emit

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from config import runtime
from core.database import Database
from core.video_source import VideoSource
from core.alert_manager import AlertManager
from core.event_manager import EventManager

# ── Logging Setup ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ── Flask App Setup ─────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max upload

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Core Components ─────────────────────────────────────────────
db = Database(config.DB_PATH)
video_source = VideoSource(config.VIDEO_DIR)
alert_manager = AlertManager(
    db=db,
    snapshot_dir=config.SNAPSHOT_DIR,
    max_per_minute=config.ALERT_MAX_PER_MINUTE,
    dedup_seconds=config.ALERT_DEDUP_SECONDS,
)
event_manager = EventManager(db=db, log_interval=3.0)

# ── AI Pipeline (lazy loaded) ──────────────────────────────────
pipeline = None
pipeline_lock = threading.Lock()
processing_thread = None
stop_processing = threading.Event()

# ── Latest analysis result (for API polling) ────────────────────
latest_result = {}
latest_result_lock = threading.Lock()

# ── Frame streaming state (MJPEG) ──────────────────────────────
latest_frame_jpeg = None
latest_frame_id = 0
latest_frame_lock = threading.Lock()
frame_condition = threading.Condition(latest_frame_lock)

# Analytics counters
analytics_counter = 0
ANALYTICS_LOG_INTERVAL = 30  # Log analytics every N frames


def get_pipeline():
    """Lazy-load the AI pipeline."""
    global pipeline
    if pipeline is None:
        with pipeline_lock:
            if pipeline is None:
                logger.info("Loading AI Pipeline (first request)...")
                try:
                    from ai.pipeline import SurveillancePipeline
                    pipeline = SurveillancePipeline(config)
                    logger.info("AI Pipeline loaded successfully!")
                except Exception as e:
                    logger.error(f"Failed to load AI Pipeline: {e}")
                    raise
    return pipeline


# ── Alert Callback ──────────────────────────────────────────────
def on_alert(alert):
    """Push alert to connected clients via SocketIO."""
    socketio.emit("new_alert", alert, namespace="/")


alert_manager.register_callback(on_alert)


# ── Video Processing Loop ──────────────────────────────────────
def processing_loop():
    """Main video processing loop running in a background thread."""
    global latest_result, analytics_counter, latest_frame_jpeg, latest_frame_id
    
    pipe = get_pipeline()
    frame_delay = 1.0 / runtime.processing_fps
    
    logger.info(f"Processing started: {video_source.source_name}")
    runtime.is_running = True
    
    frame_count = 0
    stats_emit_counter = 0
    
    while not stop_processing.is_set() and video_source.is_open:
        loop_start = time.time()
        
        # Read frame
        ret, frame = video_source.read_frame()
        if not ret:
            if video_source.source_type == "file" and not video_source.loop:
                logger.info("Video playback completed")
                break
            time.sleep(0.01)
            continue
        
        frame_count += 1
        
        # Skip frames if configured
        if config.FRAME_SKIP > 1 and frame_count % config.FRAME_SKIP != 0:
            continue
        
        # Resize frame for processing
        h, w = frame.shape[:2]
        max_w, max_h = config.MAX_DISPLAY_WIDTH, config.MAX_DISPLAY_HEIGHT
        if w > max_w or h > max_h:
            scale = min(max_w / w, max_h / h)
            frame = cv2.resize(frame, None, fx=scale, fy=scale)
        
        # Run AI pipeline
        try:
            result = pipe.process_frame(frame)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            continue
        
        # Store latest result
        with latest_result_lock:
            # Remove frame from stored result (too large for JSON)
            result_copy = {k: v for k, v in result.items() if k != "annotated_frame"}
            latest_result = result_copy
        
        # Check for alerts
        annotated = result.get("annotated_frame")
        raw_frame = annotated if annotated is not None else frame
        alert_manager.check_and_alert(
            result, frame=raw_frame, source_name=video_source.source_name or "unknown"
        )
        
        # Log events
        event_manager.log_event(
            result, source_name=video_source.source_name or "unknown"
        )
        
        # Log analytics periodically
        analytics_counter += 1
        if analytics_counter % ANALYTICS_LOG_INTERVAL == 0:
            event_manager.log_analytics(result)
        
        # Encode annotated frame for high-performance MJPEG streaming
        if annotated is not None:
            try:
                ret_enc, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 55])
                if ret_enc:
                    with frame_condition:
                        latest_frame_jpeg = buffer.tobytes()
                        latest_frame_id += 1
                        frame_condition.notify_all()
            except Exception as e:
                logger.error(f"Frame encoding error: {e}")
        
        # Emit metadata stats over SocketIO (throttled — every 3rd frame)
        stats_emit_counter += 1
        if stats_emit_counter % 3 == 0:
            try:
                socketio.emit("video_frame", {"stats": result_copy}, namespace="/")
            except Exception as e:
                logger.error(f"Socket emit error: {e}")
        
        # Rate limiting
        elapsed = time.time() - loop_start
        if elapsed < frame_delay:
            time.sleep(frame_delay - elapsed)
    
    runtime.is_running = False
    logger.info("Processing loop ended")
    with latest_frame_lock:
        frame_condition.notify_all()
    socketio.emit("processing_stopped", {}, namespace="/")


def start_processing():
    """Start the video processing thread."""
    global processing_thread, latest_frame_jpeg, latest_frame_id
    
    with latest_frame_lock:
        latest_frame_jpeg = None
        latest_frame_id = 0
    
    stop_processing.clear()
    processing_thread = threading.Thread(target=processing_loop, daemon=True)
    processing_thread.start()


def stop_processing_loop():
    """Stop the video processing thread."""
    stop_processing.set()
    with latest_frame_lock:
        frame_condition.notify_all()
    if processing_thread and processing_thread.is_alive():
        processing_thread.join(timeout=3)
    runtime.is_running = False
    video_source.close()


def generate_mjpeg_stream():
    """Generator for streaming multipart MJPEG video to browsers."""
    last_id = -1
    while runtime.is_running or not stop_processing.is_set():
        with latest_frame_lock:
            # If no new frame yet, wait for notification (up to 200ms)
            if latest_frame_id == last_id:
                frame_condition.wait(timeout=0.2)
            
            if latest_frame_jpeg is not None and latest_frame_id != last_id:
                frame_bytes = latest_frame_jpeg
                last_id = latest_frame_id
            else:
                frame_bytes = None
        
        if frame_bytes is not None:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame_bytes)).encode() + b"\r\n\r\n"
                + frame_bytes + b"\r\n"
            )
        else:
            time.sleep(0.01)


@app.route("/video_feed")
def video_feed():
    """High-performance multipart MJPEG streaming route."""
    return Response(
        generate_mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


# ═══════════════════════════════════════════════════════════════
# ROUTES — Page Views
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def dashboard():
    """Main dashboard page."""
    return render_template("dashboard.html", page="dashboard")


@app.route("/surveillance")
def surveillance():
    """Live surveillance page."""
    return render_template("dashboard.html", page="surveillance")


@app.route("/alerts")
def alerts_page():
    """Alerts page."""
    return render_template("alerts.html", page="alerts")


@app.route("/history")
def history_page():
    """Event history page."""
    return render_template("history.html", page="history")


@app.route("/analytics")
def analytics_page():
    """Analytics page."""
    return render_template("analytics.html", page="analytics")


@app.route("/settings")
def settings_page():
    """Settings page."""
    return render_template("settings.html", page="settings")


# ═══════════════════════════════════════════════════════════════
# API Routes
# ═══════════════════════════════════════════════════════════════

@app.route("/api/status")
def api_status():
    """Get system status."""
    pipe_status = {}
    try:
        if pipeline:
            pipe_status = pipeline.get_status()
    except Exception:
        pass
    
    return jsonify({
        "system": "online",
        "ai_ready": pipeline is not None and (pipeline.is_ready if pipeline else False),
        "is_processing": runtime.is_running,
        "video_source": video_source.get_status(),
        "pipeline": pipe_status,
        "config": runtime.to_dict(),
        "alert_stats": alert_manager.get_stats(),
    })


@app.route("/api/latest")
def api_latest():
    """Get latest analysis result."""
    with latest_result_lock:
        return jsonify(latest_result)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload a video file for processing."""
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400
    
    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    
    # Save uploaded file
    filename = file.filename.replace(" ", "_")
    filepath = os.path.join(config.VIDEO_DIR, filename)
    file.save(filepath)
    
    # Stop current processing
    stop_processing_loop()
    
    # Initialize pipeline
    try:
        pipe = get_pipeline()
        pipe.reset()
    except Exception as e:
        return jsonify({"error": f"Failed to load AI model: {str(e)}"}), 500
    
    # Open video
    if not video_source.open_file(filepath, loop=True):
        return jsonify({"error": "Failed to open video file"}), 500
    
    runtime.current_source = filename
    runtime.demo_mode = False
    
    # Start processing
    start_processing()
    
    return jsonify({
        "status": "processing",
        "source": filename,
        "video_info": video_source.get_status(),
    })


@app.route("/api/webcam", methods=["POST"])
def api_webcam():
    """Start webcam capture."""
    stop_processing_loop()
    
    try:
        pipe = get_pipeline()
        pipe.reset()
    except Exception as e:
        return jsonify({"error": f"Failed to load AI model: {str(e)}"}), 500
    
    device = request.json.get("device", 0) if request.json else 0
    
    if not video_source.open_webcam(device):
        return jsonify({"error": "Failed to open webcam"}), 500
    
    runtime.current_source = video_source.source_name or f"Webcam {device}"
    runtime.demo_mode = False
    
    start_processing()
    
    return jsonify({
        "status": "processing",
        "source": video_source.source_name or f"Webcam {device}",
    })


@app.route("/api/demo", methods=["POST"])
def api_demo():
    """Start demo mode with sample video."""
    stop_processing_loop()
    
    try:
        pipe = get_pipeline()
        pipe.reset()
    except Exception as e:
        return jsonify({"error": f"Failed to load AI model: {str(e)}"}), 500
    
    # Get available demos
    demos = video_source.get_available_demos(config.VIDEO_DIR)
    
    if not demos:
        return jsonify({
            "error": "No demo videos found. Place MP4 files in data/videos/ directory.",
            "video_dir": os.path.abspath(config.VIDEO_DIR),
        }), 404
    
    # Select requested demo or first available
    demo_key = request.json.get("demo_key") if request.json else None
    if demo_key and demo_key in demos:
        filepath = demos[demo_key]
    else:
        # Use first available
        demo_key = list(demos.keys())[0]
        filepath = demos[demo_key]
    
    if not video_source.open_file(filepath, loop=True):
        return jsonify({"error": f"Failed to open demo video: {demo_key}"}), 500
    
    runtime.current_source = f"Demo: {demo_key}"
    runtime.demo_mode = True
    
    start_processing()
    
    return jsonify({
        "status": "processing",
        "source": demo_key,
        "demo_mode": True,
        "available_demos": list(demos.keys()),
    })


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Stop processing."""
    stop_processing_loop()
    return jsonify({"status": "stopped"})


@app.route("/api/demos")
def api_demos():
    """List available demo videos."""
    demos = video_source.get_available_demos(config.VIDEO_DIR)
    demo_list = []
    for key, path in demos.items():
        demo_info = config.DEMO_VIDEOS.get(key, {})
        demo_list.append({
            "key": key,
            "filename": os.path.basename(path),
            "description": demo_info.get("description", key),
            "expected_threat": demo_info.get("expected_threat", "Unknown"),
        })
    return jsonify({"demos": demo_list, "video_dir": os.path.abspath(config.VIDEO_DIR)})


@app.route("/api/events")
def api_events():
    """Get events with filtering."""
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    severity = request.args.get("severity")
    event_type = request.args.get("event_type")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    
    events = db.get_events(
        limit=limit, offset=offset, severity=severity,
        event_type=event_type, start_date=start_date, end_date=end_date
    )
    total = db.get_event_count(severity=severity)
    
    return jsonify({"events": events, "total": total})


@app.route("/api/alerts_data")
def api_alerts_data():
    """Get alerts with filtering."""
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    threat_level = request.args.get("threat_level")
    
    alerts = db.get_alerts(limit=limit, offset=offset, threat_level=threat_level)
    total = db.get_alert_count(threat_level=threat_level)
    
    return jsonify({"alerts": alerts, "total": total})


@app.route("/api/alerts/<int:alert_id>/acknowledge", methods=["POST"])
def api_acknowledge_alert(alert_id):
    """Acknowledge an alert."""
    db.acknowledge_alert(alert_id)
    return jsonify({"status": "acknowledged"})


@app.route("/api/stats")
def api_stats():
    """Get statistics for analytics page."""
    stats = db.get_statistics()
    analytics = db.get_analytics(limit=200)
    
    return jsonify({
        "statistics": stats,
        "analytics": analytics,
    })


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    """Get or update settings."""
    if request.method == "GET":
        return jsonify(runtime.to_dict())
    
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Update runtime config
    if "yolo_confidence" in data:
        runtime.yolo_confidence = float(data["yolo_confidence"])
    if "processing_fps" in data:
        runtime.processing_fps = max(1, int(data["processing_fps"]))
    if "threat_weights" in data:
        runtime.update_weights(data["threat_weights"])
    if "threat_levels" in data:
        runtime.update_thresholds(data["threat_levels"])
    if "persistence_window" in data:
        runtime.persistence_window = int(data["persistence_window"])
    if "persistence_confirm" in data:
        runtime.persistence_confirm = int(data["persistence_confirm"])
    
    # Apply to pipeline if loaded
    if pipeline:
        pipeline.update_settings(data)
    
    return jsonify({"status": "updated", "config": runtime.to_dict()})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset the system (clear database, reset pipeline)."""
    stop_processing_loop()
    db.clear_all()
    if pipeline:
        pipeline.reset()
    return jsonify({"status": "reset"})


# ── Static File Serving ─────────────────────────────────────────

@app.route("/snapshots/<path:filename>")
def serve_snapshot(filename):
    """Serve alert snapshot images."""
    return send_from_directory(config.SNAPSHOT_DIR, filename)


@app.route("/videos/<path:filename>")
def serve_video(filename):
    """Serve video files."""
    return send_from_directory(config.VIDEO_DIR, filename)


# ── SocketIO Events ─────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    """Client connected."""
    logger.info("Client connected")
    emit("system_status", {
        "ai_ready": pipeline is not None and (pipeline.is_ready if pipeline else False),
        "is_processing": runtime.is_running,
    })


@socketio.on("disconnect")
def on_disconnect():
    """Client disconnected."""
    logger.info("Client disconnected")


@socketio.on("request_status")
def on_request_status():
    """Client requesting system status."""
    pipe_status = {}
    try:
        if pipeline:
            pipe_status = pipeline.get_status()
    except Exception:
        pass
    
    emit("system_status", {
        "ai_ready": pipeline is not None and (pipeline.is_ready if pipeline else False),
        "is_processing": runtime.is_running,
        "video_source": video_source.get_status(),
        "pipeline": pipe_status,
    })


# ═══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  AI-Driven Intelligent Surveillance Framework")
    print("  Academic Research Prototype")
    print("=" * 60)
    print(f"  Dashboard: http://localhost:{config.FLASK_PORT}")
    print(f"  Video Dir: {os.path.abspath(config.VIDEO_DIR)}")
    print(f"  Database:  {os.path.abspath(config.DB_PATH)}")
    print("=" * 60)
    print()
    print("  Place demo videos (MP4) in the data/videos/ folder")
    print("  Then use the dashboard to start processing")
    print()
    
    # Pre-load AI pipeline on startup
    try:
        logger.info("Pre-loading AI pipeline...")
        get_pipeline()
        logger.info("AI pipeline ready!")
    except Exception as e:
        logger.warning(f"AI pipeline will load on first use: {e}")
    
    socketio.run(
        app,
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
        allow_unsafe_werkzeug=True,
    )
