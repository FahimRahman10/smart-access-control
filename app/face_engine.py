import os
import re
import cv2
import pickle
import shutil
import numpy as np
from typing import Dict, Any, Optional, Tuple
from app.database import get_user_by_id

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DATASET_DIR = os.path.join(BASE_DIR, "dataset")

YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")
ENCODINGS_CACHE = os.path.join(MODELS_DIR, "encodings.pkl")

# Folder to User ID mapping
FOLDER_USER_MAP = {
    "admin_fahim": "ADM0001",
    "user_adm001": "ADM0001",
    "adm0001": "ADM0001",
    "adm001": "ADM0001",
}

class FaceRecognitionEngine:
    def __init__(self, score_threshold: float = 0.6, cosine_threshold: float = 0.65):
        self.score_threshold = score_threshold
        self.cosine_threshold = cosine_threshold
        
        # Initialize YuNet face detector
        self.detector = cv2.FaceDetectorYN.create(
            model=YUNET_PATH,
            config="",
            input_size=(320, 320),
            score_threshold=score_threshold,
            nms_threshold=0.3,
            top_k=5000
        )
        
        # Initialize SFace recognizer
        self.recognizer = cv2.FaceRecognizerSF.create(
            model=SFACE_PATH,
            config=""
        )
        
        # Enrolled profiles: {user_id: [feature_vector_1, ...]}
        self.known_embeddings: Dict[str, list] = {}
        self.load_or_build_index()

    def extract_face_feature(self, img_bgr: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[dict]]:
        """
        Detects the primary face in the image and extracts its 128-D SFace feature vector.
        Safely validates input and caps resolution to avoid CPU denial-of-service.
        Returns: (feature_vector, bbox_and_landmarks_dict)
        """
        if img_bgr is None or not isinstance(img_bgr, np.ndarray) or img_bgr.size == 0:
            return None, None

        # Downsample extremely large images to maintain fast real-time inference
        h, w = img_bgr.shape[:2]
        max_dim = 1080
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            h, w = img_bgr.shape[:2]

        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(img_bgr)
        if faces is None or len(faces) == 0:
            return None, None
        
        face_count = len(faces)
        # Pick the most prominent / highest confidence face
        primary_face = max(faces, key=lambda f: f[14])
        aligned_face = self.recognizer.alignCrop(img_bgr, primary_face)
        feature = self.recognizer.feature(aligned_face)
        
        box = {
            "x": int(primary_face[0]),
            "y": int(primary_face[1]),
            "w": int(primary_face[2]),
            "h": int(primary_face[3]),
            "score": float(primary_face[14]),
            "face_count": face_count
        }
        return feature, box

    def load_or_build_index(self, force_rebuild: bool = False):
        """Loads embeddings from cache, or scans dataset/ to build them."""
        if os.path.exists(ENCODINGS_CACHE) and not force_rebuild:
            try:
                with open(ENCODINGS_CACHE, "rb") as f:
                    self.known_embeddings = pickle.load(f)
                print(f"[FaceEngine] Loaded {len(self.known_embeddings)} enrolled identities from cache.")
                return
            except Exception as e:
                print(f"[FaceEngine] Failed to load cache: {e}. Rebuilding index...")

        self.rebuild_index()

    def rebuild_index(self):
        """Scans dataset directory and generates feature embeddings for all known people."""
        print("[FaceEngine] Scanning dataset directory to build face embeddings...")
        embeddings = {}

        if not os.path.exists(DATASET_DIR):
            os.makedirs(DATASET_DIR, exist_ok=True)

        for folder_name in os.listdir(DATASET_DIR):
            if folder_name == "intruder_sample":
                continue # Do not enroll the test intruder!
                
            folder_path = os.path.join(DATASET_DIR, folder_name)
            if not os.path.isdir(folder_path):
                continue
                
            if folder_name in FOLDER_USER_MAP:
                user_id = FOLDER_USER_MAP[folder_name]
            elif folder_name.startswith("user_"):
                user_id = folder_name[5:].upper()
            else:
                user_id = folder_name.upper()
            user_vectors = []

            for filename in os.listdir(folder_path):
                if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                file_path = os.path.join(folder_path, filename)
                img = cv2.imread(file_path)
                if img is None:
                    continue
                feat, _ = self.extract_face_feature(img)
                if feat is not None:
                    user_vectors.append(feat)

            if user_vectors:
                embeddings[user_id] = user_vectors
                print(f"[FaceEngine] Enrolled {user_id} with {len(user_vectors)} face sample(s).")

        self.known_embeddings = embeddings
        os.makedirs(MODELS_DIR, exist_ok=True)
        with open(ENCODINGS_CACHE, "wb") as f:
            pickle.dump(embeddings, f)
        print(f"[FaceEngine] Index saved with {len(embeddings)} identities.")

    def verify(self, img_bgr: np.ndarray, threshold: Optional[float] = None) -> Dict[str, Any]:
        """
        Verifies an incoming face frame against all enrolled users.
        """
        thresh = threshold if threshold is not None else self.cosine_threshold
        feature, box = self.extract_face_feature(img_bgr)
        
        if feature is None:
            return {
                "status": "DENIED",
                "reason": "NO_FACE_DETECTED",
                "message": "No human face detected. Please position your face within the frame.",
                "confidence": 0.0,
                "user": None,
                "box": None
            }

        best_score = -1.0
        best_user_id = None

        for user_id, vectors in self.known_embeddings.items():
            for v in vectors:
                score = float(self.recognizer.match(feature, v, cv2.FaceRecognizerSF_FR_COSINE))
                if score > best_score:
                    best_score = score
                    best_user_id = user_id

        # Normalize score into percentage display (0 to 100%)
        # For Cosine similarity, 0.65+ is a positive match, 1.0 is identical
        confidence_pct = max(0.0, min(100.0, best_score * 100))
        face_count = box.get("face_count", 1) if box else 0
        tailgating_warning = face_count > 1

        if best_score >= thresh and best_user_id:
            user_info = get_user_by_id(best_user_id)
            if not user_info:
                # Fallback to prevent false rejection if database sync lagged
                user_info = {
                    "user_id": best_user_id,
                    "name": f"Personnel ({best_user_id})",
                    "role": "ADMIN" if "ADM" in best_user_id else "EMPLOYEE",
                    "department": "Security Enrolled",
                    "access_level": 2 if "ADM" in best_user_id else 1,
                    "photo_url": f"/static/samples/{best_user_id.lower()}.jpg"
                }

            role = user_info.get("role", "EMPLOYEE")
            grant_msg = f"ACCESS GRANTED — Welcome {user_info['name']} ({role})"
            if tailgating_warning:
                grant_msg += f" [WARNING: {face_count} faces detected in frame - possible tailgating]"

            return {
                "status": "GRANTED",
                "reason": "IDENTITY_VERIFIED",
                "message": grant_msg,
                "confidence": round(confidence_pct, 1),
                "raw_score": round(best_score, 4),
                "threshold": thresh,
                "tailgating_warning": tailgating_warning,
                "user": user_info,
                "box": box
            }

        # Face detected, but does not match any enrolled identity
        denied_msg = "ACCESS DENIED — Unrecognized identity. Intruder warning logged."
        if tailgating_warning:
            denied_msg += f" [WARNING: {face_count} faces detected]"

        return {
            "status": "DENIED",
            "reason": "UNRECOGNIZED_FACE",
            "message": denied_msg,
            "confidence": round(confidence_pct, 1),
            "raw_score": round(best_score, 4),
            "threshold": thresh,
            "tailgating_warning": tailgating_warning,
            "user": None,
            "box": box
        }

    def enroll_new_image(self, user_id: str, img_bgr: np.ndarray, save_filename: str = "custom_face.jpg", replace_existing: bool = False) -> bool:
        """Dynamically add or replace a photo for an enrolled user."""
        clean_uid = re.sub(r'[^a-zA-Z0-9_-]', '', str(user_id).strip()).upper()
        if not clean_uid:
            return False

        feat, _ = self.extract_face_feature(img_bgr)
        if feat is None:
            # Fallback: attempt detection with a more forgiving threshold for mobile/webcam photos
            try:
                h, w = img_bgr.shape[:2]
                temp_detector = cv2.FaceDetectorYN.create(
                    model=YUNET_PATH,
                    config="",
                    input_size=(w, h),
                    score_threshold=0.35,
                    nms_threshold=0.3,
                    top_k=5000
                )
                _, faces = temp_detector.detect(img_bgr)
                if faces is not None and len(faces) > 0:
                    primary_face = max(faces, key=lambda f: f[14])
                    aligned_face = self.recognizer.alignCrop(img_bgr, primary_face)
                    feat = self.recognizer.feature(aligned_face)
            except Exception as e:
                print(f"[FaceEngine] Fallback detection error: {e}")

        if feat is None:
            return False
            
        target_folder = None
        for folder, uid in FOLDER_USER_MAP.items():
            if uid == clean_uid or uid.replace("000", "0") == clean_uid.replace("000", "0"):
                target_folder = folder
                break
        if not target_folder:
            target_folder = f"user_{clean_uid.lower()}"
            FOLDER_USER_MAP[target_folder] = clean_uid
            
        folder_path = os.path.join(DATASET_DIR, target_folder)
        os.makedirs(folder_path, exist_ok=True)
        cv2.imwrite(os.path.join(folder_path, save_filename), img_bgr)
        
        # Update in-memory vectors
        if replace_existing:
            self.known_embeddings[clean_uid] = [feat]
        else:
            if clean_uid not in self.known_embeddings:
                self.known_embeddings[clean_uid] = []
            self.known_embeddings[clean_uid].append(feat)
        
        # Save cache
        with open(ENCODINGS_CACHE, "wb") as f:
            pickle.dump(self.known_embeddings, f)
        return True

    def rename_user(self, old_id: str, new_id: str):
        """Transfers face embeddings, folder mappings, and dataset folders to a new employee ID."""
        old_uid = re.sub(r'[^a-zA-Z0-9_-]', '', str(old_id).strip()).upper()
        new_uid = re.sub(r'[^a-zA-Z0-9_-]', '', str(new_id).strip()).upper()
        if not old_uid or not new_uid or old_uid == new_uid:
            return

        # 1. Transfer embeddings
        embeddings = []
        for key in list(self.known_embeddings.keys()):
            k_clean = key.upper()
            if k_clean == old_uid or k_clean.replace("000", "0") == old_uid.replace("000", "0"):
                embeddings.extend(self.known_embeddings.pop(key))
        if embeddings:
            self.known_embeddings[new_uid] = embeddings

        # 2. Update folder map
        for folder, uid in list(FOLDER_USER_MAP.items()):
            if uid.upper() == old_uid or uid.upper().replace("000", "0") == old_uid.replace("000", "0"):
                FOLDER_USER_MAP[folder] = new_uid

        # 3. Rename dataset folder if exists
        old_dataset_folder = os.path.join(DATASET_DIR, f"user_{old_uid.lower()}")
        new_dataset_folder = os.path.join(DATASET_DIR, f"user_{new_uid.lower()}")
        if os.path.exists(old_dataset_folder) and not os.path.exists(new_dataset_folder):
            try:
                os.rename(old_dataset_folder, new_dataset_folder)
            except Exception:
                pass

        # 4. Save cache
        with open(ENCODINGS_CACHE, "wb") as f:
            pickle.dump(self.known_embeddings, f)

    def delete_user_dataset(self, user_id: str):
        """Deletes face dataset, sample photo, and embeddings for an enrolled user."""
        uid_upper = re.sub(r'[^a-zA-Z0-9_-]', '', str(user_id).strip()).upper()
        if not uid_upper:
            return

        if uid_upper in self.known_embeddings:
            del self.known_embeddings[uid_upper]
            with open(ENCODINGS_CACHE, "wb") as f:
                pickle.dump(self.known_embeddings, f)
            print(f"[FaceEngine] Deleted embeddings for {uid_upper}")
        
        # Remove dataset folder if present
        if os.path.exists(DATASET_DIR):
            for folder_name in os.listdir(DATASET_DIR):
                folder_path = os.path.join(DATASET_DIR, folder_name)
                if not os.path.isdir(folder_path):
                    continue
                clean_name = folder_name.upper()
                if (clean_name == uid_upper or 
                    clean_name.startswith(f"{uid_upper}_") or 
                    clean_name == f"USER_{uid_upper}"):
                    try:
                        shutil.rmtree(folder_path)
                        print(f"[FaceEngine] Removed folder: {folder_path}")
                    except Exception as e:
                        print(f"[FaceEngine] Error removing {folder_path}: {e}")

        # Remove sample photo from static/samples if exists
        static_sample = os.path.join(BASE_DIR, "app", "static", "samples", f"{uid_upper.lower()}.jpg")
        if os.path.exists(static_sample):
            try:
                os.remove(static_sample)
            except Exception:
                pass

# Singleton engine instance
engine: Optional[FaceRecognitionEngine] = None

def get_engine() -> FaceRecognitionEngine:
    global engine
    if engine is None:
        engine = FaceRecognitionEngine()
    return engine
