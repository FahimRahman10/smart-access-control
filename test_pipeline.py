import os
import sys
import subprocess

# Auto-detect if running outside .venv and transparently switch to the project's virtualenv
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
if os.path.exists(VENV_PYTHON) and sys.executable.lower() != os.path.abspath(VENV_PYTHON).lower():
    try:
        import cv2
    except ImportError:
        result = subprocess.call([VENV_PYTHON] + sys.argv)
        sys.exit(result)

import cv2

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.database import init_db, get_users, get_stats
from app.face_engine import get_engine

def run_test():
    print("=== 1. Initializing Database ===")
    init_db()
    users = get_users()
    print(f"Total Enrolled Users: {len(users)}")
    for u in users:
        print(f"  • [{u['user_id']}] {u['name']} - Role: {u['role']} ({u['department']})")

    print("\n=== 2. Loading Face Engine ===")
    engine = get_engine()
    print(f"Engine enrolled identities: {list(engine.known_embeddings.keys())}")

    print("\n=== 3. Testing Positive Match: Admin (Fahim Rahman - ADM0001) ===")
    admin_img = cv2.imread("dataset/admin_fahim/adm0001_enrolled.jpg")
    if admin_img is None:
        admin_img = cv2.imread("app/static/samples/adm0001.jpg")
    res_admin = engine.verify(admin_img)
    print(f"Result: {res_admin['status']}")
    print(f"Confidence: {res_admin['confidence']}% (Raw Score: {res_admin.get('raw_score')})")
    print(f"Message: {res_admin['message']}")
    assert res_admin["status"] == "GRANTED", "Admin should be GRANTED access"
    assert res_admin["user"]["role"] == "ADMIN", "Role should be ADMIN"

    print("\n=== 4. Testing Positive Match: Admin Sample Portrait ===")
    sample_img = cv2.imread("app/static/samples/adm0001.jpg")
    res_sample = engine.verify(sample_img)
    print(f"Result: {res_sample['status']}")
    print(f"Confidence: {res_sample['confidence']}% (Raw Score: {res_sample.get('raw_score')})")
    print(f"Message: {res_sample['message']}")
    assert res_sample["status"] == "GRANTED", "Admin sample should be GRANTED access"

    print("\n=== 5. Testing Intruder Denial (Unregistered Person) ===")
    intruder_img = cv2.imread("dataset/intruder_sample/intruder.jpg")
    res_intruder = engine.verify(intruder_img)
    print(f"Result: {res_intruder['status']}")
    print(f"Confidence: {res_intruder['confidence']}% (Raw Score: {res_intruder['raw_score']})")
    print(f"Message: {res_intruder['message']}")
    assert res_intruder["status"] == "DENIED", "Intruder should be DENIED access"
    assert res_intruder["reason"] == "UNRECOGNIZED_FACE", "Reason should be UNRECOGNIZED_FACE"

    print("\n=== 6. Testing Edge Case: Frame With No Face ===")
    import numpy as np
    blank_frame = np.zeros((300, 300, 3), dtype=np.uint8)
    res_blank = engine.verify(blank_frame)
    print(f"Result: {res_blank['status']}")
    print(f"Reason: {res_blank['reason']}")
    assert res_blank["status"] == "DENIED"
    assert res_blank["reason"] == "NO_FACE_DETECTED"

    print("\nALL VERIFICATION TESTS PASSED! ML PIPELINE IS FULLY OPERATIONAL.")

if __name__ == "__main__":
    run_test()
