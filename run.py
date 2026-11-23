import os
import sys
import subprocess

# Auto-detect if running outside .venv and transparently switch to the project's virtualenv
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
if os.path.exists(VENV_PYTHON) and sys.executable.lower() != os.path.abspath(VENV_PYTHON).lower():
    try:
        import uvicorn
        import cv2
    except ImportError:
        result = subprocess.call([VENV_PYTHON] + sys.argv)
        sys.exit(result)

import uvicorn

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure current directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import init_db
from app.face_engine import get_engine

if __name__ == "__main__":
    print("=" * 65)
    print("🛡️  SMART ACCESS CONTROL - BIOMETRIC VERIFICATION GATE")
    print("=" * 65)
    
    # 1. Initialize SQLite Database & seed default identities
    print("[1/2] Initializing SQLite database...")
    init_db()
    
    # 2. Warm up Face Engine & Embeddings
    print("[2/2] Loading YuNet Detector & SFace Feature Recognizer...")
    engine = get_engine()
    print(f"      Enrolled Identities: {list(engine.known_embeddings.keys())}")
    
    print("\n🚀 Starting Server at: http://127.0.0.1:8000")
    print("   • Access Kiosk:    http://127.0.0.1:8000/")
    print("   • Admin Dashboard: http://127.0.0.1:8000/admin")
    print("   • API Docs:        http://127.0.0.1:8000/docs\n")
    
    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
    except Exception as e:
        print(f"❌ Server launch error: {e}")

