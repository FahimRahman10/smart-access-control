import os
import re
import time
import base64
import cv2
import numpy as np
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional, List

from app.database import (
    init_db, get_users, get_recent_logs, log_access, get_stats, 
    get_user_by_id, get_connection, delete_log, clear_all_logs, delete_user, update_user
)
from app.face_engine import get_engine

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")

SNAPSHOTS_DIR = os.path.join(STATIC_DIR, "snapshots")

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.path.join(STATIC_DIR, "samples"), exist_ok=True)
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    init_db()
    get_engine()
    print("[Server] Database initialized and Face Engine ready.")
    yield

app = FastAPI(
    title="Smart Face Recognition Access Control",
    description="Enterprise Biometric Face Verification System with Role-Based Access Control",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/admin")
def read_admin():
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))

@app.get("/api/users")
def api_get_users():
    return {"users": get_users()}

@app.delete("/api/users/{user_id}")
def api_delete_user(user_id: str):
    clean_user_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id.strip()).upper()
    if not clean_user_id:
        raise HTTPException(status_code=400, detail="Invalid user ID format.")

    engine = get_engine()
    engine.delete_user_dataset(clean_user_id)
    success = delete_user(clean_user_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Employee/Admin '{clean_user_id}' not found.")
    return {"status": "SUCCESS", "message": f"Successfully deleted employee/admin {clean_user_id}."}

@app.put("/api/users/{user_id}")
@app.post("/api/users/{user_id}/update")
async def api_update_user(
    user_id: str,
    new_user_id: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """Updates an employee profile, employee ID, and optionally replaces their facial recognition portrait."""
    clean_user_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id.strip()).upper()
    user = get_user_by_id(clean_user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"Employee '{clean_user_id}' not found.")
    canonical_user_id = user["user_id"]

    # Determine final employee ID
    target_user_id = canonical_user_id
    if new_user_id and new_user_id.strip():
        clean_new_id = re.sub(r'[^a-zA-Z0-9_-]', '', new_user_id.strip()).upper()
        if not clean_new_id:
            raise HTTPException(status_code=400, detail="Invalid new employee ID format.")
        if clean_new_id != canonical_user_id:
            existing = get_user_by_id(clean_new_id)
            if existing and existing["user_id"] != canonical_user_id:
                raise HTTPException(status_code=400, detail=f"Employee ID '{clean_new_id}' is already assigned to {existing['name']}.")
            target_user_id = clean_new_id
            engine = get_engine()
            engine.rename_user(canonical_user_id, target_user_id)

    photo_url = None
    if file and file.filename:
        content = await file.read()
        if len(content) > 0:
            nparr = np.frombuffer(content, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_bgr is None:
                raise HTTPException(status_code=400, detail="Invalid image file format.")

            engine = get_engine()
            success = await run_in_threadpool(
                engine.enroll_new_image,
                target_user_id,
                img_bgr,
                f"{target_user_id.lower()}_enrolled.jpg",
                True  # replace_existing
            )
            if not success:
                raise HTTPException(status_code=400, detail="Could not detect a clear human face in uploaded photo. Please ensure face is centered and clearly lit.")

            ts = int(time.time())
            # Save primary sample
            primary_sample_path = os.path.join(STATIC_DIR, "samples", f"{target_user_id.lower()}.jpg")
            cv2.imwrite(primary_sample_path, img_bgr)

            # Also ensure both 3-digit and 4-digit alias files exist (e.g. adm001.jpg and adm0001.jpg)
            if target_user_id.startswith(("ADM", "EMP")):
                prefix = target_user_id[:3].lower()
                num_part = target_user_id[3:]
                if num_part.isdigit():
                    val = int(num_part)
                    alt_3 = os.path.join(STATIC_DIR, "samples", f"{prefix}{val:03d}.jpg")
                    alt_4 = os.path.join(STATIC_DIR, "samples", f"{prefix}{val:04d}.jpg")
                    cv2.imwrite(alt_3, img_bgr)
                    cv2.imwrite(alt_4, img_bgr)

            photo_url = f"/static/samples/{target_user_id.lower()}.jpg?t={ts}"

    update_user(
        user_id=canonical_user_id,
        new_user_id=target_user_id if target_user_id != canonical_user_id else None,
        name=name,
        role=role,
        department=department,
        photo_url=photo_url
    )

    updated_user = get_user_by_id(target_user_id)
    return {
        "status": "SUCCESS",
        "message": f"Successfully updated employee {target_user_id}.",
        "user": updated_user
    }

@app.get("/api/logs")
def api_get_logs(limit: int = 50):
    return {"logs": get_recent_logs(limit=limit)}

@app.delete("/api/logs/{log_id}")
def api_delete_log(log_id: int):
    success = delete_log(log_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Log entry #{log_id} not found.")
    return {"status": "SUCCESS", "message": f"Log #{log_id} deleted successfully."}

@app.delete("/api/logs")
def api_clear_logs():
    count = clear_all_logs()
    return {"status": "SUCCESS", "message": f"Cleared all {count} gate audit log entries."}

@app.get("/api/stats")
def api_get_stats():
    return get_stats()

class VerifyPayload(BaseModel):
    image_base64: Optional[str] = None
    threshold: Optional[float] = None

@app.post("/api/verify")
async def api_verify_post(
    request: Request,
    file: Optional[UploadFile] = File(None),
    image_base64: Optional[str] = Form(None),
    threshold: Optional[float] = Form(None)
):
    """
    Verifies an incoming face photo (either via multipart File upload, form-data, or JSON payload).
    Runs CPU inference via threadpool to prevent blocking the async event loop.
    """
    engine = get_engine()
    img_bgr = None
    snapshot_url = None

    if file:
        content = await file.read()
        nparr = np.frombuffer(content, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    elif image_base64:
        # Base64 string from webcam snapshot
        if "," in image_base64:
            clean_b64 = image_base64.split(",", 1)[1]
        else:
            clean_b64 = image_base64
        try:
            content = base64.b64decode(clean_b64)
            nparr = np.frombuffer(content, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            raise HTTPException(status_code=400, detail="Malformed base64 image data.")
    else:
        # Check if JSON payload was sent
        try:
            if "application/json" in request.headers.get("content-type", ""):
                body = await request.json()
                b64 = body.get("image_base64")
                if b64:
                    clean_b64 = b64.split(",", 1)[1] if "," in b64 else b64
                    content = base64.b64decode(clean_b64)
                    nparr = np.frombuffer(content, np.uint8)
                    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if threshold is None and "threshold" in body:
                        threshold = body.get("threshold")
        except Exception:
            pass

    if img_bgr is None:
        raise HTTPException(status_code=400, detail="Valid 'file', 'image_base64', or JSON body with facial image is required.")

    # Run verification in background threadpool to prevent blocking the asyncio loop
    thresh_val = float(threshold) if threshold is not None else engine.cosine_threshold
    result = await run_in_threadpool(engine.verify, img_bgr, thresh_val)

    # Save a small, efficient thumbnail to disk to prevent database bloat
    try:
        snap_id = f"snap_{int(time.time() * 1000)}.jpg"
        snap_path = os.path.join(SNAPSHOTS_DIR, snap_id)
        # Create thumbnail (max 160px height)
        sh, sw = img_bgr.shape[:2]
        thumb_scale = 160.0 / max(sh, sw) if max(sh, sw) > 160 else 1.0
        thumb_img = cv2.resize(img_bgr, (int(sw * thumb_scale), int(sh * thumb_scale)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(snap_path, thumb_img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        snapshot_url = f"/static/snapshots/{snap_id}"
    except Exception:
        snapshot_url = None

    # Log access decision to database
    user = result.get("user")
    user_id = user["user_id"] if user else None
    name = user["name"] if user else ("Unknown Intruder" if result["status"] == "DENIED" else "Unregistered Person")
    role = user["role"] if user else None
    dept = user["department"] if user else None

    log_id = log_access(
        user_id=user_id,
        name=name,
        role=role,
        department=dept,
        status=result["status"],
        confidence=result["confidence"],
        reason=result["reason"],
        snapshot_data=snapshot_url
    )
    result["log_id"] = log_id
    result["snapshot_url"] = snapshot_url

    return JSONResponse(content=result)

@app.post("/api/enroll")
async def api_enroll_post(
    user_id: str = Form(...),
    name: str = Form(...),
    role: str = Form(...),
    department: str = Form(...),
    file: UploadFile = File(...)
):
    """Enrolls a new employee with their reference face portrait."""
    clean_user_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id.strip()).upper()
    if not clean_user_id:
        raise HTTPException(status_code=400, detail="Invalid user ID. Only letters, numbers, hyphens, and underscores are allowed.")

    content = await file.read()
    nparr = np.frombuffer(content, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img_bgr is None:
        raise HTTPException(status_code=400, detail="Invalid image file.")

    engine = get_engine()
    success = await run_in_threadpool(
        engine.enroll_new_image,
        clean_user_id,
        img_bgr,
        f"{clean_user_id.lower()}_enrolled.jpg"
    )
    if not success:
        raise HTTPException(status_code=400, detail="Could not detect a clear human face in uploaded photo.")

    # Save photo to static/samples
    static_sample_path = os.path.join(STATIC_DIR, "samples", f"{clean_user_id.lower()}.jpg")
    cv2.imwrite(static_sample_path, img_bgr)
    photo_url = f"/static/samples/{clean_user_id.lower()}.jpg"

    # Insert or update in database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO users (user_id, name, role, department, access_level, photo_url)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        name = excluded.name,
        role = excluded.role,
        department = excluded.department,
        access_level = excluded.access_level,
        photo_url = excluded.photo_url
    """, (clean_user_id, name.strip(), role.strip().upper(), department.strip(), 2 if role.strip().upper() == "ADMIN" else 1, photo_url))
    conn.commit()
    conn.close()

    return {"status": "SUCCESS", "message": f"Successfully enrolled {name.strip()} ({clean_user_id})", "photo_url": photo_url}
