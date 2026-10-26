"""
SQLite Database Module
=======================
Local event and alert storage using SQLite.

Tables:
- events: All detected surveillance events
- alerts: High-priority threat alerts
- analytics: Performance metrics snapshots
"""

import sqlite3
import json
import time
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    """SQLite database for surveillance event storage."""
    
    def __init__(self, db_path):
        """
        Initialize database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._create_tables()
        logger.info(f"Database initialized: {db_path}")
    
    def _get_conn(self):
        """Get database connection with timeout and WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn
    
    def _create_tables(self):
        """Create database tables if they don't exist."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    datetime TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    threat_score REAL DEFAULT 0,
                    severity TEXT DEFAULT 'NORMAL',
                    confidence REAL DEFAULT 0,
                    source TEXT DEFAULT 'unknown',
                    person_count INTEGER DEFAULT 0,
                    object_count INTEGER DEFAULT 0,
                    weapon_detected INTEGER DEFAULT 0,
                    violence_score REAL DEFAULT 0,
                    crowd_anomaly REAL DEFAULT 0,
                    persistence_score REAL DEFAULT 0,
                    snapshot_path TEXT,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    datetime TEXT NOT NULL,
                    threat_level TEXT NOT NULL,
                    threat_score REAL NOT NULL,
                    source TEXT DEFAULT 'unknown',
                    detected_objects TEXT,
                    reason TEXT,
                    confidence REAL DEFAULT 0,
                    snapshot_path TEXT,
                    event_duration REAL DEFAULT 0,
                    breakdown TEXT,
                    acknowledged INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    fps REAL DEFAULT 0,
                    inference_ms REAL DEFAULT 0,
                    pipeline_ms REAL DEFAULT 0,
                    threat_score REAL DEFAULT 0,
                    person_count INTEGER DEFAULT 0,
                    detection_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
                CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts(threat_level);
            """)
            conn.commit()
        finally:
            conn.close()
    
    # ── Event Operations ────────────────────────────────────────
    
    def save_event(self, event_data):
        """Save a detection event."""
        conn = self._get_conn()
        try:
            ts = event_data.get("timestamp", time.time())
            conn.execute("""
                INSERT INTO events (
                    timestamp, datetime, event_type, threat_score, severity,
                    confidence, source, person_count, object_count,
                    weapon_detected, violence_score, crowd_anomaly,
                    persistence_score, snapshot_path, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts,
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                event_data.get("event_type", "detection"),
                event_data.get("threat_score", 0),
                event_data.get("severity", "NORMAL"),
                event_data.get("confidence", 0),
                event_data.get("source", "unknown"),
                event_data.get("person_count", 0),
                event_data.get("object_count", 0),
                1 if event_data.get("weapon_detected") else 0,
                event_data.get("violence_score", 0),
                event_data.get("crowd_anomaly", 0),
                event_data.get("persistence_score", 0),
                event_data.get("snapshot_path", ""),
                json.dumps(event_data.get("details", {})),
            ))
            conn.commit()
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        finally:
            conn.close()
    
    def get_events(self, limit=50, offset=0, severity=None, event_type=None,
                   start_date=None, end_date=None):
        """Get events with optional filters."""
        conn = self._get_conn()
        try:
            query = "SELECT * FROM events WHERE 1=1"
            params = []
            
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            if event_type:
                query += " AND event_type = ?"
                params.append(event_type)
            if start_date:
                query += " AND datetime >= ?"
                params.append(start_date)
            if end_date:
                query += " AND datetime <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    
    def get_event_count(self, severity=None):
        """Get total event count."""
        conn = self._get_conn()
        try:
            if severity:
                row = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE severity = ?", (severity,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
            return row[0]
        finally:
            conn.close()
    
    # ── Alert Operations ────────────────────────────────────────
    
    def save_alert(self, alert_data):
        """Save a threat alert."""
        conn = self._get_conn()
        try:
            ts = alert_data.get("timestamp", time.time())
            conn.execute("""
                INSERT INTO alerts (
                    timestamp, datetime, threat_level, threat_score,
                    source, detected_objects, reason, confidence,
                    snapshot_path, event_duration, breakdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts,
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                alert_data.get("threat_level", "UNKNOWN"),
                alert_data.get("threat_score", 0),
                alert_data.get("source", "unknown"),
                json.dumps(alert_data.get("detected_objects", [])),
                alert_data.get("reason", ""),
                alert_data.get("confidence", 0),
                alert_data.get("snapshot_path", ""),
                alert_data.get("event_duration", 0),
                json.dumps(alert_data.get("breakdown", {})),
            ))
            conn.commit()
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        finally:
            conn.close()
    
    def get_alerts(self, limit=50, offset=0, threat_level=None,
                   start_date=None, end_date=None):
        """Get alerts with optional filters."""
        conn = self._get_conn()
        try:
            query = "SELECT * FROM alerts WHERE 1=1"
            params = []
            
            if threat_level:
                query += " AND threat_level = ?"
                params.append(threat_level)
            if start_date:
                query += " AND datetime >= ?"
                params.append(start_date)
            if end_date:
                query += " AND datetime <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            rows = conn.execute(query, params).fetchall()
            alerts = []
            for row in rows:
                alert = dict(row)
                # Parse JSON fields
                try:
                    alert["detected_objects"] = json.loads(alert.get("detected_objects", "[]"))
                except (json.JSONDecodeError, TypeError):
                    alert["detected_objects"] = []
                try:
                    alert["breakdown"] = json.loads(alert.get("breakdown", "{}"))
                except (json.JSONDecodeError, TypeError):
                    alert["breakdown"] = {}
                alerts.append(alert)
            return alerts
        finally:
            conn.close()
    
    def get_alert_count(self, threat_level=None):
        """Get total alert count."""
        conn = self._get_conn()
        try:
            if threat_level:
                row = conn.execute(
                    "SELECT COUNT(*) FROM alerts WHERE threat_level = ?",
                    (threat_level,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()
            return row[0]
        finally:
            conn.close()
    
    def acknowledge_alert(self, alert_id):
        """Mark an alert as acknowledged."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,)
            )
            conn.commit()
        finally:
            conn.close()
    
    # ── Analytics Operations ────────────────────────────────────
    
    def save_analytics(self, data):
        """Save analytics snapshot."""
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO analytics (
                    timestamp, fps, inference_ms, pipeline_ms,
                    threat_score, person_count, detection_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                time.time(),
                data.get("fps", 0),
                data.get("inference_ms", 0),
                data.get("pipeline_ms", 0),
                data.get("threat_score", 0),
                data.get("person_count", 0),
                data.get("detection_count", 0),
            ))
            conn.commit()
        finally:
            conn.close()
    
    def get_analytics(self, limit=500):
        """Get recent analytics data."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM analytics ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    
    # ── Statistics ──────────────────────────────────────────────
    
    def get_statistics(self):
        """Get overall statistics for the analytics page."""
        conn = self._get_conn()
        try:
            stats = {}
            
            # Event counts by severity
            for severity in ["NORMAL", "SUSPICIOUS", "HIGH_RISK", "CRITICAL"]:
                row = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE severity = ?", (severity,)
                ).fetchone()
                stats[f"events_{severity.lower()}"] = row[0]
            
            stats["events_total"] = conn.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]
            
            # Alert counts
            stats["alerts_total"] = conn.execute(
                "SELECT COUNT(*) FROM alerts"
            ).fetchone()[0]
            
            for level in ["HIGH_RISK", "CRITICAL"]:
                row = conn.execute(
                    "SELECT COUNT(*) FROM alerts WHERE threat_level = ?", (level,)
                ).fetchone()
                stats[f"alerts_{level.lower()}"] = row[0]
            
            # Average threat score
            row = conn.execute(
                "SELECT AVG(threat_score) FROM events"
            ).fetchone()
            stats["avg_threat_score"] = round(row[0], 1) if row[0] else 0
            
            # Average FPS
            row = conn.execute(
                "SELECT AVG(fps) FROM analytics WHERE fps > 0"
            ).fetchone()
            stats["avg_fps"] = round(row[0], 1) if row[0] else 0
            
            # Average inference time
            row = conn.execute(
                "SELECT AVG(inference_ms) FROM analytics WHERE inference_ms > 0"
            ).fetchone()
            stats["avg_inference_ms"] = round(row[0], 1) if row[0] else 0
            
            return stats
        finally:
            conn.close()
    
    def clear_all(self):
        """Clear all data (for testing/demo reset)."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                DELETE FROM events;
                DELETE FROM alerts;
                DELETE FROM analytics;
            """)
            conn.commit()
            logger.info("Database cleared")
        finally:
            conn.close()
