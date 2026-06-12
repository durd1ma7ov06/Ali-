"""
face_dataset_builder.py
=======================
Local desktop GUI for building a face-recognition dataset.

Dataset layout
--------------
face_data/
  photos/
    <person_id>/
      01.jpg
      02.jpg
      ...
  people.csv
  manifest.json

Run:
    python face_dataset_builder.py

Dependencies:
    Pillow  (pip install Pillow)
    tkinter (stdlib on Windows/macOS; on Linux: sudo apt install python3-tk)
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

# ── Try Pillow ────────────────────────────────────────────────────────────────
try:
    from PIL import Image as _PILImage
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILLOW_AVAILABLE = False

# ── Paths ─────────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.resolve()
FACE_DATA_DIR = _PROJECT_ROOT / "face_data"
PHOTOS_DIR    = FACE_DATA_DIR / "photos"
PEOPLE_CSV    = FACE_DATA_DIR / "people.csv"
MANIFEST_JSON = FACE_DATA_DIR / "manifest.json"

SCHEMA_VERSION = "1.0"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _slug(fio: str) -> str:
    """'Ali Valiyev' → 'ali_valiyev'"""
    s = fio.strip().lower()
    s = re.sub(r"[^\w\s]", "", s)          # remove punctuation
    s = re.sub(r"\s+", "_", s)             # spaces → underscore
    s = re.sub(r"_+", "_", s).strip("_")   # collapse underscores
    return s or "unknown"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_valid_image_ext(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_EXTENSIONS


def _save_image(src: Path, dest: Path) -> None:
    """Copy src → dest as JPEG (RGB). Falls back to raw copy if Pillow absent."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if _PILLOW_AVAILABLE:
        with _PILImage.open(src) as img:
            img = img.convert("RGB")
            img.save(dest, "JPEG", quality=95)
    else:
        shutil.copy2(src, dest)


def _next_photo_index(person_dir: Path) -> int:
    """Return the next sequential photo number (1-based)."""
    existing = sorted(person_dir.glob("*.jpg"))
    if not existing:
        return 1
    nums = []
    for p in existing:
        try:
            nums.append(int(p.stem))
        except ValueError:
            pass
    return (max(nums) + 1) if nums else 1


# ── CSV helpers ───────────────────────────────────────────────────────────────

_CSV_FIELDS = [
    "person_id", "fio", "display_name",
    "photo_dir", "created_at", "updated_at", "photo_count",
]


