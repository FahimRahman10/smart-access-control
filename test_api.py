import os
import sys
import subprocess

# Auto-detect if running outside .venv and transparently switch to the project's virtualenv
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
if os.path.exists(VENV_PYTHON) and sys.executable.lower() != os.path.abspath(VENV_PYTHON).lower():
    try:
        import requests
    except ImportError:
        result = subprocess.call([VENV_PYTHON] + sys.argv)
        sys.exit(result)

import requests

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

session = requests.Session()
session.trust_env = False  # Avoid routing local loopback requests to external proxy
url = "http://127.0.0.1:8000/api/verify"

print("--- Testing /api/verify ---")

try:
    # Check if server is online
    session.get("http://127.0.0.1:8000/api/stats", timeout=3)
except Exception:
    print("❌ ERROR: Server is not running at http://127.0.0.1:8000.")
    print("   Please start the server first by running: python run.py")
    sys.exit(1)

# 1. Test Admin (Fahim Rahman)
with open("dataset/adm0001/01.jpeg", "rb") as f:
    r1 = session.post(url, files={"file": ("01.jpeg", f, "image/jpeg")}).json()
print("Admin Result:   ", r1["status"], f"({r1['confidence']}%) -", r1["message"])
assert r1["status"] == "GRANTED", f"Expected GRANTED but got {r1['status']}"

# 2. Test Admin Sample Portrait (03.jpeg)
with open("dataset/adm0001/03.jpeg", "rb") as f:
    r2 = session.post(url, files={"file": ("03.jpeg", f, "image/jpeg")}).json()
print("Sample Result:  ", r2["status"], f"({r2['confidence']}%) -", r2["message"])
assert r2["status"] == "GRANTED", f"Expected GRANTED but got {r2['status']}"

# 3. Test Intruder
with open("dataset/intruder_sample/intruder.jpg", "rb") as f:
    r3 = session.post(url, files={"file": ("intruder.jpg", f, "image/jpeg")}).json()
print("Intruder Result:", r3["status"], f"({r3['confidence']}%) -", r3["message"])
assert r3["status"] == "DENIED", f"Expected DENIED but got {r3['status']}"

# 4. Check Access Logs
r_logs = session.get("http://127.0.0.1:8000/api/logs").json()
print("\n--- Recent Logs Recorded in SQLite ---")
for log in r_logs["logs"]:
    print(f"#{log['log_id']} [{log['status']}] {log['name']} ({log['role'] or 'N/A'}) - Confidence: {log['confidence']}%")

print("\n--- Summary Statistics ---")
stats = session.get("http://127.0.0.1:8000/api/stats").json()
print(stats)
print("\nALL API ENDPOINTS TESTED AND VERIFIED SUCCESSFULLY!")
