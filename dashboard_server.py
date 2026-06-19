import threading
import json
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer

# Global state that will be updated by the main pipeline and AI client
status_data = {
    "online": True,
    "provider": "openrouter",
    "model": "google/gemini-2.5-flash",
    "last_speech": "",
    "last_gesture": "neutral",
    "last_face_seen": "None",
    "busy": False,
    "uptime": time.time(),
    "last_user_text": "",
    "head_angle": 90,
    "arms_offsets": [0, 0, 0, 0, 0, 0] # rs, re, rw, ls, le, lw
}

status_lock = threading.Lock()

def update_status(**kwargs):
    with status_lock:
        for k, v in kwargs.items():
            if k in status_data:
                status_data[k] = v

def get_status_json():
    with status_lock:
        data = dict(status_data)
        data["uptime_seconds"] = int(time.time() - data["uptime"])
        return json.dumps(data)

# Premium Dashboard HTML Template using dark-mode glassmorphism
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amir Temur Robot - Premium Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-grad: linear-gradient(135deg, #090514 0%, #110d24 50%, #030107 100%);
            --panel-bg: rgba(22, 17, 38, 0.65);
            --panel-border: rgba(255, 255, 255, 0.08);
            --accent-glow: rgba(139, 92, 246, 0.35);
            --neon-purple: #8b5cf6;
            --neon-blue: #3b82f6;
            --neon-green: #10b981;
            --neon-red: #ef4444;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-grad);
            color: var(--text-main);
            min-height: 100vh;
            overflow-x: hidden;
            display: flex;
            flex-direction: column;
        }

        header {
            padding: 1.5rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--panel-border);
            backdrop-filter: blur(12px);
            background: rgba(9, 5, 20, 0.7);
            z-index: 10;
        }

        .logo-section h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.9rem;
            font-weight: 800;
            background: linear-gradient(to right, #c084fc, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
            text-shadow: 0 0 20px rgba(139, 92, 246, 0.2);
        }

        .logo-section p {
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-top: 2px;
            letter-spacing: 0.3px;
        }

        .system-time {
            font-family: 'Outfit', sans-serif;
            font-size: 1.1rem;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.05);
            padding: 0.5rem 1.25rem;
            border-radius: 99px;
            border: 1px solid var(--panel-border);
            color: #c084fc;
            box-shadow: 0 0 15px rgba(139, 92, 246, 0.1);
        }

        main {
            flex: 1;
            padding: 2rem;
            max-width: 1450px;
            width: 100%;
            margin: 0 auto;
            display: grid;
            grid-template-columns: repeat(12, 1fr);
            gap: 1.5rem;
        }

        .card {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 1.25rem;
            padding: 1.5rem;
            backdrop-filter: blur(20px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, transparent, var(--neon-purple), transparent);
            opacity: 0.4;
        }

        .card:hover {
            transform: translateY(-2px);
            border-color: rgba(139, 92, 246, 0.3);
            box-shadow: 0 12px 40px 0 rgba(139, 92, 246, 0.15);
        }

        .card-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.15rem;
            font-weight: 600;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.6rem;
            color: #c084fc;
        }

        /* Status Grid */
        .status-grid {
            grid-column: span 4;
            display: flex;
            flex-direction: column;
            gap: 1.1rem;
        }

        .status-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.02);
            padding: 0.9rem 1.2rem;
            border-radius: 0.75rem;
            border: 1px solid rgba(255, 255, 255, 0.03);
        }

        .status-label {
            font-size: 0.9rem;
            color: var(--text-muted);
        }

        .status-value {
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            font-size: 0.95rem;
        }

        .badge {
            padding: 0.3rem 0.85rem;
            border-radius: 99px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
        }

        .badge-online {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
            box-shadow: 0 0 12px rgba(16, 185, 129, 0.25);
        }

        .badge-offline {
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
            box-shadow: 0 0 12px rgba(239, 68, 68, 0.25);
        }

        .badge-busy {
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
            box-shadow: 0 0 10px rgba(245, 158, 11, 0.15);
        }

        /* Motor Gauges */
        .motor-card {
            grid-column: span 5;
        }

        .motor-list {
            display: flex;
            flex-direction: column;
            gap: 0.95rem;
        }

        .motor-item {
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }

        .motor-info {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
        }

        .motor-name {
            font-weight: 500;
            color: var(--text-main);
        }

        .motor-val {
            font-family: 'Outfit', sans-serif;
            color: #60a5fa;
            font-weight: 600;
        }

        .bar-container {
            height: 8px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 99px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.02);
        }

        .bar-fill {
            height: 100%;
            border-radius: 99px;
            background: linear-gradient(90deg, #3b82f6, #8b5cf6);
            width: 50%;
            transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* Face & Feed logs */
        .camera-card {
            grid-column: span 3;
            display: flex;
            flex-direction: column;
        }

        .feed-placeholder {
            flex: 1;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 0.75rem;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            border: 1px dashed rgba(255, 255, 255, 0.1);
            min-height: 150px;
            text-align: center;
            padding: 1rem;
        }

        .feed-placeholder svg {
            width: 48px;
            height: 48px;
            color: var(--neon-purple);
            margin-bottom: 0.75rem;
            filter: drop-shadow(0 0 10px rgba(139, 92, 246, 0.6));
        }

        .feed-label {
            font-size: 0.95rem;
            font-weight: 600;
            margin-bottom: 4px;
        }

        .feed-sub {
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        /* Chat Log */
        .chat-card {
            grid-column: span 12;
            height: 400px;
            display: flex;
            flex-direction: column;
        }

        .chat-log {
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 1rem;
            padding-right: 0.5rem;
        }

        .chat-log::-webkit-scrollbar {
            width: 6px;
        }

        .chat-log::-webkit-scrollbar-track {
            background: transparent;
        }

        .chat-log::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 99px;
        }

        .chat-msg {
            display: flex;
            flex-direction: column;
            max-width: 80%;
            padding: 0.85rem 1.1rem;
            border-radius: 1rem;
            font-size: 0.95rem;
            line-height: 1.4;
        }

        .msg-user {
            align-self: flex-end;
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(37, 99, 235, 0.15) 100%);
            border: 1px solid rgba(59, 130, 246, 0.25);
            border-bottom-right-radius: 0.25rem;
        }

        .msg-robot {
            align-self: flex-start;
            background: linear-gradient(135deg, rgba(139, 92, 246, 0.15) 0%, rgba(109, 40, 217, 0.1) 100%);
            border: 1px solid rgba(139, 92, 246, 0.2);
            border-bottom-left-radius: 0.25rem;
        }

        .msg-meta {
            font-family: 'Outfit', sans-serif;
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        footer {
            text-align: center;
            padding: 1.5rem;
            color: var(--text-muted);
            font-size: 0.8rem;
            border-top: 1px solid var(--panel-border);
            margin-top: auto;
            backdrop-filter: blur(10px);
            background: rgba(9, 5, 20, 0.5);
        }

        @media (max-width: 1024px) {
            .status-grid, .motor-card, .camera-card {
                grid-column: span 12;
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-section">
            <h1>AMIR TEMUR HUMANOID</h1>
            <p>Tizim Holati va Boshqaruv Paneli</p>
        </div>
        <div class="system-time" id="live-time">00:00:00</div>
    </header>

    <main>
        <!-- Card 1: System Status -->
        <div class="card status-grid">
            <h2 class="card-title">
                <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
                Asosiy Holat
            </h2>
            <div class="status-row">
                <span class="status-label">Ulanish</span>
                <span id="status-online"><span class="badge badge-online">Yuklanmoqda...</span></span>
            </div>
            <div class="status-row">
                <span class="status-label">Faoliyat</span>
                <span id="status-busy"><span class="badge">Noma'lum</span></span>
            </div>
            <div class="status-row">
                <span class="status-label">AI Provayder</span>
                <span class="status-value" id="status-provider">OpenRouter</span>
            </div>
            <div class="status-row">
                <span class="status-label">AI Model</span>
                <span class="status-value" id="status-model">-</span>
            </div>
            <div class="status-row">
                <span class="status-label">Uptime</span>
                <span class="status-value" id="status-uptime">0s</span>
            </div>
        </div>

        <!-- Card 2: Motor Offsets -->
        <div class="card motor-card">
            <h2 class="card-title">
                <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
                Motorlar offsets (ESP32)
            </h2>
            <div class="motor-list">
                <div class="motor-item">
                    <div class="motor-info">
                        <span class="motor-name">Bosh burchagi (Head Servo)</span>
                        <span class="motor-val" id="val-head">90°</span>
                    </div>
                    <div class="bar-container">
                        <div class="bar-fill" id="bar-head" style="width: 50%;"></div>
                    </div>
                </div>
                <div class="motor-item">
                    <div class="motor-info">
                        <span class="motor-name">O'ng yelka (R-Shoulder)</span>
                        <span class="motor-val" id="val-rs">0°</span>
                    </div>
                    <div class="bar-container">
                        <div class="bar-fill" id="bar-rs" style="width: 50%;"></div>
                    </div>
                </div>
                <div class="motor-item">
                    <div class="motor-info">
                        <span class="motor-name">O'ng tirsak (R-Elbow)</span>
                        <span class="motor-val" id="val-re">0°</span>
                    </div>
                    <div class="bar-container">
                        <div class="bar-fill" id="bar-re" style="width: 50%;"></div>
                    </div>
                </div>
                <div class="motor-item">
                    <div class="motor-info">
                        <span class="motor-name">Chap yelka (L-Shoulder)</span>
                        <span class="motor-val" id="val-ls">0°</span>
                    </div>
                    <div class="bar-container">
                        <div class="bar-fill" id="bar-ls" style="width: 50%;"></div>
                    </div>
                </div>
                <div class="motor-item">
                    <div class="motor-info">
                        <span class="motor-name">Chap tirsak (L-Elbow)</span>
                        <span class="motor-val" id="val-le">0°</span>
                    </div>
                    <div class="bar-container">
                        <div class="bar-fill" id="bar-le" style="width: 50%;"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Card 3: Camera Feed status -->
        <div class="card camera-card">
            <h2 class="card-title">
                <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24"><path d="M12 9c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3zm0 8c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm9-13h-3.17L16 2H8L6.17 4H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2z"/></svg>
                Yuz Tanish (Face Detect)
            </h2>
            <div class="feed-placeholder">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15.182 15.182a4.5 4.5 0 0 1-6.364 0M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9.75 9.75c0 .414-.168.75-.375.75s-.375-.336-.375-.75.168-.75.375-.75.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75.168-.75.375-.75.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Z" /></svg>
                <div class="feed-label" id="face-label">Yuz aniqlanmadi</div>
                <div class="feed-sub" id="face-meta">Kamera faol...</div>
            </div>
        </div>

        <!-- Card 4: Chat Log -->
        <div class="card chat-card">
            <h2 class="card-title">
                <svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 9h12v2H6V9zm8 5H6v-2h8v2zm4-6H6V6h12v2z"/></svg>
                Muloqot jurnali (Speech logs)
            </h2>
            <div class="chat-log" id="chat-log-box">
                <!-- Message structures will be appended here dynamically -->
            </div>
        </div>
    </main>

    <footer>
        Amir Temur Humanoid Robot Project — Premium Dashboard v2.0
    </footer>

    <script>
        // Real-time time
        function updateTime() {
            const now = new Date();
            document.getElementById('live-time').innerText = now.toTimeString().split(' ')[0];
        }
        setInterval(updateTime, 1000);
        updateTime();

        // Format offset percentages for progress bar (ranges from -90 to +90)
        function getPercent(offset) {
            const min = -90;
            const max = 90;
            // Map offset [-90, 90] to [0, 100]%
            const pct = ((offset - min) / (max - min)) * 100;
            return Math.max(0, Math.min(100, pct));
        }

        // Keep track of last messages to prevent duplicates
        let lastUserMessage = "";
        let lastRobotMessage = "";

        function appendMessage(role, text) {
            if (!text) return;
            const chatLog = document.getElementById('chat-log-box');
            
            const msgDiv = document.createElement('div');
            msgDiv.className = 'chat-msg ' + (role === 'user' ? 'msg-user' : 'msg-robot');
            
            const metaDiv = document.createElement('div');
            metaDiv.className = 'msg-meta';
            metaDiv.innerText = role === 'user' ? 'Siz' : 'Amir Temur';
            
            const textSpan = document.createElement('span');
            textSpan.innerText = text;
            
            msgDiv.appendChild(metaDiv);
            msgDiv.appendChild(textSpan);
            chatLog.appendChild(msgDiv);
            chatLog.scrollTop = chatLog.scrollHeight;
        }

        // Poll status
        async function fetchStatus() {
            try {
                const res = await fetch('/status');
                const data = await res.json();

                // 1. Connection Badge
                const onlineEl = document.getElementById('status-online');
                if (data.online) {
                    onlineEl.innerHTML = '<span class="badge badge-online">ONLINE (Gemini/OpenRouter)</span>';
                } else {
                    onlineEl.innerHTML = '<span class="badge badge-offline">OFFLINE (Ollama Fallback)</span>';
                }

                // 2. Busy Badge
                const busyEl = document.getElementById('status-busy');
                if (data.busy) {
                    busyEl.innerHTML = '<span class="badge badge-busy">BAND (Gapirmoqda...)</span>';
                } else {
                    busyEl.innerHTML = '<span class="badge badge-online" style="background: rgba(59,130,246,0.15); color: #60a5fa; border-color: rgba(59,130,246,0.3)">KUTMOQDA</span>';
                }

                // 3. Labels
                document.getElementById('status-provider').innerText = data.provider;
                document.getElementById('status-model').innerText = data.model;
                
                // Uptime format
                const uptimeSec = data.uptime_seconds || 0;
                const hrs = Math.floor(uptimeSec / 3600);
                const mins = Math.floor((uptimeSec % 3600) / 60);
                const secs = uptimeSec % 60;
                document.getElementById('status-uptime').innerText = `${hrs}s ${mins}m ${secs}s`;

                // 4. Motors
                const headAngle = data.head_angle !== undefined ? data.head_angle : 90;
                document.getElementById('val-head').innerText = headAngle + '°';
                document.getElementById('bar-head').style.width = ((headAngle / 180) * 100) + '%';

                const offsets = data.arms_offsets || [0,0,0,0,0,0];
                
                // Update UI for shoulders and elbows
                document.getElementById('val-rs').innerText = offsets[0] + '°';
                document.getElementById('bar-rs').style.width = getPercent(offsets[0]) + '%';
                
                document.getElementById('val-re').innerText = offsets[1] + '°';
                document.getElementById('bar-re').style.width = getPercent(offsets[1]) + '%';
                
                document.getElementById('val-ls').innerText = offsets[3] + '°';
                document.getElementById('bar-ls').style.width = getPercent(offsets[3]) + '%';
                
                document.getElementById('val-le').innerText = offsets[4] + '°';
                document.getElementById('bar-le').style.width = getPercent(offsets[4]) + '%';

                // 5. Face Recognition
                const faceLabel = document.getElementById('face-label');
                const faceMeta = document.getElementById('face-meta');
                if (data.last_face_seen && data.last_face_seen !== 'None') {
                    faceLabel.innerText = data.last_face_seen;
                    faceLabel.style.color = '#34d399';
                    faceMeta.innerText = 'Tanish muvaffaqiyatli';
                } else {
                    faceLabel.innerText = 'Yuz aniqlanmadi';
                    faceLabel.style.color = '';
                    faceMeta.innerText = 'Kamera faol...';
                }

                // 6. Append chat logs if new
                if (data.last_user_text && data.last_user_text !== lastUserMessage) {
                    lastUserMessage = data.last_user_text;
                    appendMessage('user', lastUserMessage);
                }
                if (data.last_speech && data.last_speech !== lastRobotMessage) {
                    lastRobotMessage = data.last_speech;
                    appendMessage('robot', lastRobotMessage);
                }

            } catch (err) {
                console.error("Dashboard status fetch failed:", err);
            }
        }

        // Initial and interval polls
        fetchStatus();
        setInterval(fetchStatus, 1000);
    </script>
</body>
</html>
"""

class DashboardHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(get_status_json().encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

def start_server_in_thread(port=8085):
    def run_server():
        server_address = ("", port)
        try:
            httpd = HTTPServer(server_address, DashboardHTTPRequestHandler)
            print(f"[DASHBOARD] Dashboard server running at http://localhost:{port}")
            httpd.serve_forever()
        except Exception as exc:
            print(f"[DASHBOARD] Failed to start dashboard server: {exc}")

    t = threading.Thread(target=run_server, name="dashboard-http", daemon=True)
    t.start()
