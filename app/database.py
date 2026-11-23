import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "access_control.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        department TEXT NOT NULL,
        access_level INTEGER DEFAULT 1,
        photo_url TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS access_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        name TEXT NOT NULL,
        role TEXT,
        department TEXT,
        timestamp TEXT NOT NULL,
        status TEXT NOT NULL,
        confidence REAL NOT NULL,
        reason TEXT,
        snapshot_data TEXT
    );
    """)
    
    # Safe migration: ensure sample_count exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    if "sample_count" not in columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN sample_count INTEGER DEFAULT 1")
        except Exception:
            pass
            
    conn.commit()
    seed_default_users(conn)
    conn.close()

def seed_default_users(conn: sqlite3.Connection):
    cursor = conn.cursor()
    default_users = [
        ("ADM0001", "Fahim Rahman", "ADMIN", "IT & Security Ops", 2, "/static/samples/adm0001.jpg"),
        ("EMP0001", "Protik Hossain", "EMPLOYEE", "Marketing & Growth", 1, "/static/samples/emp0001.jpg"),
        ("EMP0002", "Maruf Hossain", "EMPLOYEE", "Software Engineering", 1, "/static/samples/emp0002.jpg"),
        ("EMP0003", "Fahim Reza", "EMPLOYEE", "Finance & Compliance", 1, "/static/samples/emp0003.jpg"),
        ("EMP0004", "Saad Linkon", "EMPLOYEE", "Software Engineering", 1, "/static/samples/emp0004.jpg"),
        ("EMP0005", "Ridhwan Rabbi", "EMPLOYEE", "People & Culture (HR)", 1, "/static/samples/emp0005.jpg"),
    ]
    cursor.executemany("""
    INSERT INTO users (user_id, name, role, department, access_level, photo_url)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id) DO NOTHING
    """, default_users)
    conn.commit()

def get_users() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, role, department, access_level, photo_url, created_at FROM users ORDER BY user_id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, role, department, access_level, photo_url, created_at FROM users WHERE UPPER(user_id) = UPPER(?)", (user_id.strip(),))
    row = cursor.fetchone()
    if not row:
        # Fallback check for alternate 3-digit vs 4-digit notation (e.g. ADM001 <-> ADM0001)
        uid = user_id.strip().upper()
        if len(uid) == 7 and uid.startswith(("ADM", "EMP")) and uid[3] == "0":
            alt_id = uid[:3] + uid[4:]  # e.g. ADM0001 -> ADM001
            cursor.execute("SELECT user_id, name, role, department, access_level, photo_url, created_at FROM users WHERE UPPER(user_id) = UPPER(?)", (alt_id,))
            row = cursor.fetchone()
        elif len(uid) == 6 and uid.startswith(("ADM", "EMP")):
            alt_id = uid[:3] + "0" + uid[3:]  # e.g. ADM001 -> ADM0001
            cursor.execute("SELECT user_id, name, role, department, access_level, photo_url, created_at FROM users WHERE UPPER(user_id) = UPPER(?)", (alt_id,))
            row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def log_access(
    user_id: Optional[str],
    name: str,
    role: Optional[str],
    department: Optional[str],
    status: str,
    confidence: float,
    reason: str,
    snapshot_data: Optional[str] = None
) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO access_logs (user_id, name, role, department, timestamp, status, confidence, reason, snapshot_data)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, name, role, department, ts, status, round(confidence, 4), reason, snapshot_data))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def get_recent_logs(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT log_id, user_id, name, role, department, timestamp, status, confidence, reason, snapshot_data
    FROM access_logs
    ORDER BY log_id DESC
    LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM access_logs")
    total_logs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM access_logs WHERE status = 'GRANTED'")
    granted_logs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM access_logs WHERE status = 'DENIED'")
    denied_logs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE UPPER(role) = 'ADMIN'")
    admin_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE UPPER(role) != 'ADMIN'")
    employee_count = cursor.fetchone()[0]
    
    conn.close()
    return {
        "total_scans": total_logs,
        "granted_count": granted_logs,
        "denied_count": denied_logs,
        "enrolled_users": total_users,
        "admin_count": admin_count,
        "employee_count": employee_count,
        "accuracy_rate": round((granted_logs / total_logs * 100) if total_logs > 0 else 100.0, 1)
    }

def delete_user(user_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE UPPER(user_id) = UPPER(?)", (user_id.strip(),))
    deleted = cursor.rowcount > 0
    # Access logs are preserved for compliance & immutable security audit trail
    conn.commit()
    conn.close()
    return deleted

def update_user(
    user_id: str,
    new_user_id: Optional[str] = None,
    name: Optional[str] = None,
    role: Optional[str] = None,
    department: Optional[str] = None,
    photo_url: Optional[str] = None
) -> bool:
    clean_old_id = user_id.strip().upper()
    user_row = get_user_by_id(clean_old_id)
    if not user_row:
        return False
    actual_current_id = user_row["user_id"]

    conn = get_connection()
    cursor = conn.cursor()
    updates = []
    params = []

    if new_user_id is not None and new_user_id.strip():
        clean_new_id = new_user_id.strip().upper()
        if clean_new_id != actual_current_id:
            updates.append("user_id = ?")
            params.append(clean_new_id)
            cursor.execute("UPDATE access_logs SET user_id = ? WHERE UPPER(user_id) = ?", (clean_new_id, actual_current_id))

    if name is not None and name.strip():
        updates.append("name = ?")
        params.append(name.strip())
    if role is not None and role.strip():
        role_clean = role.strip().upper()
        updates.append("role = ?")
        params.append(role_clean)
        updates.append("access_level = ?")
        params.append(2 if role_clean == "ADMIN" else 1)
    if department is not None and department.strip():
        updates.append("department = ?")
        params.append(department.strip())
    if photo_url is not None and photo_url.strip():
        updates.append("photo_url = ?")
        params.append(photo_url.strip())

    if not updates:
        conn.close()
        return True

    params.append(actual_current_id)
    sql = f"UPDATE users SET {', '.join(updates)} WHERE UPPER(user_id) = ?"
    cursor.execute(sql, params)
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def delete_log(log_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM access_logs WHERE log_id = ?", (log_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def clear_all_logs() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM access_logs")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


