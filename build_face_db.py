"""
build_face_db.py — Build / rebuild the face embedding SQLite database.

Usage:
  python build_face_db.py                  # build missing embeddings
  python build_face_db.py --rebuild        # drop and rebuild all embeddings
  python build_face_db.py --person-id ali  # build only for one person
  python build_face_db.py --self-test      # run recognition self-test
  python build_face_db.py --rebuild --self-test

Reads:
  face_data/people.csv
  face_data/photos/<person_id>/*.jpg

Writes:
  face_data/faces.sqlite
"""
from __future__ import annotations

import argparse
import os
import sys


def _setup_env():
    # Don't touch ESP32 from this CLI.
    os.environ.setdefault("ESP32_SERIAL_ENABLED", "false")
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _print_report(report: dict) -> None:
    print()
    print("Build report")
    print("-" * 60)
    print(f"  people loaded      : {report.get('people', 0)}")
    print(f"  photos scanned     : {report.get('photos_scanned', 0)}")
    print(f"  embeddings created : {report.get('embeddings_created', 0)}")
    print(f"  skipped            : {report.get('skipped', 0)}")
    reasons = report.get("skip_reasons", {})
    if reasons:
        print("  skip reasons       :")
        for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"    - {k}: {v}")
    warnings = report.get("warnings", [])
    if warnings:
        print("  warnings           :")
        for w in warnings:
            print(f"    [warn] {w}")
    print("-" * 60)


def _print_self_test(report: dict) -> None:
    print()
    print("Self-test results")
    print("-" * 60)
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
                  f"got={(r['got'] or '?'):30s} "
                  f"sim={r['similarity']:.3f} "
                  f"reason={r['reason']}")
    total = report["passed"] + report["failed"]
    print(f"\n{report['passed']}/{total} photos correctly recognised.")
    print("-" * 60)


def main() -> int:
    _setup_env()

    parser = argparse.ArgumentParser(
        description="Build / rebuild face embedding database."
    )
    parser.add_argument("--rebuild", action="store_true",
                        help="drop existing embeddings and re-embed everything")
    parser.add_argument("--person-id", default=None,
                        help="only build for this person")
    parser.add_argument("--self-test", action="store_true",
                        help="run recognition self-test after build")
    args = parser.parse_args()

    # Lazy import so --help works even if InsightFace is missing.
    from face_recognition_db import (
        FaceDatabase, _insightface_available, FACE_DATA_DIR, DB_PATH,
    )

    print("=" * 60)
    print("Face database builder")
    print("=" * 60)
    print(f"  data_dir       : {FACE_DATA_DIR}")
    print(f"  db_path        : {DB_PATH}")
    print(f"  insightface ok : {_insightface_available()}")
    print(f"  rebuild        : {args.rebuild}")
    if args.person_id:
        print(f"  person_id      : {args.person_id}")
    print()

    if not _insightface_available():
        print("[ERROR] insightface / onnxruntime are not installed.")
        print("        pip install insightface onnxruntime")
        return 2

    # Construct DB. This will load the model and (if rebuild=False) build any
    # new embeddings already.
    db = FaceDatabase()
    if not db.people:
        print("[ERROR] No people found. Add face_data/people.csv first or use "
              "face_dataset_builder.py.")
        return 2

    if args.rebuild or args.person_id:
        report = db.build_from_photos(rebuild=args.rebuild,
                                      person_id=args.person_id)
        if "error" in report:
            print(f"[ERROR] {report['error']}")
            return 2
        _print_report(report)
        # Reload in-memory embeddings after a write
        from face_recognition_db import _connect_db
        conn = _connect_db(db.db_path)
        try:
            db._reload_embeddings(conn)
        finally:
            conn.close()
    else:
        # Even on incremental run, print a quick status
        print(f"[OK] db has people={len(db.people)} "
              f"embeddings={len(db._embeddings)} "
              f"recognizer={db.recognizer_type}")

    if args.self_test:
        report = db.self_test()
        _print_self_test(report)
        if report["failed"] > 0 and report["passed"] == 0:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
