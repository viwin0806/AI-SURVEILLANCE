/**
 * Dashboard JavaScript — Real-time Surveillance Dashboard
 * 
 * Handles SocketIO communication, video frame rendering,
 * threat gauge animation, and dashboard state management.
 */

// ── SocketIO Connection ────────────────────────────────────────
const socket = io({
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 10,
});

// ── State ──────────────────────────────────────────────────────
let isProcessing = false;
let currentThreatLevel = 'NORMAL';
let alertsQueue = [];

// ── SocketIO Event Handlers ────────────────────────────────────

socket.on('connect', () => {
    console.log('Connected to server');
    updateConnectionStatus(true);
    socket.emit('request_status');
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    updateConnectionStatus(false);
});

socket.on('video_frame', (data) => {
    try {
        if (data.stats) {
            updateDashboard(data.stats);
        }
        // Fallback only if base64 frame is provided and stream isn't already active
        if (data.frame) {
            const img = document.getElementById('videoFrame');
            if (img && (!img.src || !img.src.includes('/video_feed'))) {
                displayFrame(data.frame);
            }
        }
    } catch (e) {
        console.error('Frame processing error:', e);
    }
});

socket.on('new_alert', (alert) => {
    try {
        addAlertToPanel(alert);
        showAlertNotification(alert);
    } catch (e) {
        console.error('Alert processing error:', e);
    }
});

socket.on('system_status', (status) => {
    updateSystemStatus(status);
});

socket.on('processing_stopped', () => {
    isProcessing = false;
    updateProcessingUI(false);
});

// ── Video Frame Streaming ──────────────────────────────────────

function startVideoStream() {
    const img = document.getElementById('videoFrame');
    const placeholder = document.getElementById('videoPlaceholder');
    if (img) {
        img.onerror = () => {
            console.warn('Video stream interrupted, reconnecting...');
            if (isProcessing) {
                setTimeout(() => {
                    if (isProcessing) {
                        img.src = '/video_feed?t=' + Date.now();
                    }
                }, 1000);
            }
        };
        // Point directly to high-performance native MJPEG route
        img.src = '/video_feed?t=' + Date.now();
        img.style.display = 'block';
    }
    if (placeholder) {
        placeholder.style.display = 'none';
    }
}

function stopVideoStream() {
    const img = document.getElementById('videoFrame');
    const placeholder = document.getElementById('videoPlaceholder');
    if (img) {
        img.src = '';
        img.style.display = 'none';
    }
    if (placeholder) {
        placeholder.style.display = 'flex';
    }
}

function displayFrame(frameBase64) {
    const img = document.getElementById('videoFrame');
    const placeholder = document.getElementById('videoPlaceholder');
    if (img) {
        img.src = 'data:image/jpeg;base64,' + frameBase64;
        img.style.display = 'block';
    }
    if (placeholder) {
        placeholder.style.display = 'none';
    }
}

// ── Dashboard Updates ──────────────────────────────────────────