def _load_people() -> dict[str, dict]:
    """Return {person_id: row_dict}. Creates file if missing."""
    FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PEOPLE_CSV.exists():
        with open(PEOPLE_CSV, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_CSV_FIELDS).writeheader()
        return {}
    people: dict[str, dict] = {}
    try:
        with open(PEOPLE_CSV, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pid = row.get("person_id", "").strip()
                if pid:
                    people[pid] = row
    except Exception:
        pass
    return people


def _save_people(people: dict[str, dict]) -> None:
    FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PEOPLE_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        w.writeheader()
        for row in people.values():
            w.writerow(row)


# ── Manifest helpers ──────────────────────────────────────────────────────────

def _load_manifest() -> dict[str, Any]:
    FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MANIFEST_JSON.exists():
        return _empty_manifest()
    try:
        with open(MANIFEST_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure required keys exist
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("total_people", 0)
        data.setdefault("total_photos", 0)
        data.setdefault("last_updated_at", _now_iso())
        data.setdefault("photo_hashes", {})   # {person_id: [sha256, ...]}
        data.setdefault("history", [])
        return data
    except Exception:
        return _empty_manifest()


def _empty_manifest() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "total_people": 0,
        "total_photos": 0,
        "last_updated_at": _now_iso(),
        "photo_hashes": {},
        "history": [],
    }


def _save_manifest(manifest: dict[str, Any]) -> None:
    FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_JSON, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def _manifest_total_photos(manifest: dict[str, Any]) -> int:
    return sum(len(v) for v in manifest.get("photo_hashes", {}).values())


def _append_history(
    manifest: dict[str, Any],
    action: str,
    person_id: str,
    fio: str,
    files_added: list[str],
    files_skipped: list[str],
) -> None:
    manifest.setdefault("history", []).append({
        "timestamp": _now_iso(),
        "action": action,
        "person_id": person_id,
        "fio": fio,
        "files_added": files_added,
        "files_skipped": files_skipped,
    })


# ── Core logic (no GUI dependency) ───────────────────────────────────────────

def add_person_photos(
    fio: str,
    display_name: str,
    image_paths: list[Path],
) -> dict[str, Any]:
    """
    Add a person (new or existing) with the given image files.

    Returns a result dict:
        {
          "person_id": str,
          "is_new_person": bool,
          "files_added": [str, ...],
          "files_skipped": [str, ...],
          "errors": [str, ...],
        }
    """
    fio = fio.strip()
    display_name = display_name.strip() or fio
    if not fio:
        return {"person_id": "", "is_new_person": False,
                "files_added": [], "files_skipped": [],
                "errors": ["FIO cannot be empty."]}

    person_id = _slug(fio)
    person_dir = PHOTOS_DIR / person_id
    person_dir.mkdir(parents=True, exist_ok=True)

    people   = _load_people()
    manifest = _load_manifest()

    is_new_person = person_id not in people
    now = _now_iso()

    if is_new_person:
        people[person_id] = {
            "person_id":    person_id,
            "fio":          fio,
            "display_name": display_name,
            "photo_dir":    str(PHOTOS_DIR.relative_to(_PROJECT_ROOT) / person_id),
            "created_at":   now,
            "updated_at":   now,
            "photo_count":  "0",
        }

    # Existing hashes for this person
    known_hashes: list[str] = manifest.setdefault(
        "photo_hashes", {}
    ).setdefault(person_id, [])

    files_added:   list[str] = []
    files_skipped: list[str] = []
    errors:        list[str] = []

    next_idx = _next_photo_index(person_dir)

    for src in image_paths:
        src = Path(src)
        if not src.exists():
            errors.append(f"File not found: {src.name}")
            continue
        if not _is_valid_image_ext(src):
            errors.append(f"Unsupported extension: {src.name}")
            continue

        # Validate image with Pillow if available
        if _PILLOW_AVAILABLE:
            try:
                with _PILImage.open(src) as img:
                    img.verify()
            except Exception as exc:
                errors.append(f"Invalid image {src.name}: {exc}")
                continue

        # Duplicate hash check
        file_hash = _sha256(src)
        if file_hash in known_hashes:
            files_skipped.append(src.name)
            continue

        # Save
        dest = person_dir / f"{next_idx:02d}.jpg"
        try:
            _save_image(src, dest)
        except Exception as exc:
            errors.append(f"Failed to save {src.name}: {exc}")
            continue

        known_hashes.append(file_hash)
        files_added.append(dest.name)
        next_idx += 1

    # Update CSV row
    photo_count = len(list(person_dir.glob("*.jpg")))
    people[person_id]["photo_count"] = str(photo_count)
    people[person_id]["updated_at"]  = now
    if not is_new_person:
        # Preserve original display_name unless user explicitly changed it
        if display_name and display_name != fio:
            people[person_id]["display_name"] = display_name

    # Update manifest totals
    manifest["total_people"]     = len(people)
    manifest["total_photos"]     = _manifest_total_photos(manifest)
    manifest["last_updated_at"]  = now

    action = "add_person" if is_new_person else "add_photos"
    if files_added:
        _append_history(manifest, action, person_id, fio, files_added, files_skipped)
    elif files_skipped:
        _append_history(manifest, "skip_duplicate_photo",
                        person_id, fio, [], files_skipped)

    _save_people(people)
    _save_manifest(manifest)

    return {
        "person_id":    person_id,
        "is_new_person": is_new_person,
        "files_added":  files_added,
        "files_skipped": files_skipped,
        "errors":       errors,
    }


def get_all_people() -> list[dict]:
    """Return list of all person rows sorted by fio."""
    people = _load_people()
    return sorted(people.values(), key=lambda r: r.get("fio", "").lower())


def get_summary() -> dict[str, Any]:
    manifest = _load_manifest()
    return {
        "total_people": manifest.get("total_people", 0),
        "total_photos": manifest.get("total_photos", 0),
        "last_updated": manifest.get("last_updated_at", "—"),
        "history":      manifest.get("history", []),
    }


# ── Tkinter GUI ───────────────────────────────────────────────────────────────

class FaceDatasetApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Face Dataset Builder")
        self.resizable(True, True)
        self.minsize(820, 600)
        self._selected_files: list[Path] = []
        self._build_ui()
        self._refresh_people_table()
        self._refresh_summary()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Top: input form ──────────────────────────────────────────────────
        form = ttk.LabelFrame(self, text="Add / Update Person", padding=10)
        form.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="FIO *").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._fio_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._fio_var, width=35).grid(
            row=0, column=1, sticky="ew")

        ttk.Label(form, text="Display name").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        self._dname_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._dname_var, width=35).grid(
            row=1, column=1, sticky="ew", pady=(6, 0))

        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(btn_frame, text="📂 Select Images",
                   command=self._select_files).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="✅ Save / Add",
                   command=self._save).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="🗑 Clear form",
                   command=self._clear_form).pack(side="left")

        # Selected files label
        self._files_label_var = tk.StringVar(value="No files selected.")
        ttk.Label(form, textvariable=self._files_label_var,
                  foreground="#555").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # ── Middle: people table + log ────────────────────────────────────────
        mid = ttk.Frame(self)
        mid.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)
        mid.columnconfigure(0, weight=3)
        mid.columnconfigure(1, weight=2)
        mid.rowconfigure(0, weight=1)

        # People table
        tbl_frame = ttk.LabelFrame(mid, text="Known People", padding=6)
        tbl_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tbl_frame.rowconfigure(0, weight=1)
        tbl_frame.columnconfigure(0, weight=1)

        cols = ("person_id", "fio", "display_name", "photos", "updated_at")
        self._tree = ttk.Treeview(tbl_frame, columns=cols,
                                  show="headings", selectmode="browse")
        widths = {"person_id": 130, "fio": 150, "display_name": 110,
                  "photos": 55, "updated_at": 140}
        for c in cols:
            self._tree.heading(c, text=c.replace("_", " ").title())
            self._tree.column(c, width=widths.get(c, 100), anchor="w")
        vsb = ttk.Scrollbar(tbl_frame, orient="vertical",
                            command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<<TreeviewSelect>>", self._on_person_select)

        # Log / status panel
        log_frame = ttk.LabelFrame(mid, text="Log / Status", padding=6)
        log_frame.grid(row=0, column=1, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self._log = tk.Text(log_frame, state="disabled", wrap="word",
                            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
                            relief="flat")
        lsb = ttk.Scrollbar(log_frame, orient="vertical",
                             command=self._log.yview)
        self._log.configure(yscrollcommand=lsb.set)
        self._log.grid(row=0, column=0, sticky="nsew")
        lsb.grid(row=0, column=1, sticky="ns")

        # ── Bottom: summary bar ───────────────────────────────────────────────
        self._summary_var = tk.StringVar()
        ttk.Label(self, textvariable=self._summary_var,
                  relief="sunken", anchor="w", padding=(6, 2)).grid(
            row=2, column=0, sticky="ew", padx=10, pady=(4, 8))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _select_files(self):
        paths = filedialog.askopenfilenames(
            title="Select face images",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.webp"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            self._selected_files = [Path(p) for p in paths]
            self._files_label_var.set(
                f"{len(self._selected_files)} file(s) selected: "
                + ", ".join(p.name for p in self._selected_files[:4])
                + ("…" if len(self._selected_files) > 4 else "")
            )
        else:
            self._selected_files = []
            self._files_label_var.set("No files selected.")

    def _save(self):
        fio = self._fio_var.get().strip()
        dname = self._dname_var.get().strip()

        if not fio:
            messagebox.showwarning("Missing FIO", "Please enter a FIO.")
            return
        if not self._selected_files:
            messagebox.showwarning("No images", "Please select at least one image.")
            return

        result = add_person_photos(fio, dname, self._selected_files)

        pid    = result["person_id"]
        added  = result["files_added"]
        skip   = result["files_skipped"]
        errs   = result["errors"]
        is_new = result["is_new_person"]

        lines = [
            f"{'✨ New person' if is_new else '➕ Updated'}: {fio} ({pid})",
        ]
        if added:
            lines.append(f"  Added {len(added)} photo(s): {', '.join(added)}")
        if skip:
            lines.append(f"  Skipped {len(skip)} duplicate(s): {', '.join(skip)}")
        if errs:
            lines.append(f"  Errors ({len(errs)}): {'; '.join(errs)}")
        if not added and not errs:
            lines.append("  Nothing new to add.")

        self._log_write("\n".join(lines))
        self._refresh_people_table()
        self._refresh_summary()

        if added:
            self._clear_form()

    def _clear_form(self):
        self._fio_var.set("")
        self._dname_var.set("")
        self._selected_files = []
        self._files_label_var.set("No files selected.")

    def _on_person_select(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        item = self._tree.item(sel[0])
        pid = item["values"][0]
        people = _load_people()
        row = people.get(pid)
        if row:
            self._fio_var.set(row.get("fio", ""))
            self._dname_var.set(row.get("display_name", ""))

    # ── Refresh helpers ───────────────────────────────────────────────────────

    def _refresh_people_table(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for row in get_all_people():
            self._tree.insert("", "end", values=(
                row.get("person_id", ""),
                row.get("fio", ""),
                row.get("display_name", ""),
                row.get("photo_count", "0"),
                row.get("updated_at", ""),
            ))

    def _refresh_summary(self):
        s = get_summary()
        self._summary_var.set(
            f"  People: {s['total_people']}   "
            f"Photos: {s['total_photos']}   "
            f"Last updated: {s['last_updated']}   "
            f"Pillow: {'✓' if _PILLOW_AVAILABLE else '✗ (install Pillow for image validation)'}"
        )

    def _log_write(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", f"\n[{_now_iso()}]\n{text}\n")
        self._log.see("end")
        self._log.configure(state="disabled")


# ── Dry-run / self-test (no real images needed) ───────────────────────────────

def _dry_run_test():
    """
    Smoke-test the core logic without a GUI or real image files.
    Creates fake 1×1 JPEG bytes and exercises the full pipeline.
    """
    import tempfile, io

    print("=" * 60)
    print("face_dataset_builder.py — dry-run self-test")
    print("=" * 60)

    # Build a minimal valid JPEG in memory (1×1 white pixel)
    def _make_fake_jpeg(tmp_dir: Path, name: str) -> Path:
        p = tmp_dir / name
        if _PILLOW_AVAILABLE:
            img = _PILImage.new("RGB", (1, 1), color=(255, 255, 255))
            img.save(p, "JPEG")
        else:
            # Minimal valid JPEG header (1×1 white)
            _MINIMAL_JPEG = bytes([
                0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46,0x00,0x01,
                0x01,0x00,0x00,0x01,0x00,0x01,0x00,0x00,0xFF,0xDB,0x00,0x43,
                0x00,0x08,0x06,0x06,0x07,0x06,0x05,0x08,0x07,0x07,0x07,0x09,
                0x09,0x08,0x0A,0x0C,0x14,0x0D,0x0C,0x0B,0x0B,0x0C,0x19,0x12,
                0x13,0x0F,0x14,0x1D,0x1A,0x1F,0x1E,0x1D,0x1A,0x1C,0x1C,0x20,
                0x24,0x2E,0x27,0x20,0x22,0x2C,0x23,0x1C,0x1C,0x28,0x37,0x29,
                0x2C,0x30,0x31,0x34,0x34,0x34,0x1F,0x27,0x39,0x3D,0x38,0x32,
                0x3C,0x2E,0x33,0x34,0x32,0xFF,0xC0,0x00,0x0B,0x08,0x00,0x01,
                0x00,0x01,0x01,0x01,0x11,0x00,0xFF,0xC4,0x00,0x1F,0x00,0x00,
                0x01,0x05,0x01,0x01,0x01,0x01,0x01,0x01,0x00,0x00,0x00,0x00,
                0x00,0x00,0x00,0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,
                0x09,0x0A,0x0B,0xFF,0xC4,0x00,0xB5,0x10,0x00,0x02,0x01,0x03,
                0x03,0x02,0x04,0x03,0x05,0x05,0x04,0x04,0x00,0x00,0x01,0x7D,
                0x01,0x02,0x03,0x00,0x04,0x11,0x05,0x12,0x21,0x31,0x41,0x06,
                0x13,0x51,0x61,0x07,0x22,0x71,0x14,0x32,0x81,0x91,0xA1,0x08,
                0x23,0x42,0xB1,0xC1,0x15,0x52,0xD1,0xF0,0x24,0x33,0x62,0x72,
                0x82,0x09,0x0A,0x16,0x17,0x18,0x19,0x1A,0x25,0x26,0x27,0x28,
                0x29,0x2A,0x34,0x35,0x36,0x37,0x38,0x39,0x3A,0x43,0x44,0x45,
                0x46,0x47,0x48,0x49,0x4A,0x53,0x54,0x55,0x56,0x57,0x58,0x59,
                0x5A,0x63,0x64,0x65,0x66,0x67,0x68,0x69,0x6A,0x73,0x74,0x75,
                0x76,0x77,0x78,0x79,0x7A,0x83,0x84,0x85,0x86,0x87,0x88,0x89,
                0x8A,0x92,0x93,0x94,0x95,0x96,0x97,0x98,0x99,0x9A,0xA2,0xA3,
                0xA4,0xA5,0xA6,0xA7,0xA8,0xA9,0xAA,0xB2,0xB3,0xB4,0xB5,0xB6,
                0xB7,0xB8,0xB9,0xBA,0xC2,0xC3,0xC4,0xC5,0xC6,0xC7,0xC8,0xC9,
                0xCA,0xD2,0xD3,0xD4,0xD5,0xD6,0xD7,0xD8,0xD9,0xDA,0xE1,0xE2,
                0xE3,0xE4,0xE5,0xE6,0xE7,0xE8,0xE9,0xEA,0xF1,0xF2,0xF3,0xF4,
                0xF5,0xF6,0xF7,0xF8,0xF9,0xFA,0xFF,0xDA,0x00,0x08,0x01,0x01,
                0x00,0x00,0x3F,0x00,0xFB,0xD2,0x8A,0x28,0x03,0xFF,0xD9,
            ])
            p.write_bytes(_MINIMAL_JPEG)
        return p

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        img1 = _make_fake_jpeg(tmp_dir, "photo_a.jpg")
        img2 = _make_fake_jpeg(tmp_dir, "photo_b.jpg")  # same content → duplicate

        # Test 1: add new person
        r1 = add_person_photos("Test Person", "Tester", [img1])
        assert r1["is_new_person"], "Should be new person"
        assert len(r1["files_added"]) == 1, f"Expected 1 added, got {r1['files_added']}"
        assert len(r1["files_skipped"]) == 0
        print(f"  [PASS] New person created: {r1['person_id']}")

        # Test 2: add same image again → duplicate
        r2 = add_person_photos("Test Person", "Tester", [img1])
        assert not r2["is_new_person"], "Should be existing person"
        assert len(r2["files_added"]) == 0
        assert len(r2["files_skipped"]) == 1
        print(f"  [PASS] Duplicate photo skipped: {r2['files_skipped']}")

        # Test 3: add different image to same person
        r3 = add_person_photos("Test Person", "Tester", [img2])
        # img2 has same bytes as img1 → still a duplicate
        assert len(r3["files_skipped"]) == 1
        print(f"  [PASS] Same-content image skipped (hash match): {r3['files_skipped']}")

        # Test 4: add second person
        img3 = _make_fake_jpeg(tmp_dir, "photo_c.jpg")
        # Make it different content
        img3.write_bytes(img3.read_bytes() + b"\x00")
        r4 = add_person_photos("Another Person", "Another", [img3])
        assert r4["is_new_person"]
        print(f"  [PASS] Second person created: {r4['person_id']}")

        # Test 5: verify CSV and manifest
        people = _load_people()
        assert "test_person" in people, "test_person missing from CSV"
        assert "another_person" in people, "another_person missing from CSV"
        manifest = _load_manifest()
        assert manifest["total_people"] == 2
        print(f"  [PASS] CSV has {len(people)} people, manifest total_people={manifest['total_people']}")
        print(f"  [PASS] History entries: {len(manifest['history'])}")

        # Test 6: slug generation
        assert _slug("Ali Valiyev") == "ali_valiyev"
        assert _slug("Dilshod  Karimov!") == "dilshod_karimov"
        assert _slug("  Spaces  ") == "spaces"
        print("  [PASS] Slug generation correct")

        # Cleanup test data
        test_pid = "test_person"
        another_pid = "another_person"
        for pid in [test_pid, another_pid]:
            pdir = PHOTOS_DIR / pid
            if pdir.exists():
                shutil.rmtree(pdir)
        people = _load_people()
        people.pop(test_pid, None)
        people.pop(another_pid, None)
        _save_people(people)
        manifest = _load_manifest()
        manifest["photo_hashes"].pop(test_pid, None)
        manifest["photo_hashes"].pop(another_pid, None)
        manifest["total_people"] = len(people)
        manifest["total_photos"] = _manifest_total_photos(manifest)
        _save_manifest(manifest)

    print()
    print("All dry-run tests passed.")
    print(f"Dataset root: {FACE_DATA_DIR}")
    print(f"people.csv:   {PEOPLE_CSV}")
    print(f"manifest.json:{MANIFEST_JSON}")
    print(f"Pillow:       {'available' if _PILLOW_AVAILABLE else 'NOT installed — install with: pip install Pillow'}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Ensure data dirs exist
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    _load_people()    # creates people.csv if missing
    _load_manifest()  # creates manifest.json if missing

    if "--test" in sys.argv:
        _dry_run_test()
        return

    try:
        app = FaceDatasetApp()
        app.mainloop()
    except tk.TclError as exc:
        print(f"[ERROR] Cannot start GUI: {exc}")
        print("Tip: on headless Linux, install: sudo apt install python3-tk")
        print("     or run with --test for CLI dry-run mode.")
        sys.exit(1)


if __name__ == "__main__":
    main()
