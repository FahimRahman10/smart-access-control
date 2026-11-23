// Biometric Access Control - Front-end Engine

let currentStream = null;
let isWebcamActive = false;
let audioCtx = null;

// Synthesize audio feedback via Web Audio API
function playChime(isGranted) {
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    const now = audioCtx.currentTime;
    if (isGranted) {
      // Pleasant harmonic double-beep for Access Granted
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, now); // D5
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.15); // A5
      gain.gain.setValueAtTime(0.15, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.35);
      osc.start(now);
      osc.stop(now + 0.35);
    } else {
      // Low dual warning buzzer for Access Denied
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(160, now);
      osc.frequency.setValueAtTime(120, now + 0.15);
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
      osc.start(now);
      osc.stop(now + 0.4);
    }
  } catch (e) {
    console.log("Audio not supported or permitted:", e);
  }
}

// Live Digital Clock
function updateClock() {
  const clockEl = document.getElementById('timestamp-clock');
  if (clockEl) {
    const now = new Date();
    clockEl.innerText = now.toLocaleTimeString() + " • UTC" + (now.getTimezoneOffset() > 0 ? "-" : "+") + Math.abs(now.getTimezoneOffset() / 60);
  }
}
setInterval(updateClock, 1000);
updateClock();

// Start Webcam
async function startWebcam() {
  const video = document.getElementById('camera-video');
  const preview = document.getElementById('preview-image');
  const stateText = document.getElementById('camera-state-text');
  const toggleBtnText = document.getElementById('toggle-cam-text');

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
    });
    currentStream = stream;
    video.srcObject = stream;
    video.style.display = 'block';
    preview.style.display = 'none';
    isWebcamActive = true;
    stateText.innerText = "Webcam Active • Live Feed";
    toggleBtnText.innerText = "Freeze / Upload Mode";
  } catch (err) {
    console.warn("Webcam not accessible or denied:", err);
    stateText.innerText = "Webcam Offline • Simulation Mode Ready";
    video.style.display = 'none';
    preview.style.display = 'block';
    preview.src = '/static/samples/adm0001.jpg';
    isWebcamActive = false;
    toggleBtnText.innerText = "Try Webcam Again";
  }
}

function toggleWebcam() {
  if (isWebcamActive && currentStream) {
    currentStream.getTracks().forEach(track => track.stop());
    currentStream = null;
    isWebcamActive = false;
    document.getElementById('camera-video').style.display = 'none';
    document.getElementById('preview-image').style.display = 'block';
    document.getElementById('camera-state-text').innerText = "Simulation / Upload Mode Active";
    document.getElementById('toggle-cam-text').innerText = "Switch to Camera";
  } else {
    startWebcam();
  }
}

// Simulate Profile via 1-Click Chip
async function simulateProfile(imgUrl, name, role) {
  const preview = document.getElementById('preview-image');
  const video = document.getElementById('camera-video');
  
  if (currentStream) {
    currentStream.getTracks().forEach(track => track.stop());
    currentStream = null;
    isWebcamActive = false;
  }
  
  video.style.display = 'none';
  preview.style.display = 'block';
  preview.src = imgUrl;
  document.getElementById('camera-state-text').innerText = `Simulating: ${name} (${role})`;
  document.getElementById('toggle-cam-text').innerText = "Switch to Camera";

  // Trigger optical scan animation
  triggerScanAnimation();

  // Fetch the image as a Blob and send to verification endpoint
  try {
    const res = await fetch(imgUrl);
    const blob = await res.blob();
    const formData = new FormData();
    formData.append('file', blob, 'sample.jpg');

    const verifyRes = await fetch('/api/verify', {
      method: 'POST',
      body: formData
    });
    const result = await verifyRes.json();
    renderVerificationResult(result);
  } catch (err) {
    console.error("Verification failed:", err);
  }
}

// File Upload
async function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const preview = document.getElementById('preview-image');
  const video = document.getElementById('camera-video');
  
  if (currentStream) {
    currentStream.getTracks().forEach(track => track.stop());
    currentStream = null;
    isWebcamActive = false;
  }

  video.style.display = 'none';
  preview.style.display = 'block';
  preview.src = URL.createObjectURL(file);
  document.getElementById('camera-state-text').innerText = `Uploaded: ${file.name}`;
  document.getElementById('toggle-cam-text').innerText = "Switch to Camera";

  triggerScanAnimation();

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/verify', {
      method: 'POST',
      body: formData
    });
    const result = await res.json();
    renderVerificationResult(result);
  } catch (err) {
    console.error("Failed to verify uploaded file:", err);
  }
}