function updateDashboard(stats) {
    if (!stats) return;
    
    // Detection stats
    setText('personCount', stats.person_count || 0);
    setText('objectCount', stats.object_count || 0);
    
    // Weapon status
    const weaponEl = document.getElementById('weaponStatus');
    if (stats.weapon_detected) {
        weaponEl.textContent = '⚠️ DETECTED';
        weaponEl.style.color = 'var(--color-danger)';
    } else {
        weaponEl.textContent = 'None';
        weaponEl.style.color = 'var(--color-text-secondary)';
    }
    
    // Violence probability
    const violenceProb = stats.violence_probability || 0;
    const violenceEl = document.getElementById('violenceProb');
    violenceEl.textContent = (violenceProb * 100).toFixed(0) + '%';
    if (violenceProb > 0.5) violenceEl.style.color = 'var(--color-danger)';
    else if (violenceProb > 0.25) violenceEl.style.color = 'var(--color-warning)';
    else violenceEl.style.color = 'var(--color-success)';
    
    // Crowd density
    setText('crowdDensity', stats.crowd_density || '—');
    
    // Persistence status
    const persistEl = document.getElementById('persistenceStatus');
    if (stats.is_persistent) {
        persistEl.textContent = '⚠️ ACTIVE';
        persistEl.style.color = 'var(--color-danger)';
    } else {
        persistEl.textContent = 'Normal';
        persistEl.style.color = 'var(--color-text-secondary)';
    }
    
    // Threat gauge
    updateThreatGauge(stats.threat_score || 0, stats.threat_level || 'NORMAL');
    
    // Score breakdown
    const rawScores = stats.threat?.raw_scores || {};
    updateBreakdown('breakWeapon', 'breakWeaponVal', rawScores.weapon_presence || 0);
    updateBreakdown('breakViolence', 'breakViolenceVal', rawScores.violence_score || 0);
    updateBreakdown('breakCrowd', 'breakCrowdVal', rawScores.crowd_anomaly || 0);
    updateBreakdown('breakMovement', 'breakMovementVal', rawScores.movement_intensity || 0);
    updateBreakdown('breakPersistence', 'breakPersistenceVal', rawScores.temporal_persistence || 0);
    
    // System stats
    setText('sysInference', (stats.inference_time_ms || 0).toFixed(1) + ' ms');
    setText('sysFPS', (stats.pipeline_fps || 0).toFixed(1));
    setText('sysFrames', stats.frame_number || 0);
    
    // Header FPS
    const headerFPS = document.getElementById('headerFPS');
    if (headerFPS) headerFPS.textContent = (stats.pipeline_fps || 0).toFixed(1);
    
    // Video progress
    if (stats.detection) {
        // source info can come from video_source status via polling
    }
}

function updateThreatGauge(score, level) {
    score = Math.max(0, Math.min(100, score));
    
    // Update score display
    const scoreDisplay = document.getElementById('threatScoreDisplay');
    scoreDisplay.textContent = Math.round(score);
    
    // Update gauge arc
    const arc = document.getElementById('gaugeArc');
    const circumference = 2 * Math.PI * 85; // ~534
    const offset = circumference - (score / 100) * circumference;
    arc.style.strokeDashoffset = offset;
    
    // Color based on threat level
    const colors = {
        'NORMAL': '#22c55e',
        'SUSPICIOUS': '#eab308',
        'HIGH_RISK': '#f97316',
        'CRITICAL': '#ef4444',
    };
    const color = colors[level] || '#22c55e';
    arc.style.stroke = color;
    scoreDisplay.style.color = color;
    
    // Update level badge
    const badge = document.getElementById('threatLevelBadge');
    badge.textContent = level.replace('_', ' ');
    badge.className = 'threat-level-badge threat-' + level.toLowerCase().replace('_', '-');
    
    // Pulse animation on high threat
    const gauge = document.getElementById('threatGauge');
    if (level === 'CRITICAL') {
        gauge.classList.add('pulse-danger');
    } else {
        gauge.classList.remove('pulse-danger');
    }
    
    currentThreatLevel = level;
}

function updateBreakdown(barId, valId, value) {
    const bar = document.getElementById(barId);
    const val = document.getElementById(valId);
    if (bar) bar.style.width = Math.min(value, 100) + '%';
    if (val) val.textContent = value.toFixed(0) + '%';
    
    // Color the bar based on value
    if (bar) {
        if (value > 70) bar.style.background = 'var(--color-danger)';
        else if (value > 40) bar.style.background = 'var(--color-warning)';
        else bar.style.background = 'var(--color-primary)';
    }
}

// ── Video Controls ─────────────────────────────────────────────

function uploadVideo() {
    document.getElementById('videoFileInput').click();
}

async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('video', file);
    
    showLoading('Uploading and starting AI analysis...');
    
    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        
        if (data.error) {
            hideLoading();
            alert('Error: ' + data.error);
            return;
        }
        
        isProcessing = true;
        updateProcessingUI(true);
        setText('sourceLabel', file.name);
        setText('sysSource', file.name);
        hideLoading();
        
    } catch (e) {
        hideLoading();
        alert('Upload failed: ' + e.message);
    }
    
    event.target.value = '';
}

async function startWebcam() {
    showLoading('Starting webcam...');
    
    try {
        const res = await fetch('/api/webcam', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({device: 0}),
        });
        const data = await res.json();
        
        if (data.error) {
            hideLoading();
            alert('Error: ' + data.error);
            return;
        }
        
        isProcessing = true;
        updateProcessingUI(true);
        const srcName = data.source || 'Webcam';
        setText('sourceLabel', srcName);
        setText('sysSource', srcName);
        hideLoading();
        
    } catch (e) {
        hideLoading();
        alert('Failed to start webcam: ' + e.message);
    }
}

