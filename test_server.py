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

import threading
import time
import requests
import uvicorn
from app.main import app

def main():
    config = uvicorn.Config(app, host="127.0.0.1", port=8001, log_level="info")
    server = uvicorn.Server(config)

    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    session = requests.Session()
    session.trust_env = False  # Avoid routing local loopback requests to external proxy

    # Wait for server ready
    for _ in range(30):
        try:
            r = session.get("http://127.0.0.1:8001/api/stats", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)

    try:
        # 1. Stats
        r = session.get("http://127.0.0.1:8001/api/stats")
        print("1. Stats [200]:", r.status_code, r.json())
        assert r.status_code == 200

        # 2. Users
        r = session.get("http://127.0.0.1:8001/api/users")
        users = r.json()["users"]
        print(f"2. Users [200]: Count = {len(users)}, Users = {[u['user_id'] for u in users]}")
        assert r.status_code == 200
        assert len(users) >= 6

        # 3. Verify Positive (Admin Fahim Rahman)
        with open("dataset/admin_fahim/adm0001_enrolled.jpg", "rb") as f:
            r = session.post("http://127.0.0.1:8001/api/verify", files={"file": ("adm0001_enrolled.jpg", f, "image/jpeg")})
        res_data = r.json()
        print(f"3. Verify Admin [200]: Status={res_data['status']}, Confidence={res_data['confidence']}%, User={res_data.get('user', {}).get('name')}")
        assert res_data["status"] == "GRANTED"
        assert res_data["user"]["user_id"] == "ADM0001"
        assert res_data.get("snapshot_url") is not None

        # 4. Verify Negative (Intruder)
        with open("dataset/intruder_sample/intruder.jpg", "rb") as f:
            r = session.post("http://127.0.0.1:8001/api/verify", files={"file": ("intruder.jpg", f, "image/jpeg")})
        res_intruder = r.json()
        print(f"4. Verify Intruder [200]: Status={res_intruder['status']}, Confidence={res_intruder['confidence']}%")
        assert res_intruder["status"] == "DENIED"

        # 5. Access Logs
        r = session.get("http://127.0.0.1:8001/api/logs?limit=5")
        logs = r.json()["logs"]
        print(f"5. Logs [200]: Retrieved {len(logs)} recent entries. Latest = #{logs[0]['log_id']} [{logs[0]['status']}] {logs[0]['name']}")
        assert len(logs) > 0

        # 6. Update Employee
        r = session.post("http://127.0.0.1:8001/api/users/EMP0002/update", data={"name": "Maruf Hossain (Lead)", "department": "Platform Engineering", "role": "EMPLOYEE"})
        assert r.status_code == 200
        print("6. Update Employee [200]:", r.json()["message"])
        # Restore EMP0002
        session.post("http://127.0.0.1:8001/api/users/EMP0002/update", data={"name": "Maruf Hossain", "department": "Software Engineering", "role": "EMPLOYEE"})

        # 7. Create, Update ID & Picture, and Delete Temporary Employee
        from app.database import get_connection
        conn = get_connection()
        conn.execute("INSERT OR REPLACE INTO users (user_id, name, role, department, access_level, photo_url) VALUES (?, ?, ?, ?, ?, ?)", ("TMP999", "To Delete", "EMPLOYEE", "QA", 1, "/static/samples/default_avatar.svg"))
        conn.commit()
        conn.close()

        # Update TMP999 ID to TMP888 and change image
        with open("dataset/admin_fahim/adm0001_enrolled.jpg", "rb") as f:
            up_r = session.post(
                "http://127.0.0.1:8001/api/users/TMP999/update",
                data={"new_user_id": "TMP888", "name": "Renamed Temp", "role": "EMPLOYEE", "department": "QA & Test"},
                files={"file": ("new_pic.jpg", f, "image/jpeg")}
            )
        assert up_r.status_code == 200
        up_data = up_r.json()
        assert up_data["user"]["user_id"] == "TMP888"
        assert "photo_url" in up_data["user"]
        print("7. Update Employee ID & Face Picture [200]:", up_data["message"])

        del_r = session.delete("http://127.0.0.1:8001/api/users/TMP888")
        assert del_r.status_code == 200
        print("8. Delete Employee [200]:", del_r.json()["message"])

        print("\n>>> ALL API ENDPOINTS & AUTH VERIFICATION PASSED FULLY! <<<")
    finally:
        server.should_exit = True

if __name__ == "__main__":
    main()
