"""
face_recognition_db.py
======================
Embedding-based face recognition for the humanoid robot (production-grade).

Pipeline:
  1. Detect face with InsightFace SCRFD (RetinaFace-style detector).
  2. 5-point landmark alignment + 112x112 crop.
  3. ArcFace embedding (512-dim, L2-normalised).
  4. Store embeddings in SQLite, search by cosine similarity.
  5. Return top1, top2, margin, det_score, rejection reason.

Recognition strategy:
  • InsightFace `buffalo_l` pack (download once on first run, then offline).
  • If InsightFace cannot be loaded (missing wheel, no internet for first-time
    model download, etc.) the module automatically falls back to a legacy
    LBPH / histogram recognizer that uses Haar cascades.
  • The public API (`recognize(face_crop) -> dict`) is identical in both
    modes so `robot_hardware.py` does not need to know which is active.

API surface (kept stable for backward compatibility):
  class FaceDatabase
      .is_ready           bool
      .people             dict[person_id] -> {person_id, fio, display_name}
      .recognizer_type    "insightface" | "lbph" | "histogram" | "none"
      .recognize(face_crop_bgr) -> dict
      .recognize_frame(frame_bgr) -> dict        # NEW: full pipeline on a frame
      .build_from_photos(rebuild=False) -> dict  # NEW: enroll from photos/
      .self_test() -> dict
  get_face_db()           -> FaceDatabase singleton
  reload_face_db()        -> FaceDatabase

Recognize result schema (always returned, never None):
  {
    "accepted":          bool,
    "person_id":         str,
    "fio":               str,
    "display_name":      str,
    "similarity":        float,   # cosine in [-1, 1]; 1 = identical
    "distance":          float,   # 1 - similarity (legacy compat)
    "confidence":        float,   # 0..1 mapped from similarity
    "top2_person_id":    str,
    "top2_similarity":   float,
    "top2_distance":     float,
    "margin":            float,   # similarity_top1 - similarity_top2
    "det_score":         float,   # InsightFace detector confidence (0..1)
    "bbox":              [x1, y1, x2, y2] | [],
    "rejection_reason":  str,
  }

Rejection reasons:
  no_recognizer | not_ready | bad_face_crop | no_face | low_det_score |
  small_face | low_similarity | small_margin | low_quality

Config env vars (all read at import time):
  FACE_RECOGNITION_ENABLED          true
  FACE_DATA_DIR                     face_data
  FACE_DB_PATH                      face_data/faces.sqlite
  FACE_MODEL_NAME                   buffalo_l
  FACE_DET_SIZE                     640
  FACE_MIN_DET_SCORE                0.65
  FACE_MIN_FACE_PIXELS              50
  FACE_MIN_SIMILARITY               0.45
  FACE_MIN_MARGIN                   0.08
  FACE_RECOGNITION_DEBUG            false
  # Legacy fallback knobs (only used when InsightFace fails):
  FACE_LBPH_THRESHOLD               115
  FACE_RECOGNITION_MAX_DISTANCE     0.65
  FACE_RECOGNITION_MIN_MARGIN_LBPH  15
  FACE_RECOGNITION_MIN_MARGIN_HIST  0.08
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cfg_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "ha"}


def _cfg_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"[FACE-DB] {name}: invalid value {raw!r}, using default {default}")
        return default


def _cfg_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[FACE-DB] {name}: invalid value {raw!r}, using default {default}")
        return default


def _cfg_str(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip()
    return raw or default


# ─────────────────────────────────────────────────────────────────────────────
# Paths & config
# ─────────────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.resolve()

FACE_DATA_DIR  = _PROJECT_ROOT / _cfg_str("FACE_DATA_DIR", "face_data")
PEOPLE_CSV     = FACE_DATA_DIR / "people.csv"
PHOTOS_DIR     = FACE_DATA_DIR / "photos"

_DB_PATH_RAW   = _cfg_str("FACE_DB_PATH", "face_data/faces.sqlite")
DB_PATH        = Path(_DB_PATH_RAW)
if not DB_PATH.is_absolute():
    DB_PATH = _PROJECT_ROOT / DB_PATH

# InsightFace knobs
INSIGHT_MODEL_NAME = _cfg_str("FACE_MODEL_NAME", "buffalo_l")
INSIGHT_DET_SIZE   = _cfg_int("FACE_DET_SIZE", 640)
MIN_DET_SCORE      = _cfg_float("FACE_MIN_DET_SCORE", 0.65)
MIN_FACE_PIXELS    = _cfg_int("FACE_MIN_FACE_PIXELS", 50)
MIN_SIMILARITY     = _cfg_float("FACE_MIN_SIMILARITY", 0.45)
MIN_MARGIN         = _cfg_float("FACE_MIN_MARGIN", 0.08)

DEBUG_MODE         = _cfg_bool("FACE_RECOGNITION_DEBUG", False)

# Legacy fallback knobs
LBPH_THRESHOLD     = _cfg_int("FACE_LBPH_THRESHOLD", 115)
HIST_MAX_DISTANCE  = _cfg_float("FACE_RECOGNITION_MAX_DISTANCE", 0.65)
LBPH_MIN_MARGIN    = _cfg_int("FACE_RECOGNITION_MIN_MARGIN_LBPH", 15)
HIST_MIN_MARGIN    = _cfg_float("FACE_RECOGNITION_MIN_MARGIN_HIST", 0.08)


# ─────────────────────────────────────────────────────────────────────────────
# Optional dependency probes
# ─────────────────────────────────────────────────────────────────────────────

try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_OK = False

try:
    import cv2 as _cv2
    _CV2_OK = True
except ImportError:
    _cv2 = None
    _CV2_OK = False


def _insightface_available() -> bool:
    if not (_NUMPY_OK and _CV2_OK):
        return False
    try:
        import insightface  # noqa: F401
        from insightface.app import FaceAnalysis  # noqa: F401
        return True
    except Exception:
        return False


def _lbph_available() -> bool:
    if not _CV2_OK:
        return False
    return hasattr(_cv2, "face") and hasattr(_cv2.face, "LBPHFaceRecognizer_create")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_people_csv() -> list[dict]:
    if not PEOPLE_CSV.exists():
        return []
    rows: list[dict] = []
    try:
        with open(PEOPLE_CSV, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pid = (row.get("person_id") or "").strip()
                if pid:
                    rows.append(row)
    except Exception as exc:
        print(f"[FACE-DB] Failed to read people.csv: {exc}")
    return rows


def _resolve_photo_dir(row: dict) -> Path:
    raw = (row.get("photo_dir") or "").strip()
    if not raw:
        raw = str(PHOTOS_DIR / row["person_id"])
    p = Path(raw)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    return p


def _list_person_images(photo_dir: Path) -> list[Path]:
    if not photo_dir.exists():
        return []
    images: list[Path] = []
    for ext in ("*.jpg", "*.jpeg", "*.png"):
        images.extend(photo_dir.glob(ext))
    return sorted(images)


def _laplacian_var(gray) -> float:
    """Sharpness proxy: variance of the Laplacian. Higher = sharper."""
    if not _CV2_OK:
        return 0.0
    try:
        return float(_cv2.Laplacian(gray, _cv2.CV_64F).var())
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Empty-result template
# ─────────────────────────────────────────────────────────────────────────────

def _empty_result(reason: str = "no_recognizer") -> dict:
    return {
        "accepted":         False,
        "person_id":        "",
        "fio":              "",
        "display_name":     "",
        "similarity":       0.0,
        "distance":         1.0,
        "confidence":       0.0,
        "top2_person_id":   "",
        "top2_similarity":  0.0,
        "top2_distance":    1.0,
        "margin":           0.0,
        "det_score":        0.0,
        "bbox":             [],
        "rejection_reason": reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SQLite schema
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS people (
    person_id    TEXT PRIMARY KEY,
    fio          TEXT,
    display_name TEXT,
    photo_dir    TEXT,
    created_at   TEXT,
    updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id     TEXT NOT NULL,
    image_path    TEXT NOT NULL,
    embedding     BLOB NOT NULL,
    embedding_dim INTEGER NOT NULL,
    quality_score REAL,
    det_score     REAL,
    face_bbox     TEXT,
    image_hash    TEXT,
    created_at    TEXT,
    UNIQUE(person_id, image_hash),
    FOREIGN KEY (person_id) REFERENCES people(person_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_emb_person ON face_embeddings(person_id);
CREATE INDEX IF NOT EXISTS ix_emb_hash   ON face_embeddings(image_hash);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_SQL)
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# InsightFace engine wrapper
# ─────────────────────────────────────────────────────────────────────────────

class _InsightEngine:
    """
    Lazy-loaded InsightFace FaceAnalysis pipeline.

    The first call to detect_and_embed() triggers model download / load.
    On subsequent calls it reuses the loaded model.
    """

    def __init__(self, model_name: str, det_size: int):
        self.model_name = model_name
        self.det_size = det_size
        self._app = None
        self._load_error: str | None = None

    def is_loaded(self) -> bool:
        return self._app is not None

    def load(self) -> bool:
        """Try to load the InsightFace model. Returns True on success."""
        if self._app is not None:
            return True
        if self._load_error is not None:
            return False
        try:
            from insightface.app import FaceAnalysis  # type: ignore
        except Exception as exc:
            self._load_error = f"insightface import failed: {exc}"
            print(f"[FACE-DB] {self._load_error}")
            return False

        # Prefer CPU provider; CUDA/DML providers will be picked automatically
        # if onnxruntime-gpu / DirectML is installed.
        try:
            providers = ["CPUExecutionProvider"]
            try:
                import onnxruntime as ort  # type: ignore
                avail = list(ort.get_available_providers())
                # Keep CPU last as a fallback; put GPU/DML first if present.
                ranked = [p for p in (
                    "CUDAExecutionProvider",
                    "DmlExecutionProvider",
                    "CoreMLExecutionProvider",
                    "CPUExecutionProvider",
                ) if p in avail]
                if ranked:
                    providers = ranked
            except Exception:
                pass

            t0 = time.monotonic()
            app = FaceAnalysis(name=self.model_name, providers=providers)
            app.prepare(ctx_id=0, det_size=(self.det_size, self.det_size))
            self._app = app
            elapsed = time.monotonic() - t0
            print(f"[FACE-DB] InsightFace loaded model={self.model_name} "
                  f"det_size={self.det_size} providers={providers} "
                  f"in {elapsed:.2f}s")
            return True
        except Exception as exc:
            self._load_error = f"insightface load failed: {exc}"
            print(f"[FACE-DB] {self._load_error}")
            self._app = None
            return False

    def detect(self, frame_bgr) -> list:
        """Run detection + embedding on a BGR frame. Returns list of Face objects."""
        if self._app is None and not self.load():
            return []
        try:
            return self._app.get(frame_bgr)  # type: ignore[union-attr]
        except Exception as exc:
            print(f"[FACE-DB] InsightFace .get() error: {exc}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# Quality / face filtering helpers
# ─────────────────────────────────────────────────────────────────────────────

def _largest_dominant_face(faces: list, frame_shape: tuple) -> tuple[int, str]:
    """
    Pick the index of the dominant face in a frame.

    Rules:
      • If 0 faces  → ("", "no_face")
      • If 1 face   → use it
      • If >=2 faces → pick the largest by bbox area, but only if it is at
                       least 1.6× larger than the second largest (otherwise
                       the image is ambiguous and we reject for enrollment).

    Returns (index, reason). On reject, index = -1.
    """
    if not faces:
        return -1, "no_face"
    if len(faces) == 1:
        return 0, ""
    sizes = []
    for i, f in enumerate(faces):
        try:
            x1, y1, x2, y2 = f.bbox.astype(int).tolist()
            sizes.append((i, max(0, x2 - x1) * max(0, y2 - y1)))
        except Exception:
            sizes.append((i, 0))
    sizes.sort(key=lambda x: x[1], reverse=True)
    top_i, top_area = sizes[0]
    second_area = sizes[1][1] if len(sizes) > 1 else 0
    if second_area > 0 and top_area < 1.6 * second_area:
        return -1, "ambiguous_multiple_faces"
    return top_i, ""


def _normalize_embedding(vec):
    """L2-normalise a numpy embedding. Returns float32 array."""
    if np is None:
        return vec
    arr = np.asarray(vec, dtype=np.float32)
    n = float(np.linalg.norm(arr))
    if n > 1e-9:
        arr = arr / n
    return arr.astype(np.float32)


def _embedding_to_blob(vec) -> bytes:
    arr = _normalize_embedding(vec)
    return arr.tobytes()


def _blob_to_embedding(blob: bytes, dim: int):
    return np.frombuffer(blob, dtype=np.float32, count=dim)


# ─────────────────────────────────────────────────────────────────────────────
# Legacy LBPH / histogram fallback (used only if InsightFace can't load)
# ─────────────────────────────────────────────────────────────────────────────

def _legacy_face_cascade():
    if not _CV2_OK:
        return None
    try:
        path = os.path.join(_cv2.data.haarcascades,
                            "haarcascade_frontalface_default.xml")
        cascade = _cv2.CascadeClassifier(path)
        if not cascade.empty():
            return cascade
    except Exception:
        pass
    return None


def _legacy_prepare_face(img):
    if not _CV2_OK or img is None:
        return None
    try:
        if len(img.shape) == 3:
            gray = _cv2.cvtColor(img, _cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
        gray = _cv2.equalizeHist(gray)
        gray = _cv2.resize(gray, (100, 100))
        return gray
    except Exception:
        return None


def _legacy_crop_face(img_bgr, cascade):
    if not _CV2_OK or img_bgr is None or cascade is None:
        return None, None
    gray = _cv2.cvtColor(img_bgr, _cv2.COLOR_BGR2GRAY)
    gray = _cv2.equalizeHist(gray)
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4,
        minSize=(40, 40), flags=_cv2.CASCADE_SCALE_IMAGE,
    )
    if len(faces) == 0:
        return None, None
    x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
    crop = gray[y:y + h, x:x + w]
    bbox = [int(x), int(y), int(x + w), int(y + h)]
    return _cv2.resize(crop, (100, 100)), bbox


# ─────────────────────────────────────────────────────────────────────────────
# FaceDatabase — primary public class
# ─────────────────────────────────────────────────────────────────────────────

class FaceDatabase:
    """
    Embedding-based face recognition with SQLite persistence.

    On construction:
      1. Loads people.csv into self.people.
      2. Tries to load InsightFace (buffalo_l).
      3. If InsightFace is available, ensures the SQLite DB has embeddings
         for every photo on disk (auto-builds on first run).
      4. If InsightFace cannot be loaded, falls back to LBPH/histogram so
         the robot still functions, just less reliably.
    """

    def __init__(self, data_dir: Path | None = None,
                 db_path: Path | None = None):
        self.data_dir = Path(data_dir).resolve() if data_dir else FACE_DATA_DIR
        self.db_path  = Path(db_path).resolve()  if db_path  else DB_PATH

        # Public state
        self.people: dict[str, dict] = {}
        self.recognizer_type: str = "none"
        self.is_ready: bool = False

        # InsightFace state
        self._engine: _InsightEngine | None = None
        self._embeddings: list[tuple[str, Any]] = []  # [(person_id, np.ndarray)]
        self._embedding_dim: int = 0

        # Legacy fallback state
        self._lbph = None
        self._stored_faces: dict[str, list] = {}
        self._hist_db: list[tuple[str, Any]] = []
        self._cascade = None

        self._load_people()
        if not self.people:
            print("[FACE-DB] people.csv is empty or missing — recognition disabled.")
            return

        if _insightface_available():
            self._engine = _InsightEngine(INSIGHT_MODEL_NAME, INSIGHT_DET_SIZE)
            ok = self._init_insightface_db()
            if ok:
                self.recognizer_type = "insightface"
                self.is_ready = True
                self._print_ready_banner()
                return
            print("[FACE-DB] InsightFace path failed — switching to legacy fallback.")
        else:
            print("[FACE-DB] InsightFace not available — using legacy fallback. "
                  "For best accuracy: pip install insightface onnxruntime")

        # Fallback path (LBPH / histogram)
        self._init_legacy()

    # ── people.csv ────────────────────────────────────────────────────────────

    def _load_people(self) -> None:
        rows = _load_people_csv()
        for row in rows:
            pid = row["person_id"].strip()
            self.people[pid] = {
                "person_id":    pid,
                "fio":          (row.get("fio") or pid).strip() or pid,
                "display_name": (row.get("display_name")
                                 or row.get("fio") or pid).strip() or pid,
                "photo_dir":    (row.get("photo_dir") or "").strip(),
            }

    # ── Banner ────────────────────────────────────────────────────────────────

    def _print_ready_banner(self) -> None:
        print(
            f"[FACE-DB] Ready. recognizer={self.recognizer_type} "
            f"people={len(self.people)} embeddings={len(self._embeddings)} "
            f"dim={self._embedding_dim} "
            f"min_sim={MIN_SIMILARITY} min_margin={MIN_MARGIN} "
            f"min_det={MIN_DET_SCORE}"
        )

    # ── InsightFace init / build ──────────────────────────────────────────────

    def _init_insightface_db(self) -> bool:
        """Load embeddings from SQLite, building any missing ones from photos."""
        # Load lazily on first detection — but we still need to build the DB,
        # which requires the model. Force a load now.
        if not self._engine.load():  # type: ignore[union-attr]
            return False

        conn = _connect_db(self.db_path)
        try:
            self._sync_people_table(conn)
            built = self.build_from_photos(rebuild=False, conn=conn)
            self._reload_embeddings(conn)
        finally:
            conn.close()

        if not self._embeddings:
            print("[FACE-DB] InsightFace ready but no embeddings stored — "
                  "add photos and re-run.")
            return False
        return True

    def _sync_people_table(self, conn: sqlite3.Connection) -> None:
        now = _now_iso()
        for pid, p in self.people.items():
            photo_dir = p.get("photo_dir") or str(PHOTOS_DIR / pid)
            conn.execute(
                "INSERT INTO people(person_id, fio, display_name, photo_dir, "
                "created_at, updated_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(person_id) DO UPDATE SET "
                "fio=excluded.fio, display_name=excluded.display_name, "
                "photo_dir=excluded.photo_dir, updated_at=excluded.updated_at",
                (pid, p["fio"], p["display_name"], photo_dir, now, now),
            )
        conn.commit()

    # ── Build embeddings from photos ─────────────────────────────────────────

    def build_from_photos(self, rebuild: bool = False,
                          person_id: str | None = None,
                          conn: sqlite3.Connection | None = None) -> dict:
        """
        Scan face_data/photos/* and create embeddings for each photo.

        Args:
            rebuild   : if True, drop existing rows and re-embed everything.
            person_id : if given, only build for this one person.
            conn      : optional open connection (used by __init__).

        Returns a report dict.
        """
        if self._engine is None or not self._engine.load():
            print("[FACE-DB] build_from_photos: InsightFace not available.")
            return {"error": "insightface_unavailable"}

        own_conn = conn is None
        if own_conn:
            conn = _connect_db(self.db_path)

        try:
            assert conn is not None
            if rebuild:
                if person_id:
                    conn.execute(
                        "DELETE FROM face_embeddings WHERE person_id=?",
                        (person_id,),
                    )
                else:
                    conn.execute("DELETE FROM face_embeddings")
                conn.commit()

            existing_hashes: set[tuple[str, str]] = set()
            for pid, h in conn.execute(
                "SELECT person_id, image_hash FROM face_embeddings"
            ):
                if h:
                    existing_hashes.add((pid, h))

            report = {
                "people": 0,
                "photos_scanned": 0,
                "embeddings_created": 0,
                "skipped": 0,
                "skip_reasons": {},
                "warnings": [],
            }

            target_people = (
                {person_id: self.people[person_id]}
                if person_id and person_id in self.people
                else self.people
            )

            now = _now_iso()
            for pid, p in target_people.items():
                report["people"] += 1
                photo_dir = _resolve_photo_dir({"person_id": pid,
                                                "photo_dir": p.get("photo_dir", "")})
                images = _list_person_images(photo_dir)
                if not images:
                    report["warnings"].append(f"{pid}: no photos in {photo_dir}")
                    continue

                created_for_person = 0
                for img_path in images:
                    report["photos_scanned"] += 1
                    try:
                        sha = _file_sha256(img_path)
                    except Exception as exc:
                        report["skipped"] += 1
                        report["skip_reasons"].setdefault("hash_error", 0)
                        report["skip_reasons"]["hash_error"] += 1
                        print(f"[FACE-DB] hash error for {img_path.name}: {exc}")
                        continue

                    if (pid, sha) in existing_hashes and not rebuild:
                        # Already embedded; skip silently.
                        continue

                    img = _cv2.imread(str(img_path)) if _CV2_OK else None
                    if img is None:
                        report["skipped"] += 1
                        report["skip_reasons"].setdefault("read_error", 0)
                        report["skip_reasons"]["read_error"] += 1
                        continue

                    faces = self._engine.detect(img)
                    h_img, w_img = img.shape[:2]
                    idx, why = _largest_dominant_face(faces, (h_img, w_img))
                    if idx < 0:
                        report["skipped"] += 1
                        key = why or "no_face"
                        report["skip_reasons"].setdefault(key, 0)
                        report["skip_reasons"][key] += 1
                        print(f"[FACE-DB] {pid}/{img_path.name}: skipped ({key})")
                        continue

                    f = faces[idx]
                    det_score = float(getattr(f, "det_score", 0.0))
                    if det_score < MIN_DET_SCORE:
                        report["skipped"] += 1
                        report["skip_reasons"].setdefault("low_det_score", 0)
                        report["skip_reasons"]["low_det_score"] += 1
                        print(f"[FACE-DB] {pid}/{img_path.name}: skipped "
                              f"(det_score {det_score:.2f} < {MIN_DET_SCORE})")
                        continue

                    bbox = f.bbox.astype(int).tolist()
                    bw = max(0, bbox[2] - bbox[0])
                    bh = max(0, bbox[3] - bbox[1])
                    if min(bw, bh) < MIN_FACE_PIXELS:
                        report["skipped"] += 1
                        report["skip_reasons"].setdefault("small_face", 0)
                        report["skip_reasons"]["small_face"] += 1
                        print(f"[FACE-DB] {pid}/{img_path.name}: skipped "
                              f"(face too small: {bw}x{bh})")
                        continue

                    # Quality: variance of Laplacian on the face crop
                    quality = 0.0
                    try:
                        cx1 = max(0, bbox[0]); cy1 = max(0, bbox[1])
                        cx2 = min(w_img, bbox[2]); cy2 = min(h_img, bbox[3])
                        crop = img[cy1:cy2, cx1:cx2]
                        if crop.size > 0:
                            gray = _cv2.cvtColor(crop, _cv2.COLOR_BGR2GRAY)
                            quality = _laplacian_var(gray)
                    except Exception:
                        quality = 0.0

                    emb = getattr(f, "normed_embedding", None)
                    if emb is None:
                        emb = getattr(f, "embedding", None)
                    if emb is None:
                        report["skipped"] += 1
                        report["skip_reasons"].setdefault("no_embedding", 0)
                        report["skip_reasons"]["no_embedding"] += 1
                        continue

                    blob = _embedding_to_blob(emb)
                    dim = int(np.frombuffer(blob, dtype=np.float32).shape[0])

                    try:
                        conn.execute(
                            "INSERT INTO face_embeddings("
                            "person_id, image_path, embedding, embedding_dim, "
                            "quality_score, det_score, face_bbox, image_hash, "
                            "created_at) VALUES (?,?,?,?,?,?,?,?,?) "
                            "ON CONFLICT(person_id, image_hash) DO UPDATE SET "
                            "embedding=excluded.embedding, "
                            "embedding_dim=excluded.embedding_dim, "
                            "quality_score=excluded.quality_score, "
                            "det_score=excluded.det_score, "
                            "face_bbox=excluded.face_bbox",
                            (pid, str(img_path.relative_to(_PROJECT_ROOT)
                                      if str(img_path).startswith(str(_PROJECT_ROOT))
                                      else img_path),
                             blob, dim, quality, det_score,
                             json.dumps(bbox), sha, now),
                        )
                        existing_hashes.add((pid, sha))
                        created_for_person += 1
                        report["embeddings_created"] += 1
                    except Exception as exc:
                        print(f"[FACE-DB] insert error for {img_path}: {exc}")

                if created_for_person > 0:
                    print(f"[FACE-DB] {pid}: built {created_for_person} new "
                          f"embedding(s)")

            conn.commit()

            # Warn about under-photographed people
            for pid in self.people:
                count = conn.execute(
                    "SELECT COUNT(1) FROM face_embeddings WHERE person_id=?",
                    (pid,),
                ).fetchone()[0]
                if count < 3:
                    msg = (f"{pid}: only {count} embedding(s) — "
                           "recognition will be conservative. "
                           "Add at least 3 clear photos for better accuracy.")
                    report["warnings"].append(msg)
                    print(f"[FACE-DB] WARNING {msg}")

            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("last_build_at", _now_iso()),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("model_name", INSIGHT_MODEL_NAME),
            )
            conn.commit()
            return report
        finally:
            if own_conn and conn is not None:
                conn.close()

    # ── Reload embeddings from SQLite into memory ────────────────────────────

    def _reload_embeddings(self, conn: sqlite3.Connection) -> None:
        self._embeddings = []
        self._embedding_dim = 0
        for pid, blob, dim in conn.execute(
            "SELECT person_id, embedding, embedding_dim FROM face_embeddings"
        ):
            try:
                vec = _blob_to_embedding(blob, int(dim))
                self._embeddings.append((pid, vec))
                if self._embedding_dim == 0:
                    self._embedding_dim = int(dim)
            except Exception as exc:
                print(f"[FACE-DB] embedding decode error for {pid}: {exc}")


    # ── InsightFace recognition ──────────────────────────────────────────────

    def _search_embedding(self, query_vec) -> tuple:
        """Cosine search over stored embeddings. Returns (top1, top2) tuples."""
        if not self._embeddings or np is None:
            return ((-1.0, ""), (-1.0, ""))
        # Stack stored embeddings once per call (small DB so this is cheap).
        # For larger DBs, cache the matrix in self.
        all_pids: list[str] = [p for p, _ in self._embeddings]
        mat = np.stack([v for _, v in self._embeddings])  # (N, D), L2-normed
        q = _normalize_embedding(query_vec)
        sims = mat @ q  # cosine since both normed
        # Best similarity per person across all photos
        best_per_pid: dict[str, float] = {}
        for pid, s in zip(all_pids, sims.tolist()):
            if pid not in best_per_pid or s > best_per_pid[pid]:
                best_per_pid[pid] = float(s)
        ranked = sorted(best_per_pid.items(), key=lambda x: x[1], reverse=True)
        top1 = ranked[0] if ranked else (-1.0, "")
        top2 = ranked[1] if len(ranked) > 1 else (-1.0, "")
        # Note: tuples are (pid, sim) — we return as (sim, pid) for parity
        # with legacy code structure.
        return ((top1[1], top1[0]), (top2[1], top2[0]))

    def _recognize_with_insightface_face(self, face_obj, det_score: float,
                                         bbox: list[int]) -> dict:
        emb = getattr(face_obj, "normed_embedding", None)
        if emb is None:
            emb = getattr(face_obj, "embedding", None)
        if emb is None:
            return {**_empty_result("no_embedding"), "det_score": det_score,
                    "bbox": bbox}

        (sim1, pid1), (sim2, pid2) = self._search_embedding(emb)
        if pid1 == "":
            return {**_empty_result("no_match"), "det_score": det_score,
                    "bbox": bbox}

        person = self.people.get(pid1, {})
        margin = float(sim1 - sim2)
        # Map similarity to a 0..1 confidence proxy.
        # similarity tends to fall in [-1, 1]; for ArcFace genuine matches are
        # commonly > 0.4, impostor pairs around 0.1–0.3.
        confidence = max(0.0, min(1.0, (sim1 - 0.1) / 0.7))

        if DEBUG_MODE:
            print(f"[FACE-REC] top1={pid1} sim={sim1:.3f} "
                  f"top2={pid2} sim2={sim2:.3f} margin={margin:.3f} "
                  f"det={det_score:.2f}")

        result = {
            "accepted":         True,
            "person_id":        pid1,
            "fio":              person.get("fio", pid1),
            "display_name":     person.get("display_name", pid1),
            "similarity":       round(float(sim1), 4),
            "distance":         round(float(1.0 - sim1), 4),
            "confidence":       round(float(confidence), 3),
            "top2_person_id":   pid2,
            "top2_similarity":  round(float(sim2), 4),
            "top2_distance":    round(float(1.0 - sim2), 4),
            "margin":           round(float(margin), 4),
            "det_score":        round(float(det_score), 3),
            "bbox":             list(bbox),
            "rejection_reason": "",
        }

        if det_score < MIN_DET_SCORE:
            result["accepted"] = False
            result["rejection_reason"] = f"low_det_score:{det_score:.2f}<{MIN_DET_SCORE}"
            return result
        if sim1 < MIN_SIMILARITY:
            result["accepted"] = False
            result["rejection_reason"] = (
                f"low_similarity:{sim1:.3f}<{MIN_SIMILARITY}"
            )
            return result
        if margin < MIN_MARGIN:
            result["accepted"] = False
            result["rejection_reason"] = f"small_margin:{margin:.3f}<{MIN_MARGIN}"
            return result

        print(f"[FACE-REC] candidate top1={pid1} sim={sim1:.3f} "
              f"top2={pid2} sim2={sim2:.3f} margin={margin:.3f} "
              f"conf={confidence:.2f} det={det_score:.2f}")
        return result

    # ── Public recognize_frame: full pipeline on a frame ─────────────────────

    def recognize_frame(self, frame_bgr) -> dict:
        """
        Run full detect → align → embed → search on a BGR frame.
        Picks the largest face if multiple are present.
        """
        if not self.is_ready:
            return _empty_result("not_ready")

        if self.recognizer_type == "insightface" and self._engine is not None:
            faces = self._engine.detect(frame_bgr)
            if not faces:
                return _empty_result("no_face")
            # Pick largest face for recognition (allow multiple in frame).
            best_i = 0
            best_area = -1
            for i, f in enumerate(faces):
                try:
                    x1, y1, x2, y2 = f.bbox.astype(int).tolist()
                    a = max(0, x2 - x1) * max(0, y2 - y1)
                    if a > best_area:
                        best_area = a
                        best_i = i
                except Exception:
                    continue
            f = faces[best_i]
            bbox = f.bbox.astype(int).tolist()
            det_score = float(getattr(f, "det_score", 0.0))
            return self._recognize_with_insightface_face(f, det_score, bbox)

        # Legacy fallback: Haar crop + LBPH/histogram
        crop, bbox = _legacy_crop_face(frame_bgr, self._cascade)
        if crop is None:
            return _empty_result("no_face")
        result = self.recognize(crop)
        if bbox:
            result["bbox"] = bbox
        return result

    # ── Public recognize: accepts a face crop (legacy compat) ────────────────

    def recognize(self, face_crop) -> dict:
        """
        Identify a face from a crop (BGR or grayscale).

        For InsightFace: the crop is run through the full pipeline as if it
        were a small frame, so any caller that already cropped a face
        (e.g. the camera loop) still works.
        """
        if not self.is_ready:
            return _empty_result("not_ready")
        if face_crop is None:
            return _empty_result("bad_face_crop")

        if self.recognizer_type == "insightface" and self._engine is not None:
            # Treat the crop as a frame: detector will re-detect within the crop.
            # If the crop is already tightly cropped, det may fail; in that
            # case we pad and retry once.
            return self._insight_recognize_crop(face_crop)

        if self.recognizer_type == "lbph":
            return self._legacy_recognize_lbph(face_crop)
        if self.recognizer_type == "histogram":
            return self._legacy_recognize_histogram(face_crop)
        return _empty_result("no_recognizer")

    def _insight_recognize_crop(self, crop) -> dict:
        if np is None or _cv2 is None:
            return _empty_result("no_recognizer")

        img = crop
        # Ensure 3-channel BGR
        try:
            if len(img.shape) == 2:
                img = _cv2.cvtColor(img, _cv2.COLOR_GRAY2BGR)
        except Exception:
            return _empty_result("bad_face_crop")

        for attempt in range(2):
            faces = self._engine.detect(img) if self._engine else []
            if faces:
                # Pick the largest face.
                best_i = 0; best_area = -1
                for i, f in enumerate(faces):
                    try:
                        x1, y1, x2, y2 = f.bbox.astype(int).tolist()
                        a = max(0, x2 - x1) * max(0, y2 - y1)
                        if a > best_area:
                            best_area = a; best_i = i
                    except Exception:
                        continue
                f = faces[best_i]
                bbox = f.bbox.astype(int).tolist()
                det_score = float(getattr(f, "det_score", 0.0))
                return self._recognize_with_insightface_face(f, det_score, bbox)

            # Pad and retry once — tight crops sometimes confuse the detector.
            if attempt == 0:
                try:
                    h, w = img.shape[:2]
                    pad = max(20, max(h, w) // 5)
                    img = _cv2.copyMakeBorder(
                        img, pad, pad, pad, pad,
                        _cv2.BORDER_REPLICATE,
                    )
                except Exception:
                    break
        return _empty_result("no_face")

    # ── Legacy LBPH / histogram fallback ─────────────────────────────────────

    def _init_legacy(self) -> None:
        if not _CV2_OK:
            print("[FACE-DB] OpenCV missing — face recognition disabled.")
            return

        self._cascade = _legacy_face_cascade()
        if self._cascade is None:
            print("[FACE-DB] Haar cascade missing — recognition disabled.")
            return

        faces_per_person: dict[str, list] = {}
        loaded = rejected = 0
        for pid, p in self.people.items():
            photo_dir = _resolve_photo_dir({"person_id": pid,
                                            "photo_dir": p.get("photo_dir", "")})
            if not photo_dir.exists():
                continue
            person_faces = []
            for img_path in _list_person_images(photo_dir):
                img = _cv2.imread(str(img_path))
                crop, _ = _legacy_crop_face(img, self._cascade)
                if crop is None:
                    rejected += 1
                    continue
                person_faces.append(crop)
                loaded += 1
            if person_faces:
                faces_per_person[pid] = person_faces
                self._stored_faces[pid] = person_faces

        if not faces_per_person:
            print("[FACE-DB] Legacy fallback: no usable photos. Disabled.")
            return

        if _lbph_available():
            try:
                all_faces, all_labels = [], []
                self._label_to_pid = {}
                for label, (pid, faces) in enumerate(faces_per_person.items()):
                    self._label_to_pid[label] = pid
                    for f in faces:
                        all_faces.append(f); all_labels.append(label)
                self._lbph = _cv2.face.LBPHFaceRecognizer_create(
                    radius=1, neighbors=8, grid_x=8, grid_y=8,
                )
                self._lbph.train(all_faces, np.array(all_labels, dtype=np.int32))
                self.recognizer_type = "lbph"
                self.is_ready = True
                print(f"[FACE-DB] Legacy LBPH ready (people={len(self.people)}, "
                      f"photos={loaded}, rejected={rejected}, "
                      f"threshold={LBPH_THRESHOLD})")
                return
            except Exception as exc:
                print(f"[FACE-DB] LBPH init failed: {exc}")

        # Histogram last resort
        for pid, faces in faces_per_person.items():
            hists = []
            for face in faces:
                h = _cv2.calcHist([face], [0], None, [256], [0, 256])
                h = h.flatten().astype(np.float32)
                norm = float(np.linalg.norm(h))
                if norm > 0:
                    h /= norm
                hists.append(h)
            self._hist_db.append((pid, np.mean(hists, axis=0)))
        self.recognizer_type = "histogram"
        self.is_ready = True
        print(f"[FACE-DB] Legacy histogram ready (people={len(self.people)}, "
              f"photos={loaded})")

    def _legacy_recognize_lbph(self, face) -> dict:
        gray = _legacy_prepare_face(face)
        if gray is None:
            return _empty_result("bad_face_crop")
        try:
            label, dist = self._lbph.predict(gray)
        except Exception as exc:
            return _empty_result(f"lbph_error:{exc}")
        # LBPH does not give top2; compute by training mini-recognizers.
        all_dists = []
        for pid, faces in self._stored_faces.items():
            try:
                tmp = _cv2.face.LBPHFaceRecognizer_create(
                    radius=1, neighbors=8, grid_x=8, grid_y=8)
                tmp.train(faces, np.zeros(len(faces), dtype=np.int32))
                _, d = tmp.predict(gray)
                all_dists.append((d, pid))
            except Exception:
                all_dists.append((9999.0, pid))
        all_dists.sort(key=lambda x: x[0])
        d1, pid1 = all_dists[0]
        d2, pid2 = (all_dists[1] if len(all_dists) > 1 else (9999.0, ""))
        margin = d2 - d1
        person = self.people.get(pid1, {})
        confidence = max(0.0, 1.0 - d1 / max(LBPH_THRESHOLD, 1))
        sim1 = max(0.0, 1.0 - d1 / 200.0)
        sim2 = max(0.0, 1.0 - d2 / 200.0)
        result = {
            "accepted": True,
            "person_id": pid1,
            "fio": person.get("fio", pid1),
            "display_name": person.get("display_name", pid1),
            "similarity": round(sim1, 4),
            "distance": round(d1, 1),
            "confidence": round(confidence, 3),
            "top2_person_id": pid2,
            "top2_similarity": round(sim2, 4),
            "top2_distance": round(d2, 1),
            "margin": round(margin, 1),
            "det_score": 0.0,
            "bbox": [],
            "rejection_reason": "",
        }
        if d1 > LBPH_THRESHOLD:
            result["accepted"] = False
            result["rejection_reason"] = f"distance_too_high:{d1:.1f}>{LBPH_THRESHOLD}"
            return result
        if margin < LBPH_MIN_MARGIN:
            result["accepted"] = False
            result["rejection_reason"] = f"margin_too_small:{margin:.1f}<{LBPH_MIN_MARGIN}"
            return result
        return result

    def _legacy_recognize_histogram(self, face) -> dict:
        gray = _legacy_prepare_face(face)
        if gray is None:
            return _empty_result("bad_face_crop")
        h = _cv2.calcHist([gray], [0], None, [256], [0, 256])
        h = h.flatten().astype(np.float32)
        n = float(np.linalg.norm(h))
        if n > 0:
            h /= n
        all_dists = []
        for pid, ref in self._hist_db:
            d = float(np.linalg.norm(h - ref))
            all_dists.append((d, pid))
        all_dists.sort(key=lambda x: x[0])
        d1, pid1 = all_dists[0]
        d2, pid2 = (all_dists[1] if len(all_dists) > 1 else (9999.0, ""))
        margin = d2 - d1
        person = self.people.get(pid1, {})
        confidence = max(0.0, 1.0 - d1 / max(HIST_MAX_DISTANCE, 1e-6))
        sim1 = max(0.0, 1.0 - d1)
        sim2 = max(0.0, 1.0 - d2)
        result = {
            "accepted": True, "person_id": pid1,
            "fio": person.get("fio", pid1),
            "display_name": person.get("display_name", pid1),
            "similarity": round(sim1, 4),
            "distance": round(d1, 4),
            "confidence": round(confidence, 3),
            "top2_person_id": pid2,
            "top2_similarity": round(sim2, 4),
            "top2_distance": round(d2, 4),
            "margin": round(margin, 4),
            "det_score": 0.0,
            "bbox": [],
            "rejection_reason": "",
        }
        if d1 > HIST_MAX_DISTANCE:
            result["accepted"] = False
            result["rejection_reason"] = f"hist_distance_too_high:{d1:.3f}>{HIST_MAX_DISTANCE}"
            return result
        if margin < HIST_MIN_MARGIN:
            result["accepted"] = False
            result["rejection_reason"] = f"hist_margin_too_small:{margin:.3f}<{HIST_MIN_MARGIN}"
            return result
        return result

    # ── Self-test ────────────────────────────────────────────────────────────

    def self_test(self) -> dict:
        """For each enrolled photo, recognize and verify the best match is itself."""
        if not self.is_ready:
            return {"passed": 0, "failed": 0, "results": [],
                    "note": "recognizer not ready"}

        results: list[dict] = []
        passed = failed = 0
        for pid, p in self.people.items():
            photo_dir = _resolve_photo_dir({"person_id": pid,
                                            "photo_dir": p.get("photo_dir", "")})
            for img_path in _list_person_images(photo_dir):
                img = _cv2.imread(str(img_path)) if _CV2_OK else None
                if img is None:
                    continue
                r = self.recognize_frame(img)
                ok = r.get("accepted") and r.get("person_id") == pid
                entry = {
                    "person_id": pid,
                    "image": img_path.name,
                    "status": "PASS" if ok else "FAIL",
                    "got": r.get("person_id", ""),
                    "similarity": r.get("similarity", 0.0),
                    "margin": r.get("margin", 0.0),
                    "det_score": r.get("det_score", 0.0),
                    "reason": r.get("rejection_reason", ""),
                }
                results.append(entry)
                if ok:
                    passed += 1
                else:
                    failed += 1
        return {"passed": passed, "failed": failed, "results": results}


# ─────────────────────────────────────────────────────────────────────────────
# Module singleton
# ─────────────────────────────────────────────────────────────────────────────

_db: FaceDatabase | None = None


def get_face_db() -> FaceDatabase:
    global _db
    if _db is None:
        _db = FaceDatabase()
    return _db


def reload_face_db() -> FaceDatabase:
    global _db
    _db = FaceDatabase()
    return _db


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _print_self_test(report: dict) -> None:
    print()
    print("Self-test results:")
    for r in report["results"]:
        if r["status"] == "PASS":
            print(f"  [PASS] {r['person_id']:30s} "
                  f"img={r['image']:14s} "
                  f"sim={r['similarity']:.3f} "
                  f"margin={r['margin']:.3f} "
                  f"det={r['det_score']:.2f}")
        else:
            print(f"  [FAIL] {r['person_id']:30s} "
                  f"img={r['image']:14s} "
                  f"got={r['got'] or '?':30s} "
                  f"sim={r['similarity']:.3f} "
                  f"reason={r['reason']}")
    print(f"\n{report['passed']} passed, {report['failed']} failed "
          f"out of {report['passed'] + report['failed']} photo(s).")


if __name__ == "__main__":
    os.environ.setdefault("ESP32_SERIAL_ENABLED", "false")

    args = set(sys.argv[1:])
    rebuild = "--rebuild" in args
    self_test = "--self-test" in args or not args

    print("=" * 70)
    print("face_recognition_db.py — dry-run")
    print("=" * 70)
    print(f"  data_dir         : {FACE_DATA_DIR}")
    print(f"  db_path          : {DB_PATH}")
    print(f"  insightface ok   : {_insightface_available()}")
    print(f"  numpy/cv2 ok     : {_NUMPY_OK} / {_CV2_OK}")
    print(f"  model            : {INSIGHT_MODEL_NAME}")
    print(f"  min_det / min_sim / min_margin : "
          f"{MIN_DET_SCORE} / {MIN_SIMILARITY} / {MIN_MARGIN}")
    print()

    db = get_face_db()
    print(f"Loaded recognizer={db.recognizer_type} people={len(db.people)} "
          f"ready={db.is_ready}")

    if rebuild and db.recognizer_type == "insightface":
        print("\nRebuilding embeddings...")
        report = db.build_from_photos(rebuild=True)
        print(f"  people             : {report.get('people', 0)}")
        print(f"  photos_scanned     : {report.get('photos_scanned', 0)}")
        print(f"  embeddings_created : {report.get('embeddings_created', 0)}")
        print(f"  skipped            : {report.get('skipped', 0)} "
              f"reasons={report.get('skip_reasons', {})}")
        for w in report.get("warnings", []):
            print(f"  [warn] {w}")
        # Reload after rebuild
        conn = _connect_db(db.db_path)
        try:
            db._reload_embeddings(conn)
        finally:
            conn.close()

    if self_test and db.is_ready:
        report = db.self_test()
        _print_self_test(report)
        if report["failed"] > 0 and report["passed"] == 0:
            sys.exit(1)