async function startDemo() {
    // First check available demos
    try {
        const res = await fetch('/api/demos');
        const data = await res.json();
        
        if (!data.demos || data.demos.length === 0) {
            const msg = `No demo videos found.\n\nPlease place MP4 video files in:\n${data.video_dir}\n\nYou can use any video with people/crowd scenes for demonstration.`;
            alert(msg);
            return;
        }
        
        if (data.demos.length === 1) {
            // Only one demo — start it directly
            startDemoVideo(data.demos[0].key);
        } else {
            // Show selection modal
            showDemoModal(data.demos);
        }
    } catch (e) {
        alert('Failed to load demos: ' + e.message);
    }
}

async function startDemoVideo(demoKey) {
    closeDemoModal();
    showLoading('Starting Demo Mode — loading AI model and video...');
    
    try {
        const res = await fetch('/api/demo', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({demo_key: demoKey}),
        });
        const data = await res.json();
        
        if (data.error) {
            hideLoading();
            alert('Error: ' + data.error);
            return;
        }
        
        isProcessing = true;
        updateProcessingUI(true);
        setText('sourceLabel', 'Demo: ' + demoKey);
        setText('sysSource', 'Demo: ' + demoKey);
        
        // Show demo banner
        const banner = document.getElementById('demoBanner');
        if (banner) banner.style.display = 'block';
        
        hideLoading();
        
    } catch (e) {
        hideLoading();
        alert('Failed to start demo: ' + e.message);
    }
}

async function stopProcessing() {
    try {
        await fetch('/api/stop', {method: 'POST'});
        isProcessing = false;
        updateProcessingUI(false);
        
        const banner = document.getElementById('demoBanner');
        if (banner) banner.style.display = 'none';
    } catch (e) {
        console.error('Failed to stop:', e);
    }
}

// ── Demo Modal ─────────────────────────────────────────────────

function showDemoModal(demos) {
    const modal = document.getElementById('demoModal');
    const body = document.getElementById('demoModalBody');
    
    let html = '<div class="demo-list">';
    for (const demo of demos) {
        html += `
        <div class="demo-item" onclick="startDemoVideo('${demo.key}')">
            <div class="demo-item-info">
                <strong>${demo.key.replace(/_/g, ' ')}</strong>
                <p>${demo.description}</p>
                <span class="text-muted">Expected: ${demo.expected_threat}</span>
            </div>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        </div>`;
    }
    html += '</div>';
    
    body.innerHTML = html;
    modal.style.display = 'flex';
}

function closeDemoModal() {
    document.getElementById('demoModal').style.display = 'none';
}

// ── Alert Panel ────────────────────────────────────────────────

function addAlertToPanel(alert) {
    if (!alert) return;
    const list = document.getElementById('alertsList');
    if (!list) return;
    
    // Remove empty state
    const empty = list.querySelector('.empty-state');
    if (empty) empty.remove();
    
    const levelStr = String(alert.threat_level || 'UNKNOWN');
    const levelClass = levelStr.toLowerCase().replace(/_/g, '-');
    
    const card = document.createElement('div');
    card.className = `alert-item alert-${levelClass} slide-in`;
    card.innerHTML = `
        <div class="alert-item-header">
            <span class="severity-badge severity-${levelClass}">${levelStr.replace(/_/g, ' ')}</span>
            <span class="alert-item-time">${alert.datetime || 'Now'}</span>
        </div>
        <div class="alert-item-body">
            <span class="alert-item-score">Score: ${(alert.threat_score || 0).toFixed(0)}</span>
            <span class="alert-item-reason">${alert.reason || ''}</span>
        </div>
    `;
    
    list.insertBefore(card, list.firstChild);
    
    // Keep only last 10 alerts in panel
    while (list.children.length > 10) {
        list.removeChild(list.lastChild);
    }
}