// Capture frame from webcam & send
async function captureAndVerify() {
  triggerScanAnimation();

  if (isWebcamActive) {
    const video = document.getElementById('camera-video');
    const canvas = document.getElementById('hidden-canvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const base64Img = canvas.toDataURL('image/jpeg', 0.9);

    const formData = new FormData();
    formData.append('image_base64', base64Img);

    try {
      const res = await fetch('/api/verify', {
        method: 'POST',
        body: formData
      });
      const result = await res.json();
      renderVerificationResult(result);
    } catch (err) {
      console.error("Webcam verification failed:", err);
    }
  } else {
    // If in preview mode, re-verify currently loaded sample
    const preview = document.getElementById('preview-image');
    if (preview.src) {
      const res = await fetch(preview.src);
      const blob = await res.blob();
      const formData = new FormData();
      formData.append('file', blob, 'preview.jpg');

      const verifyRes = await fetch('/api/verify', {
        method: 'POST',
        body: formData
      });
      const result = await verifyRes.json();
      renderVerificationResult(result);
    }
  }
}

// Visual HUD Laser animation trigger
function triggerScanAnimation() {
  const laser = document.getElementById('scan-laser');
  const badge = document.getElementById('hud-text');
  if (laser) {
    laser.style.animation = 'none';
    laser.offsetHeight; // reflow
    laser.style.animation = 'laserSweep 1.2s ease-in-out infinite alternate';
  }
  if (badge) {
    badge.innerText = "EXTRACTING FACIAL EMBEDDING...";
  }
}

// Render Result to DOM
function renderVerificationResult(data) {
  const banner = document.getElementById('decision-banner');
  const headline = document.getElementById('decision-headline');
  const sub = document.getElementById('decision-sub');
  const resAvatar = document.getElementById('res-avatar');
  const resName = document.getElementById('res-name');
  const resRoleTag = document.getElementById('res-role-tag');
  const resDept = document.getElementById('res-dept');
  const resLevel = document.getElementById('res-access-level');
  const confVal = document.getElementById('confidence-val');
  const confBar = document.getElementById('confidence-bar');
  const hudText = document.getElementById('hud-text');

  confVal.innerText = `${data.confidence}%`;
  confBar.style.width = `${Math.min(100, Math.max(0, data.confidence))}%`;

  if (data.status === 'GRANTED') {
    playChime(true);
    banner.className = 'decision-banner granted';
    headline.innerText = 'ACCESS GRANTED';
    sub.innerText = data.message;
    hudText.innerText = `IDENTIFIED: ${data.user.name.toUpperCase()}`;

    // Fill user info
    resAvatar.style.display = 'block';
    let photoSrc = data.user.photo_url || `/static/samples/${data.user.user_id.toLowerCase()}.jpg`;
    if (photoSrc && !photoSrc.includes('?')) {
      photoSrc += `?t=${Date.now()}`;
    }
    resAvatar.src = photoSrc;
    resAvatar.onerror = () => { resAvatar.src = '/static/samples/default_avatar.svg'; };
    resName.innerText = data.user.name;
    resDept.innerText = data.user.department;
    
    resRoleTag.style.display = 'inline-block';
    resRoleTag.innerText = data.user.role;
    resRoleTag.className = `tag-pill ${data.user.role === 'ADMIN' ? 'tag-admin' : 'tag-employee'}`;
    resRoleTag.style.background = '';
    resRoleTag.style.color = '';

    resLevel.innerText = data.user.role === 'ADMIN' 
      ? '🛡️ CLEARANCE LEVEL 2: UNRESTRICTED ADMIN ACCESS' 
      : '🟢 CLEARANCE LEVEL 1: STANDARD OFFICE ENTRANCE';

  } else {
    playChime(false);
    banner.className = 'decision-banner denied';
    headline.innerText = 'ACCESS DENIED';
    sub.innerText = data.message;
    hudText.innerText = 'WARNING: UNRECOGNIZED SUBJECT';

    resAvatar.style.display = 'none';
    resName.innerText = 'Intruder / Unregistered';
    resDept.innerText = data.reason === 'NO_FACE_DETECTED' ? 'No Human Face Found' : 'Not in Company Database';
    resRoleTag.style.display = 'inline-block';
    resRoleTag.innerText = 'UNAUTHORIZED';
    resRoleTag.className = 'tag-pill tag-denied';
    resRoleTag.style.background = '';
    resRoleTag.style.color = '';
    resLevel.innerText = '🚨 SECURITY EVENT LOGGED TO AUDIT TRAIL';
  }

  // Refresh recent feed & demo profile audit tags
  loadRecentFeed();
  loadDemoProfiles();
}

// Fetch and display the recent activity feed
async function loadRecentFeed() {
  const feedEl = document.getElementById('recent-feed');
  try {
    const res = await fetch('/api/logs?limit=8');
    const data = await res.json();
    if (!data.logs || data.logs.length === 0) {
      feedEl.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 1rem;">No recent scans yet.</div>';
      return;
    }

    feedEl.innerHTML = data.logs.map(log => `
      <div class="feed-item ${log.status.toLowerCase()}">
        <div>
          <div class="feed-user">${log.name}</div>
          <div class="feed-time">${log.timestamp} • ${log.department || 'Unknown'}</div>
        </div>
        <div style="text-align: right;">
          <span class="badge-status ${log.status.toLowerCase()}">${log.status}</span>
          <div style="font-size: 0.72rem; color: var(--cyan-primary); margin-top: 2px;">${log.confidence}%</div>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error("Failed to load recent feed:", err);
  }
}

// Dynamically load demo profiles synced with recent audit trail
async function loadDemoProfiles() {
  const container = document.getElementById('sample-faces-row');
  if (!container) return;

  try {
    const [usersRes, logsRes] = await Promise.all([
      fetch('/api/users'),
      fetch('/api/logs?limit=50')
    ]);

    const usersData = await usersRes.json();
    const logsData = await logsRes.json();
    const users = usersData.users || [];
    const logs = logsData.logs || [];

    // Map recent audit scan by user_id
    const userAuditMap = {};
    let intruderLastLog = null;

    logs.forEach(log => {
      if (log.user_id && !userAuditMap[log.user_id]) {
        userAuditMap[log.user_id] = log;
      }
      if (log.status === 'DENIED' && !intruderLastLog) {
        intruderLastLog = log;
      }
    });

    let html = users.map(u => {
      const audit = userAuditMap[u.user_id];
      let auditBadgeHtml = '<span class="sample-audit-tag none">No Scan</span>';
      if (audit) {
        const timeShort = audit.timestamp.split(' ')[1] || audit.timestamp;
        auditBadgeHtml = `<span class="sample-audit-tag ${audit.status.toLowerCase()}">${audit.status === 'GRANTED' ? '✓' : '✗'} ${timeShort}</span>`;
      }

      const safeName = u.name.replace(/'/g, "\\'");
      let avatarSrc = u.photo_url || '/static/samples/default_avatar.svg';
      if (avatarSrc && !avatarSrc.includes('?')) {
        avatarSrc += `?t=${Date.now()}`;
      }
      return `
        <div class="sample-chip" onclick="simulateProfile('${avatarSrc}', '${safeName}', '${u.role}')">
          ${u.role === 'ADMIN' ? '<span class="sample-badge-admin">ADMIN</span>' : ''}
          <img src="${avatarSrc}" alt="${u.name}" class="sample-avatar" onerror="this.onerror=null; this.src='/static/samples/default_avatar.svg';">
          <div class="sample-name">${u.name}</div>
          <div class="sample-role">${u.department}</div>
          ${auditBadgeHtml}
        </div>
      `;
    }).join('');

    // Intruder sample chip
    let intruderAuditBadge = '<span class="sample-audit-tag none">No Scan</span>';
    if (intruderLastLog) {
      const timeShort = intruderLastLog.timestamp.split(' ')[1] || intruderLastLog.timestamp;
      intruderAuditBadge = `<span class="sample-audit-tag denied">✗ ${timeShort}</span>`;
    }

    html += `
      <div class="sample-chip intruder" onclick="simulateProfile('/static/samples/intruder.jpg', 'Unknown Visitor', 'INTRUDER')">
        <img src="/static/samples/intruder.jpg" alt="Intruder" class="sample-avatar" style="border-color: var(--crimson-danger);">
        <div class="sample-name" style="color: #fb7185;">Intruder</div>
        <div class="sample-role">Unregistered</div>
        ${intruderAuditBadge}
      </div>
    `;

    container.innerHTML = html;
  } catch (err) {
    console.error("Failed to load demo profiles:", err);
  }
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
  startWebcam();
  loadRecentFeed();
  loadDemoProfiles();
});