function showAlertNotification(alert) {
    if (!alert) return;
    const levelStr = String(alert.threat_level || 'ALERT').replace(/_/g, ' ');
    const scoreVal = typeof alert.threat_score === 'number' ? alert.threat_score.toFixed(0) : '0';
    
    // Browser notification
    try {
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(`🚨 ${levelStr} ALERT`, {
                body: `Score: ${scoreVal}/100 — ${alert.reason || 'Threat detected'}`,
                icon: '/static/img/alert-icon.png',
            });
        }
    } catch (e) {
        console.warn('Browser notification error:', e);
    }
    
    // In-app notification
    try {
        const notif = document.createElement('div');
        notif.className = `notification notification-danger notification-show`;
        notif.innerHTML = `🚨 <strong>${levelStr}</strong> — Score: ${scoreVal}/100`;
        document.body.appendChild(notif);
        setTimeout(() => {
            notif.classList.remove('notification-show');
            setTimeout(() => notif.remove(), 300);
        }, 5000);
    } catch (e) {
        console.warn('In-app notification error:', e);
    }
}

// ── UI Helpers ──────────────────────────────────────────────────

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function updateProcessingUI(processing) {
    const btnStop = document.getElementById('btnStop');
    const btnUpload = document.getElementById('btnUpload');
    const btnWebcam = document.getElementById('btnWebcam');
    const btnDemo = document.getElementById('btnDemo');
    const status = document.getElementById('processingStatus');
    
    if (processing) {
        if (btnStop) btnStop.style.display = 'inline-flex';
        if (btnUpload) btnUpload.style.display = 'none';
        if (btnWebcam) btnWebcam.style.display = 'none';
        if (btnDemo) btnDemo.style.display = 'none';
        if (status) status.innerHTML = '<span class="status-dot status-online"></span> Processing';
        
        startVideoStream();
    } else {
        if (btnStop) btnStop.style.display = 'none';
        if (btnUpload) btnUpload.style.display = 'inline-flex';
        if (btnWebcam) btnWebcam.style.display = 'inline-flex';
        if (btnDemo) btnDemo.style.display = 'inline-flex';
        if (status) status.innerHTML = '<span class="status-dot status-offline"></span> Idle';
        
        stopVideoStream();
    }
}

function updateConnectionStatus(connected) {
    const aiStatus = document.getElementById('headerAIStatus');
    if (aiStatus) {
        if (connected) {
            aiStatus.innerHTML = '<span class="status-dot status-online"></span> Online';
        } else {
            aiStatus.innerHTML = '<span class="status-dot status-offline"></span> Offline';
        }
    }
}

function updateSystemStatus(status) {
    if (status.ai_ready) {
        setText('sysModel', 'YOLOv8n ✓');
        const aiStatus = document.getElementById('headerAIStatus');
        if (aiStatus) aiStatus.innerHTML = '<span class="status-dot status-online"></span> Ready';
    }
    if (status.is_processing) {
        isProcessing = true;
        updateProcessingUI(true);
    }
    if (status.pipeline) {
        const det = status.pipeline.detector || {};
        setText('sysDevice', det.device || '—');
    }
}

function showLoading(msg) {
    let overlay = document.getElementById('loadingOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'loadingOverlay';
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="loading-content">
                <div class="spinner"></div>
                <p id="loadingMsg">${msg}</p>
            </div>`;
        document.body.appendChild(overlay);
    } else {
        document.getElementById('loadingMsg').textContent = msg;
        overlay.style.display = 'flex';
    }
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.style.display = 'none';
}

// ── Status Polling ─────────────────────────────────────────────

async function pollStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        if (data.ai_ready) {
            setText('sysModel', 'YOLOv8n ✓');
        }
        
        if (data.pipeline && data.pipeline.detector) {
            setText('sysDevice', data.pipeline.detector.device || '—');
        }
        
        if (data.video_source) {
            const vs = data.video_source;
            if (vs.progress && vs.progress.total > 0) {
                const prog = document.getElementById('videoProgress');
                const fill = document.getElementById('progressFill');
                const text = document.getElementById('progressText');
                if (prog) prog.style.display = 'flex';
                if (fill) fill.style.width = vs.progress.progress + '%';
                if (text) text.textContent = vs.progress.progress.toFixed(0) + '%';
            }
        }
    } catch (e) {
        // Silent fail
    }
}

// ── Request Notification Permission ────────────────────────────
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}

// ── Periodic Status Poll ───────────────────────────────────────
setInterval(pollStatus, 5000);
pollStatus();
