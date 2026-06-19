"""
movement_commands.py — Anatomically correct Uzbek voice-command → servo movement parser.

ESP32 PROTOCOL (unchanged):
  HEAD:<angle>                          — head servo, absolute 0..180 (90 = center)
  ARMS:<rs,re,rw,ls,le,lw>             — arm offsets from neutral, each -90..90
    rs = right_shoulder   re = right_elbow   rw = right_wrist
    ls = left_shoulder    le = left_elbow    lw = left_wrist

ANATOMICAL RULES:
  "qo'l ko'tar"  → shoulder only.  Elbow and wrist stay at 0.
  "tirsak buk"   → elbow only.     Shoulder and wrist stay at 0.
  "bilak bur"    → wrist only.     Shoulder and elbow stay at 0.
  "ko'krak"      → shoulder + elbow compound (natural chest pose).
  "salom/silkit" → shoulder raises, then wrist oscillates (elbow stays 0).

CONFIG ENV VARS (all read at import time via os.getenv):
  ARM_RIGHT_SHOULDER_RAISE_OFFSET   default  55  (positive = arm up)
  ARM_LEFT_SHOULDER_RAISE_OFFSET    default  55
  ARM_RIGHT_SHOULDER_CHEST_OFFSET   default  30  (partial raise for chest pose)
  ARM_LEFT_SHOULDER_CHEST_OFFSET    default  30
  ARM_RIGHT_ELBOW_BEND_OFFSET       default  45  (positive = elbow bends forward)
  ARM_LEFT_ELBOW_BEND_OFFSET        default  45
  ARM_RIGHT_WRIST_WAVE_OFFSET       default  35  (wrist oscillation amplitude)
  ARM_LEFT_WRIST_WAVE_OFFSET        default  35
  ARM_RIGHT_WRIST_TURN_OFFSET       default  45  (wrist rotation for "bilak bur")
  ARM_LEFT_WRIST_TURN_OFFSET        default  45
  ARM_AUTO_RETURN_TO_NEUTRAL        default  true
"""
from __future__ import annotations

import os
import re
import sys
import threading
from typing import Any

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

NEUTRAL_ARMS: list[int] = [0, 0, 0, 0, 0, 0]
NEUTRAL_HEAD: int = 90
DEFAULT_POSITION: list[int] = [90, 90, 90, 90, 90, 90, 90]  # legacy compat

_OFFSET_MIN = -90
_OFFSET_MAX = 90
_WAIT_MIN = 0.05
_WAIT_MAX = 10.0
_WAIT_DEFAULT = 0.5


# ---------------------------------------------------------------------------
# Config — read once at import time, override via .env
# ---------------------------------------------------------------------------

def _cfg_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[MOVEMENT] {name}: invalid value {raw!r}, using default {default}")
        return default


def _cfg_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "ha"}


# Shoulder raise offsets (positive = arm lifts up)
_R_SHOULDER_RAISE = _cfg_int("ARM_RIGHT_SHOULDER_RAISE_OFFSET", 55)
_L_SHOULDER_RAISE = _cfg_int("ARM_LEFT_SHOULDER_RAISE_OFFSET", 55)

# Shoulder partial raise for chest pose
_R_SHOULDER_CHEST = _cfg_int("ARM_RIGHT_SHOULDER_CHEST_OFFSET", 30)
_L_SHOULDER_CHEST = _cfg_int("ARM_LEFT_SHOULDER_CHEST_OFFSET", 30)

# Elbow bend offsets (positive = elbow bends forward/inward anatomically)
_R_ELBOW_BEND = _cfg_int("ARM_RIGHT_ELBOW_BEND_OFFSET", 45)
_L_ELBOW_BEND = _cfg_int("ARM_LEFT_ELBOW_BEND_OFFSET", 45)

# Wrist wave amplitude (oscillation for silkit/salom)
_R_WRIST_WAVE = _cfg_int("ARM_RIGHT_WRIST_WAVE_OFFSET", 35)
_L_WRIST_WAVE = _cfg_int("ARM_LEFT_WRIST_WAVE_OFFSET", 35)

# Wrist turn offset (for "bilak bur")
_R_WRIST_TURN = _cfg_int("ARM_RIGHT_WRIST_TURN_OFFSET", 45)
_L_WRIST_TURN = _cfg_int("ARM_LEFT_WRIST_TURN_OFFSET", 45)

# Auto-return to neutral after each sequence
_AUTO_RETURN = _cfg_bool("ARM_AUTO_RETURN_TO_NEUTRAL", True)

# Default per-step wait when AI/local sequences don't specify one
_MOVEMENT_DEFAULT_STEP_WAIT = float(_cfg_int("MOVEMENT_DEFAULT_STEP_WAIT_MS", 500)) / 1000.0

# Maximum delay (seconds) the user can request via "<N> soniyadan keyin"
_MOVEMENT_DELAY_MAX = float(_cfg_int("MOVEMENT_DELAY_MAX_SECONDS", 30))


# ---------------------------------------------------------------------------
# Safety validation
# ---------------------------------------------------------------------------

def validate_head_angle(value: Any) -> int:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return NEUTRAL_HEAD
    return max(0, min(180, v))


def validate_arm_offset(value: Any) -> int:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(_OFFSET_MIN, min(_OFFSET_MAX, v))


def validate_arm_offsets(offsets: Any) -> list[int] | None:
    if not isinstance(offsets, (list, tuple)):
        print(f"[MOVEMENT] Invalid arm offsets type {type(offsets).__name__!r}, skipping.")
        return None
    if len(offsets) != 6:
        print(f"[MOVEMENT] Arm offsets length {len(offsets)} != 6, skipping.")
        return None
    return [validate_arm_offset(v) for v in offsets]


def validate_wait(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _WAIT_DEFAULT
    return max(_WAIT_MIN, min(_WAIT_MAX, v))


def validate_step(step: Any) -> dict | None:
    if not isinstance(step, dict):
        print(f"[MOVEMENT] Step is not a dict: {type(step).__name__!r}, skipping.")
        return None
    arms = validate_arm_offsets(step.get("arms", NEUTRAL_ARMS))
    if arms is None:
        return None
    head = validate_head_angle(step.get("head", NEUTRAL_HEAD))
    wait = validate_wait(step.get("wait", _WAIT_DEFAULT))
    return {"head": head, "arms": arms, "wait": wait}


def validate_movements(movements: Any) -> list[dict]:
    """Validate a list of movement steps. Appends neutral return if configured."""
    if not isinstance(movements, (list, tuple)):
        print("[MOVEMENT] movements is not a list, returning empty.")
        return []
    clean: list[dict] = []
    for i, step in enumerate(movements):
        validated = validate_step(step)
        if validated is None:
            print(f"[MOVEMENT] Step {i} invalid, skipping.")
            continue
        clean.append(validated)
    if not clean:
        return clean
    # Auto-return to neutral if configured
    if _AUTO_RETURN:
        last = clean[-1]
        if last["arms"] != NEUTRAL_ARMS or last["head"] != NEUTRAL_HEAD:
            clean.append(_neutral(0.5))
    return clean


# ---------------------------------------------------------------------------
# Step builders
# ---------------------------------------------------------------------------

def _step(head: int, arms: list[int], wait: float) -> dict:
    """Build one validated movement step."""
    return {
        "head": validate_head_angle(head),
        "arms": [validate_arm_offset(v) for v in arms],
        "wait": validate_wait(wait),
    }


def _neutral(wait: float = 0.5) -> dict:
    """Neutral/resting position step."""
    return {"head": NEUTRAL_HEAD, "arms": list(NEUTRAL_ARMS), "wait": validate_wait(wait)}


def _arms(rs=0, re=0, rw=0, ls=0, le=0, lw=0) -> list[int]:
    """Build arms offset list with named joints. Unspecified joints stay at 0."""
    return [
        validate_arm_offset(rs),
        validate_arm_offset(re),
        validate_arm_offset(rw),
        validate_arm_offset(ls),
        validate_arm_offset(le),
        validate_arm_offset(lw),
    ]


# ---------------------------------------------------------------------------
# SHOULDER sequences — elbow and wrist stay at 0
# ---------------------------------------------------------------------------

def _seq_raise_right() -> list[dict]:
    """Right shoulder raises. Elbow=0, wrist=0."""
    return [_step(90, _arms(rs=_R_SHOULDER_RAISE), 0.6)]


def _seq_raise_left() -> list[dict]:
    """Left shoulder raises. Elbow=0, wrist=0."""
    return [_step(90, _arms(ls=_L_SHOULDER_RAISE), 0.6)]


def _seq_raise_both() -> list[dict]:
    """Both shoulders raise. Elbows=0, wrists=0."""
    return [_step(90, _arms(rs=_R_SHOULDER_RAISE, ls=_L_SHOULDER_RAISE), 0.6)]


def _seq_lower_right() -> list[dict]:
    return [_neutral(0.4)]


def _seq_lower_left() -> list[dict]:
    return [_neutral(0.4)]


def _seq_lower_both() -> list[dict]:
    return [_neutral(0.4)]


# ---------------------------------------------------------------------------
# ELBOW sequences — shoulder and wrist stay at 0
# ---------------------------------------------------------------------------

def _seq_bend_elbow_right() -> list[dict]:
    """Right elbow bends. Shoulder=0, wrist=0."""
    return [_step(90, _arms(re=_R_ELBOW_BEND), 0.5)]


def _seq_bend_elbow_left() -> list[dict]:
    """Left elbow bends. Shoulder=0, wrist=0."""
    return [_step(90, _arms(le=_L_ELBOW_BEND), 0.5)]


def _seq_bend_elbow_both() -> list[dict]:
    """Both elbows bend. Shoulders=0, wrists=0."""
    return [_step(90, _arms(re=_R_ELBOW_BEND, le=_L_ELBOW_BEND), 0.5)]


def _seq_straighten_elbow_right() -> list[dict]:
    return [_neutral(0.4)]


def _seq_straighten_elbow_left() -> list[dict]:
    return [_neutral(0.4)]


def _seq_straighten_elbow_both() -> list[dict]:
    return [_neutral(0.4)]


# ---------------------------------------------------------------------------
# WRIST sequences — shoulder and elbow stay at 0
# ---------------------------------------------------------------------------

def _seq_wrist_turn_right() -> list[dict]:
    """Right wrist rotates. Shoulder=0, elbow=0."""
    return [
        _step(90, _arms(rw=-_R_WRIST_TURN), 0.25),
        _step(90, _arms(rw=_R_WRIST_TURN), 0.25),
        _step(90, _arms(rw=-_R_WRIST_TURN), 0.25),
        _step(90, _arms(rw=_R_WRIST_TURN), 0.25),
    ]


def _seq_wrist_turn_left() -> list[dict]:
    """Left wrist rotates. Shoulder=0, elbow=0."""
    return [
        _step(90, _arms(lw=-_L_WRIST_TURN), 0.25),
        _step(90, _arms(lw=_L_WRIST_TURN), 0.25),
        _step(90, _arms(lw=-_L_WRIST_TURN), 0.25),
        _step(90, _arms(lw=_L_WRIST_TURN), 0.25),
    ]


def _seq_wrist_turn_both() -> list[dict]:
    return [
        _step(90, _arms(rw=-_R_WRIST_TURN, lw=-_L_WRIST_TURN), 0.25),
        _step(90, _arms(rw=_R_WRIST_TURN, lw=_L_WRIST_TURN), 0.25),
        _step(90, _arms(rw=-_R_WRIST_TURN, lw=-_L_WRIST_TURN), 0.25),
        _step(90, _arms(rw=_R_WRIST_TURN, lw=_L_WRIST_TURN), 0.25),
    ]


def _seq_wrist_neutral() -> list[dict]:
    return [_neutral(0.4)]


# ---------------------------------------------------------------------------
# COMPOUND sequences
# ---------------------------------------------------------------------------

def _seq_chest_right() -> list[dict]:
    """Right arm to chest: shoulder partial raise + elbow bend. Wrist=0."""
    return [_step(90, _arms(rs=_R_SHOULDER_CHEST, re=_R_ELBOW_BEND), 0.6)]


def _seq_chest_left() -> list[dict]:
    """Left arm to chest: shoulder partial raise + elbow bend. Wrist=0."""
    return [_step(90, _arms(ls=_L_SHOULDER_CHEST, le=_L_ELBOW_BEND), 0.6)]


def _seq_chest_both() -> list[dict]:
    return [_step(90, _arms(
        rs=_R_SHOULDER_CHEST, re=_R_ELBOW_BEND,
        ls=_L_SHOULDER_CHEST, le=_L_ELBOW_BEND), 0.6)]


def _seq_wave_right() -> list[dict]:
    """
    Greeting wave: shoulder raises (elbow=0), then wrist oscillates.
    Elbow stays at 0 throughout — anatomically correct.
    """
    return [
        _step(90, _arms(rs=_R_SHOULDER_RAISE), 0.4),           # arm up, elbow=0
        _step(90, _arms(rs=_R_SHOULDER_RAISE, rw=-_R_WRIST_WAVE), 0.22),
        _step(90, _arms(rs=_R_SHOULDER_RAISE, rw=_R_WRIST_WAVE), 0.22),
        _step(90, _arms(rs=_R_SHOULDER_RAISE, rw=-_R_WRIST_WAVE), 0.22),
        _step(90, _arms(rs=_R_SHOULDER_RAISE, rw=_R_WRIST_WAVE), 0.22),
        _step(90, _arms(rs=_R_SHOULDER_RAISE), 0.2),            # wrist back to 0
    ]


def _seq_wave_left() -> list[dict]:
    return [
        _step(90, _arms(ls=_L_SHOULDER_RAISE), 0.4),
        _step(90, _arms(ls=_L_SHOULDER_RAISE, lw=-_L_WRIST_WAVE), 0.22),
        _step(90, _arms(ls=_L_SHOULDER_RAISE, lw=_L_WRIST_WAVE), 0.22),
        _step(90, _arms(ls=_L_SHOULDER_RAISE, lw=-_L_WRIST_WAVE), 0.22),
        _step(90, _arms(ls=_L_SHOULDER_RAISE, lw=_L_WRIST_WAVE), 0.22),
        _step(90, _arms(ls=_L_SHOULDER_RAISE), 0.2),
    ]


def _seq_wave_both() -> list[dict]:
    return [
        _step(90, _arms(rs=_R_SHOULDER_RAISE, ls=_L_SHOULDER_RAISE), 0.4),
        _step(90, _arms(rs=_R_SHOULDER_RAISE, rw=-_R_WRIST_WAVE,
                        ls=_L_SHOULDER_RAISE, lw=-_L_WRIST_WAVE), 0.22),
        _step(90, _arms(rs=_R_SHOULDER_RAISE, rw=_R_WRIST_WAVE,
                        ls=_L_SHOULDER_RAISE, lw=_L_WRIST_WAVE), 0.22),
        _step(90, _arms(rs=_R_SHOULDER_RAISE, rw=-_R_WRIST_WAVE,
                        ls=_L_SHOULDER_RAISE, lw=-_L_WRIST_WAVE), 0.22),
        _step(90, _arms(rs=_R_SHOULDER_RAISE, rw=_R_WRIST_WAVE,
                        ls=_L_SHOULDER_RAISE, lw=_L_WRIST_WAVE), 0.22),
        _step(90, _arms(rs=_R_SHOULDER_RAISE, ls=_L_SHOULDER_RAISE), 0.2),
    ]


def _seq_greeting_salute() -> list[dict]:
    """'Salom ber' — right arm wave."""
    return _seq_wave_right()


# ---------------------------------------------------------------------------
# HEAD sequences
# ---------------------------------------------------------------------------

def _seq_head_left() -> list[dict]:
    return [_step(140, NEUTRAL_ARMS, 0.5)]


def _seq_head_right() -> list[dict]:
    return [_step(40, NEUTRAL_ARMS, 0.5)]


def _seq_head_center() -> list[dict]:
    return [_neutral(0.4)]


# ---------------------------------------------------------------------------
# NEUTRAL
# ---------------------------------------------------------------------------

def _seq_neutral() -> list[dict]:
    return [_neutral(0.4)]


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

_APOSTROPHE_RE = re.compile(r"['\u2018\u2019\u201b\u02bb\u02bc`\u02b9\u0060]")


def _normalise(text: str) -> str:
    """
    Lowercase, unify apostrophes, collapse whitespace, expand Uzbek variants.
    Handles STT output variants: o'ng/oʻng/ong, qo'l/qoʻl/qol, etc.
    """
    t = text.lower().strip()
    # Unify all apostrophe-like characters to standard '
    t = _APOSTROPHE_RE.sub("'", t)
    # Unify Uzbek special letters that STT may output differently
    t = t.replace("\u02bb", "'").replace("\u02bc", "'")
    t = re.sub(r"\s+", " ", t)

    # Expand apostrophe-containing words to canonical no-apostrophe form
    # (so matching works regardless of whether STT includes apostrophe)
    replacements = [
        # o'ng variants → ong
        ("o'ng", "ong"),
        # qo'l variants → qol
        ("qo'l", "qol"),
        ("qo'lni", "qolni"),
        ("qo'ling", "qoling"),
        ("qo'lingni", "qolingni"),
        ("qo'lim", "qolim"),
        ("qo'limni", "qolimni"),
        ("qo'llaring", "ikki qol"),   # "qo'llaring" → "ikki qol" (both arms)
        ("qo'llaringni", "ikki qol"),
        # ko'tar variants → kotar
        ("ko'tar", "kotar"),
        ("ko'taring", "kotaring"),
        ("ko'tarib", "kotarib"),
        # ko'krak/ko'ks → kokrak/koks
        ("ko'krak", "kokrak"),
        ("ko'ks", "koks"),
        ("ko'ksimga", "koksimga"),
        ("ko'ksingga", "koksimga"),
        # to'g'ri variants → togri
        ("to'g'ri", "togri"),
        ("to'g'irla", "togirla"),
        ("to'g'rila", "togirla"),
        # bosh variants
        ("boshni", "bosh"),
        ("boshingni", "bosh"),
        # side/count synonyms
        ("ikkala", "ikki"),
        ("har ikki", "ikki"),
        ("har ikkala", "ikki"),
        ("ikkovi", "ikki"),
        ("baravar", "ikki"),
        ("birga", "ikki"),
        # yelka variants
        ("yelkang", "yelka"),
        ("yelkani", "yelka"),
        ("yelkangni", "yelka"),
        # tirsak variants
        ("tirsaging", "tirsak"),
        ("tirsakni", "tirsak"),
        ("tirsagingni", "tirsak"),
        # bilak variants
        ("bilagingni", "bilak"),
        ("bilagni", "bilak"),
        ("bilakni", "bilak"),
        ("bilag", "bilak"),
    ]
    for old, new in replacements:
        t = t.replace(old, new)
    return t


# ---------------------------------------------------------------------------
# Side detection
# ---------------------------------------------------------------------------

def _has_right(t: str) -> bool:
    return "ong" in t


def _has_left(t: str) -> bool:
    return "chap" in t


def _has_both(t: str) -> bool:
    return "ikki" in t or ("ong" in t and "chap" in t)


def _side_label(t: str) -> str:
    if _has_both(t):
        return "both"
    if _has_right(t):
        return "right"
    if _has_left(t):
        return "left"
    return "both"  # default: both arms when no side specified


def _side_speech(side: str) -> str:
    return {
        "right": "o'ng qo'limni",
        "left": "chap qo'limni",
        "both": "ikkala qo'limni",
    }[side]


def _any_kw(text: str, kw_set: set) -> bool:
    return any(k in text for k in kw_set)


# ---------------------------------------------------------------------------
# Keyword sets — each joint has its own detection set
# ---------------------------------------------------------------------------

# Shoulder / arm raise
_RAISE_KW = {"kotar", "kotaring", "kotarib", "yuqori", "baland", "tepaga", "ko'tar"}
_LOWER_KW = {"tushir", "pastga", "pasaytir", "past", "qaytar", "tushiring"}

# Elbow-specific keywords
_ELBOW_KW = {"tirsak", "tirsagim", "tirsaging"}
_ELBOW_BEND_KW = {"buk", "bukib", "bukish", "eg", "egib", "egish"}
_ELBOW_STRAIGHT_KW = {"togirla", "togri", "tekisla", "yoz", "yozib", "to'g'irla"}

# Wrist-specific keywords
_WRIST_KW = {"bilak", "bilagim", "bilaging"}
_WRIST_TURN_KW = {"aylantir", "aylan", "bur", "burish", "aylantirish"}
_WRIST_NEUTRAL_KW = {"neytral", "togri", "togirla"}

# Chest / ko'krak
_CHEST_KW = {"koks", "kokrak", "koksimga", "ko'ksingga"}

# Wave / silkit
_WAVE_KW = {"silkit", "tebrat", "qimirlat", "hilpirat", "siltiq", "silkitish"}

# Shoulder keyword (for explicit shoulder commands)
_SHOULDER_KW = {"yelka"}

# Head
_HEAD_KW = {"bosh"}
_HEAD_LEFT_KW = {"chapga", "chapdan"}
_HEAD_RIGHT_KW = {"onga", "ongga"}
_HEAD_CENTER_KW = {"togri", "oldinga", "markazga", "togriga", "qara"}

# Greeting
_GREET_KW = {"salom ber", "salomlash"}

# Neutral reset
_NEUTRAL_KW = {"neytral", "boshlangich", "dastlabki", "qayt", "qaytish", "default", "resting"}

_ARM_KW = {"qol", "qolni", "qoling", "qolingni", "qolim", "qolimni", "qolini", "qollarni", "qollaring", "qollaringni",
           "yelka", "tirsak", "bilak", "ongni", "chapni", "ongini", "chapini", "ikkalasi", "ikkalasini", "ikkala"}


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_movement_command(text: str) -> dict | None:
    """
    Parse an Uzbek voice command into a movement response.

    Returns:
        None  — not a direct movement command; caller should use AI.
        dict  — {"speech": str, "movements": [validated steps]}
    """
    t = _normalise(text)

    # ── Greeting wave ─────────────────────────────────────────────────────
    if _any_kw(t, _GREET_KW):
        _log(t, "both", "shoulder+wrist", "greeting_wave",
             _arms(rs=_R_SHOULDER_RAISE, rw=_R_WRIST_WAVE))
        return {
            "speech": "Albatta! Salom!",
            "movements": validate_movements(_seq_greeting_salute()),
        }

    # ── Neutral reset ─────────────────────────────────────────────────────
    if _any_kw(t, _NEUTRAL_KW):
        _log(t, "both", "all", "neutral", _arms())
        return {
            "speech": "Mayli, neytral holatga qaytdim.",
            "movements": validate_movements(_seq_neutral()),
        }

    # ── Head commands ─────────────────────────────────────────────────────
    if _any_kw(t, _HEAD_KW):
        if _any_kw(t, _HEAD_LEFT_KW):
            _log(t, "head", "head", "turn_left", _arms())
            return {
                "speech": "Boshimni chapga burdim.",
                "movements": validate_movements(_seq_head_left()),
            }
        if _any_kw(t, _HEAD_RIGHT_KW):
            _log(t, "head", "head", "turn_right", _arms())
            return {
                "speech": "Boshimni o'ngga burdim.",
                "movements": validate_movements(_seq_head_right()),
            }
        if _any_kw(t, _HEAD_CENTER_KW):
            _log(t, "head", "head", "center", _arms())
            return {
                "speech": "Boshimni to'g'riga qaratdim.",
                "movements": validate_movements(_seq_head_center()),
            }

    # ── Elbow commands (must check before general arm raise) ──────────────
    if _any_kw(t, _ELBOW_KW):
        side = _side_label(t)
        sp = _side_speech(side)
        if _any_kw(t, _ELBOW_BEND_KW):
            seqs = {
                "right": _seq_bend_elbow_right,
                "left": _seq_bend_elbow_left,
                "both": _seq_bend_elbow_both,
            }
            _log(t, side, "elbow", "bend",
                 _arms(re=_R_ELBOW_BEND) if side != "left" else _arms(le=_L_ELBOW_BEND))
            return {
                "speech": f"Mayli, {sp} tirsagidan bukdim.",
                "movements": validate_movements(seqs[side]()),
            }
        if _any_kw(t, _ELBOW_STRAIGHT_KW):
            seqs = {
                "right": _seq_straighten_elbow_right,
                "left": _seq_straighten_elbow_left,
                "both": _seq_straighten_elbow_both,
            }
            _log(t, side, "elbow", "straighten", _arms())
            return {
                "speech": f"Mayli, {sp} tirsagini to'g'riladim.",
                "movements": validate_movements(seqs[side]()),
            }

    # ── Wrist commands ────────────────────────────────────────────────────
    if _any_kw(t, _WRIST_KW):
        side = _side_label(t)
        sp = _side_speech(side)
        if _any_kw(t, _WRIST_TURN_KW):
            seqs = {
                "right": _seq_wrist_turn_right,
                "left": _seq_wrist_turn_left,
                "both": _seq_wrist_turn_both,
            }
            _log(t, side, "wrist", "turn",
                 _arms(rw=_R_WRIST_TURN) if side != "left" else _arms(lw=_L_WRIST_TURN))
            return {
                "speech": f"Mayli, {sp} bilagini aylantiryapman.",
                "movements": validate_movements(seqs[side]()),
            }
        if _any_kw(t, _WRIST_NEUTRAL_KW):
            _log(t, side, "wrist", "neutral", _arms())
            return {
                "speech": f"Mayli, {sp} bilagini neytral qildim.",
                "movements": validate_movements(_seq_wrist_neutral()),
            }

    # ── General arm commands — require at least one arm keyword ───────────
    if not _any_kw(t, _ARM_KW):
        return None

    side = _side_label(t)
    sp = _side_speech(side)

    # Raise (shoulder only — elbow and wrist stay at 0)
    if _any_kw(t, _RAISE_KW):
        seqs = {
            "right": _seq_raise_right,
            "left": _seq_raise_left,
            "both": _seq_raise_both,
        }
        final_arms = (
            _arms(rs=_R_SHOULDER_RAISE) if side == "right" else
            _arms(ls=_L_SHOULDER_RAISE) if side == "left" else
            _arms(rs=_R_SHOULDER_RAISE, ls=_L_SHOULDER_RAISE)
        )
        _log(t, side, "shoulder", "raise", final_arms)
        return {
            "speech": f"Albatta, {sp} ko'tardim.",
            "movements": validate_movements(seqs[side]()),
        }

    # Lower
    if _any_kw(t, _LOWER_KW):
        seqs = {
            "right": _seq_lower_right,
            "left": _seq_lower_left,
            "both": _seq_lower_both,
        }
        _log(t, side, "shoulder", "lower", _arms())
        return {
            "speech": f"Mayli, {sp} tushirdim.",
            "movements": validate_movements(seqs[side]()),
        }

    # Chest (shoulder + elbow compound)
    if _any_kw(t, _CHEST_KW):
        seqs = {
            "right": _seq_chest_right,
            "left": _seq_chest_left,
            "both": _seq_chest_both,
        }
        final_arms = (
            _arms(rs=_R_SHOULDER_CHEST, re=_R_ELBOW_BEND) if side == "right" else
            _arms(ls=_L_SHOULDER_CHEST, le=_L_ELBOW_BEND) if side == "left" else
            _arms(rs=_R_SHOULDER_CHEST, re=_R_ELBOW_BEND,
                  ls=_L_SHOULDER_CHEST, le=_L_ELBOW_BEND)
        )
        _log(t, side, "shoulder+elbow", "chest", final_arms)
        return {
            "speech": f"Mayli, {sp} ko'ksimga qo'ydim.",
            "movements": validate_movements(seqs[side]()),
        }

    # Wave / silkit (shoulder raises, wrist oscillates, elbow=0)
    if _any_kw(t, _WAVE_KW):
        seqs = {
            "right": _seq_wave_right,
            "left": _seq_wave_left,
            "both": _seq_wave_both,
        }
        _log(t, side, "shoulder+wrist", "wave",
             _arms(rs=_R_SHOULDER_RAISE, rw=_R_WRIST_WAVE))
        return {
            "speech": f"Mayli, {sp} silkitdim.",
            "movements": validate_movements(seqs[side]()),
        }

    # Shoulder explicit
    if _any_kw(t, _SHOULDER_KW):
        if _any_kw(t, _RAISE_KW):
            seqs = {
                "right": _seq_raise_right,
                "left": _seq_raise_left,
                "both": _seq_raise_both,
            }
            _log(t, side, "shoulder", "raise",
                 _arms(rs=_R_SHOULDER_RAISE) if side != "left" else _arms(ls=_L_SHOULDER_RAISE))
            return {
                "speech": f"Albatta, {sp} yelkasini ko'tardim.",
                "movements": validate_movements(seqs[side]()),
            }
        if _any_kw(t, _LOWER_KW):
            _log(t, side, "shoulder", "lower", _arms())
            return {
                "speech": f"Mayli, {sp} yelkasini tushirdim.",
                "movements": validate_movements(_seq_neutral()),
            }

    return None  # arm keyword present but no recognised action → let AI handle


# ---------------------------------------------------------------------------
# Movement intent detection
# ---------------------------------------------------------------------------

# Words that strongly suggest the user is requesting body movement.
_INTENT_BODY = {
    "bosh", "boshing", "boshingni", "boshim", "boshimni", "kallang", "kallangni",
    "qol", "qolni", "qoling", "qolingni", "qolim", "qolimni",
    "qollar", "qollaring", "qollaringni",
    "yelka", "yelkang", "yelkangni", "yelkani",
    "tirsak", "tirsaging", "tirsagingni", "tirsakni",
    "bilak", "bilaging", "bilagingni", "bilakni", "bilaklar",
}
_INTENT_ACTION = {
    "kotar", "kotaring", "kotarib",
    "tushir", "tushiring", "tushirib", "pasaytir",
    "buk", "bukib", "bukish", "eg", "egib", "egish",
    "togirla", "togri", "tekisla", "yoz", "yozib",
    "aylantir", "aylan", "bur", "burish",
    "qimirlat", "silkit", "silkitish", "tebrat", "hilpirat",
    "qara", "qarat", "qaytar", "qaytib",
    "neytral", "salom", "salomlash",
    "markazga", "oldinga",
}


def is_movement_intent(text: str) -> bool:
    """
    Return True if the text clearly requests a robot body movement.
    Uses normalised tokens, so it tolerates STT apostrophe variants.
    """
    if not text or not isinstance(text, str):
        return False
    t = _normalise(text)
    has_body   = _any_kw(t, _INTENT_BODY)
    has_action = _any_kw(t, _INTENT_ACTION)
    # "salom ber" alone (no body word) is an action request → still movement
    salute_only = "salom ber" in t or "salomlash" in t
    return (has_body and has_action) or salute_only




# ---------------------------------------------------------------------------
# Compound / multi-step parser
# ---------------------------------------------------------------------------

# Split connectors. Order matters: longer phrases first.
# We split on ", " and these connector words (with surrounding spaces).
_CONNECTORS = [
    "avval", "keyin", "so'ng", "song", "keyinroq",
    "va", "bilan", "hamda",
]

# Pattern: "<N> soniyadan keyin" / "<N> sekunddan keyin" / "<N> sek keyin"
_DELAY_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:soniya|sekund|sek)\w*\s*keyin",
    re.IGNORECASE,
)


def _extract_delay_seconds(clause: str) -> tuple[float, str]:
    """
    Extract a leading or trailing 'N soniyadan keyin' delay.
    Returns (delay_seconds, clause_without_delay).
    """
    match = _DELAY_RE.search(clause)
    if not match:
        return 0.0, clause
    raw = match.group(1).replace(",", ".")
    try:
        delay = float(raw)
    except ValueError:
        delay = 0.0
    delay = max(0.0, min(_MOVEMENT_DELAY_MAX, delay))
    cleaned = (clause[:match.start()] + " " + clause[match.end():]).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return delay, cleaned


def _split_into_clauses(normalised: str) -> list[str]:
    """
    Split a normalised text into ordered clauses.
    Splits on commas and connector words.

    Delay phrases like "3 soniyadan keyin" are protected from splitting
    on the connector word "keyin" by being stashed first.
    """
    text = normalised

    # Stash delay phrases so the connector word "keyin" inside them isn't split
    stashed: list[str] = []

    def _stash(match: re.Match) -> str:
        stashed.append(match.group(0))
        return f" __DELAY_{len(stashed) - 1}__ "

    text = _DELAY_RE.sub(_stash, text)

    # Replace connectors with a sentinel
    for word in _CONNECTORS:
        text = re.sub(rf"\b{re.escape(word)}\b", "|", text)
    text = text.replace(",", "|")

    parts = [p.strip() for p in text.split("|") if p.strip()]

    # Restore stashed delay phrases
    if stashed:
        restored = []
        for p in parts:
            for idx, original in enumerate(stashed):
                p = p.replace(f"__DELAY_{idx}__", original)
            p = re.sub(r"\s+", " ", p).strip()
            if p:
                restored.append(p)
        parts = restored

    return parts


# Body words used for cross-clause context propagation
_CONTEXT_BODY_TOKENS = ("bosh", "tirsak", "bilak", "yelka", "qol")


def _parse_clause_local(clause: str) -> dict | None:
    """
    Parse one clause via the existing single-action parser.
    Returns a movement dict or None.
    """
    return parse_movement_command(clause)


# Movement-delay maximum is defined in the config section above
# (kept here as a comment for clarity).


def parse_movement_sequence(text: str) -> dict | None:
    """
    Parse a multi-step / compound Uzbek movement command.

    Examples:
      "o'ng qo'lingni ko'tar"                          → 1 step
      "chap qo'lingni 3 soniyadan keyin ko'tar"        → wait 3s, then raise
      "o'ng qo'lingni ko'tarib tirsagingni buk"        → 2 steps (raise + bend)
      "boshingni chapga, o'ngga bur"                    → head left, then right
      "avval o'ng qo'lingni ko'tar, keyin chap tushir"  → 2 ordered steps

    Returns:
      None  — could not parse (caller may fall back to AI planner)
      dict  — {"speech": str, "movements": [steps], "source": "local"}
    """
    if not text:
        return None
    t = _normalise(text)

    clauses = _split_into_clauses(t)
    if not clauses:
        return None

    all_steps: list[dict] = []
    speech_parts: list[str] = []
    matched_any = False
    last_body_context: str | None = None  # e.g. "bosh", "tirsak", "qol"

    for clause in clauses:
        delay, cleaned = _extract_delay_seconds(clause)
        if not cleaned:
            # Pure delay clause (e.g. just "3 soniyadan keyin"): skip — the
            # delay applies to the next clause that follows naturally.
            if delay > 0 and all_steps:
                # Insert wait before the previous step's end
                all_steps.append(_neutral(min(delay, _MOVEMENT_DELAY_MAX)))
            continue

        # Carry body context from the previous clause if this clause has none
        # (e.g. "boshingni chapga, o'ngga bur" → second clause needs "bosh").
        clause_to_parse = cleaned
        has_body_here = any(tok in cleaned for tok in _CONTEXT_BODY_TOKENS)
        if not has_body_here and last_body_context:
            clause_to_parse = f"{last_body_context} {cleaned}"
        else:
            for tok in _CONTEXT_BODY_TOKENS:
                if tok in cleaned:
                    last_body_context = tok
                    break

        result = _parse_clause_local(clause_to_parse)
        if result is None:
            # Unknown clause — bail out so AI planner can handle the whole text
            return None

        if delay > 0:
            # Insert a wait step (neutral hold) before this clause's steps
            all_steps.append(_neutral(min(delay, _MOVEMENT_DELAY_MAX)))

        all_steps.extend(result.get("movements", []))
        speech_parts.append(result.get("speech", ""))
        matched_any = True

    if not matched_any or not all_steps:
        return None

    # Re-validate the merged sequence (ensures auto-return-to-neutral applied
    # only at the very end, not after each clause).
    # First strip any auto-appended neutral steps that would be mid-sequence.
    merged = [s for i, s in enumerate(all_steps)
              if not (s["arms"] == NEUTRAL_ARMS and s["head"] == NEUTRAL_HEAD
                      and i < len(all_steps) - 1
                      and s["wait"] == 0.5)]
    if not merged:
        merged = all_steps

    final = validate_movements(merged)

    speech = speech_parts[0] if len(speech_parts) == 1 else "Mayli, bajaryapman."

    print(f"[MOVEMENT] sequence parsed clauses={len(clauses)} "
          f"steps={len(final)} source=local")
    return {
        "speech": speech,
        "movements": final,
        "source": "local",
    }


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log(normalised: str, side: str, joint: str, action: str, arms: list[int]) -> None:
    print(
        f"[MOVEMENT] text={normalised!r} | side={side} | joint={joint} "
        f"| action={action} | arms={arms}"
    )


# ---------------------------------------------------------------------------
# AI movement planner (structured-JSON fallback)
# ---------------------------------------------------------------------------

# When the local parser fails, we ask the AI to return a strict JSON plan
# using only allowed action/target tokens. We then map those tokens to the
# safe local sequences above. The AI never outputs servo offsets directly.

_AI_PLANNER_PROMPT = """You are the movement planner for a physical humanoid robot representing Sohibqiron Amir Temur.
The robot has: head, right_arm, left_arm, right_shoulder, left_shoulder,
right_elbow, left_elbow, right_wrist, left_wrist.

The user just gave a movement instruction in Uzbek.

Respond with ONLY a single JSON object, no other text, no markdown, no code fence.

Schema:
{
  "is_movement": true,
  "speech": "<short Uzbek speech, e.g. Mayli, bajaryapman.>",
  "commands": [
    {"action": "<action>", "target": "<target>"},
    {"wait": <seconds>}
  ]
}

Allowed actions: raise, lower, bend, straighten, rotate, wave, turn_left,
turn_right, center, neutral, salute, chest.

Allowed targets: head, right_arm, left_arm, both_arms,
right_shoulder, left_shoulder, both_shoulders,
right_elbow, left_elbow, both_elbows,
right_wrist, left_wrist, both_wrists.

Special step: {"wait": <number>} pauses for N seconds (max 30).

Rules:
- Use only the actions and targets listed above.
- Do NOT output servo angles or numeric offsets.
- Keep the plan short (max 6 commands).
- If the user's request is not a movement, respond with:
  {"is_movement": false, "speech": "Bu harakat buyrug'i emas.", "commands": []}
- Speech must be short Uzbek (under 10 words).

Examples:

User: "o'ng qo'lingni ko'tar"
Response: {"is_movement": true, "speech": "Mayli, ko'tarayapman.", "commands": [{"action": "raise", "target": "right_arm"}]}

User: "chap qo'lingni 3 soniyadan keyin ko'tar"
Response: {"is_movement": true, "speech": "Mayli, hozir.", "commands": [{"wait": 3}, {"action": "raise", "target": "left_arm"}]}

User: "o'ng qo'lingni ko'tarib tirsagingni buk"
Response: {"is_movement": true, "speech": "Tushunarli.", "commands": [{"action": "raise", "target": "right_arm"}, {"action": "bend", "target": "right_elbow"}]}

User: "boshingni chapga, o'ngga bur"
Response: {"is_movement": true, "speech": "Mayli.", "commands": [{"action": "turn_left", "target": "head"}, {"action": "turn_right", "target": "head"}, {"action": "center", "target": "head"}]}
"""


_ACTION_TARGET_TO_SEQ: dict[tuple[str, str], "callable[[], list[dict]]"] = {
    # raise
    ("raise", "right_arm"):       _seq_raise_right,
    ("raise", "left_arm"):        _seq_raise_left,
    ("raise", "both_arms"):       _seq_raise_both,
    ("raise", "right_shoulder"):  _seq_raise_right,
    ("raise", "left_shoulder"):   _seq_raise_left,
    ("raise", "both_shoulders"):  _seq_raise_both,
    # lower
    ("lower", "right_arm"):       _seq_lower_right,
    ("lower", "left_arm"):        _seq_lower_left,
    ("lower", "both_arms"):       _seq_lower_both,
    ("lower", "right_shoulder"):  _seq_lower_right,
    ("lower", "left_shoulder"):   _seq_lower_left,
    ("lower", "both_shoulders"):  _seq_lower_both,
    # elbow bend / straighten
    ("bend", "right_elbow"):      _seq_bend_elbow_right,
    ("bend", "left_elbow"):       _seq_bend_elbow_left,
    ("bend", "both_elbows"):      _seq_bend_elbow_both,
    ("straighten", "right_elbow"): _seq_straighten_elbow_right,
    ("straighten", "left_elbow"):  _seq_straighten_elbow_left,
    ("straighten", "both_elbows"): _seq_straighten_elbow_both,
    # wrist rotate / wave
    ("rotate", "right_wrist"):    _seq_wrist_turn_right,
    ("rotate", "left_wrist"):     _seq_wrist_turn_left,
    ("rotate", "both_wrists"):    _seq_wrist_turn_both,
    ("wave", "right_arm"):        _seq_wave_right,
    ("wave", "left_arm"):         _seq_wave_left,
    ("wave", "both_arms"):        _seq_wave_both,
    ("wave", "right_wrist"):      _seq_wave_right,
    ("wave", "left_wrist"):       _seq_wave_left,
    ("wave", "both_wrists"):      _seq_wave_both,
    # head
    ("turn_left",  "head"):       _seq_head_left,
    ("turn_right", "head"):       _seq_head_right,
    ("center",     "head"):       _seq_head_center,
    # neutral / salute / chest
    ("neutral", "head"):          _seq_neutral,
    ("neutral", "both_arms"):     _seq_neutral,
    ("neutral", "right_arm"):     _seq_neutral,
    ("neutral", "left_arm"):      _seq_neutral,
    ("salute",  "right_arm"):     _seq_greeting_salute,
    ("salute",  "head"):          _seq_greeting_salute,
    ("chest",   "right_arm"):     _seq_chest_right,
    ("chest",   "left_arm"):      _seq_chest_left,
    ("chest",   "both_arms"):     _seq_chest_both,
}


def _ai_command_to_steps(cmd: dict) -> list[dict]:
    """Convert one AI command dict to local movement steps."""
    if not isinstance(cmd, dict):
        return []
    if "wait" in cmd:
        try:
            delay = float(cmd["wait"])
        except (TypeError, ValueError):
            return []
        delay = max(0.0, min(_MOVEMENT_DELAY_MAX, delay))
        if delay <= 0:
            return []
        return [_neutral(delay)]
    action = str(cmd.get("action", "")).strip().lower()
    target = str(cmd.get("target", "")).strip().lower()
    seq_fn = _ACTION_TARGET_TO_SEQ.get((action, target))
    if seq_fn is None:
        print(f"[MOVEMENT] AI command rejected: action={action!r} target={target!r}")
        return []
    return seq_fn()


def parse_ai_movement_plan(plan_json: str) -> dict | None:
    """
    Parse and validate an AI-generated JSON movement plan.

    Returns the same shape as parse_movement_sequence(), or None if invalid.
    """
    import json

    if not plan_json or not isinstance(plan_json, str):
        return None

    # Strip code fences if AI ignored instructions
    text = plan_json.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"[MOVEMENT] AI plan JSON parse error: {exc}")
        return None

    if not isinstance(data, dict):
        print("[MOVEMENT] AI plan is not an object.")
        return None

    if not data.get("is_movement", False):
        print("[MOVEMENT] AI plan: is_movement=false.")
        return None

    raw_commands = data.get("commands", [])
    if not isinstance(raw_commands, list) or not raw_commands:
        print("[MOVEMENT] AI plan has no commands.")
        return None

    if len(raw_commands) > 8:
        print(f"[MOVEMENT] AI plan too long ({len(raw_commands)}), truncating to 8.")
        raw_commands = raw_commands[:8]

    all_steps: list[dict] = []
    for cmd in raw_commands:
        steps = _ai_command_to_steps(cmd)
        all_steps.extend(steps)

    if not all_steps:
        print("[MOVEMENT] AI plan produced no valid steps.")
        return None

    final = validate_movements(all_steps)
    speech = str(data.get("speech", "")).strip() or "Mayli, bajaryapman."

    print(f"[MOVEMENT] AI plan accepted commands={len(raw_commands)} "
          f"steps={len(final)} source=ai")
    return {
        "speech": speech,
        "movements": final,
        "source": "ai",
    }


def get_ai_planner_prompt() -> str:
    """Return the system prompt for AI movement planning."""
    return _AI_PLANNER_PROMPT


def generate_gestures_from_speech(speech_text: str) -> list[dict]:
    """
    Analyzes the speech_text and returns a list of movement steps (dict).
    If no keywords match, returns an empty list.
    """
    if not speech_text or not isinstance(speech_text, str):
        return []
    
    t = speech_text.lower()
    
    # 1. Greetings (Salomlashish)
    if any(kw in t for kw in ["salom", "assalom", "sog'liq", "omon", "hush kelibsiz"]):
        return validate_movements(_seq_wave_right())
        
    # 2. Heart/Me/Chest (Yurak/Men/Ko'ks)
    if any(kw in t for kw in ["men", "yurak", "ko'ks", "ko'krak", "qalb", "mening", "nomim"]):
        return validate_movements(_seq_chest_left())
        
    # 3. Strength/Justice/Sword/Kingdom (Kuch/Adolat/Qilich/Saltanat)
    if any(kw in t for kw in ["kuch", "adolat", "qilich", "saltanat", "davlat", "hokimiyat", "g'alaba", "jang", "askar", "zafar"]):
        return validate_movements(_seq_raise_right())
        
    # 4. Council/Decrees/Wills (Kengash/Tadbir/Tuzuklar/Vasiyat)
    if any(kw in t for kw in ["kengash", "tadbir", "maslahat", "tuzuk", "tuzuklar", "vasiyat", "kitob", "yozma"]):
        return validate_movements(_seq_chest_both())
        
    # 5. Head/Thought/Reason (Bosh/Fikr/Aql)
    if any(kw in t for kw in ["bosh", "boshim", "fikr", "o'y", "teran", "aqlim", "aql"]):
        return validate_movements([
            _step(110, NEUTRAL_ARMS, 0.4),
            _step(70, NEUTRAL_ARMS, 0.4),
            _neutral(0.4)
        ])
        
    # 6. Left side
    if "chap" in t:
        return validate_movements(_seq_raise_left())
        
    # 7. Right side
    if "o'ng" in t:
        return validate_movements(_seq_raise_right())
        
    # 8. Both sides
    if any(kw in t for kw in ["ikkala", "ikki"]):
        return validate_movements(_seq_raise_both())
        
    return []


_robot_busy_lock = threading.Lock()
_is_robot_busy = False

def set_robot_busy(busy: bool):
    global _is_robot_busy
    with _robot_busy_lock:
        _is_robot_busy = busy

def is_robot_busy() -> bool:
    global _is_robot_busy
    with _robot_busy_lock:
        return _is_robot_busy


def execute_movement_steps(steps: list[dict], controller) -> None:
    """
    Execute a validated movement sequence on the ESP32 controller.

    Args:
        steps: list of validated step dicts from validate_movements()
        controller: Esp32SerialController instance (or None for dry-run)
    """
    set_robot_busy(True)
    try:
        import time as _t
        for step in steps:
            head = step.get("head", NEUTRAL_HEAD)
            arms = step.get("arms", NEUTRAL_ARMS)
            wait = step.get("wait", _WAIT_DEFAULT)
            if controller is not None:
                try:
                    controller.send_head_angle(head)
                    controller.send_arm_offsets(*arms)
                    # Push to dashboard
                    try:
                        import dashboard_server
                        dashboard_server.update_status(head_angle=head, arms_offsets=list(arms))
                    except ImportError:
                        pass
                except Exception as exc:
                    print(f"[MOVEMENT] Serial error: {exc}")
            _t.sleep(wait)
    finally:
        set_robot_busy(False)


def idle_motion_loop():
    """
    Background loop that runs gentle movements (head swaying and shoulder breathing)
    when the robot is not busy speaking or performing a specific gesture.
    """
    import random
    import time
    from robot_hardware import get_esp32_controller, get_resting_arm_offsets
    
    # Wait a bit after startup
    time.sleep(5.0)
    
    last_head = 90
    last_shoulder = 0
    
    while True:
        try:
            time.sleep(random.uniform(5.0, 9.0))
            if is_robot_busy():
                continue
                
            controller = get_esp32_controller()
            if not controller:
                continue
                
            rest = get_resting_arm_offsets()
            
            # Choose a new target
            target_head = random.choice([87, 88, 89, 90, 91, 92, 93])
            target_shoulder = random.choice([0, 1, 2, 3])
            
            # Interpolate slowly to the target to make it extremely smooth and life-like
            steps = 15
            for i in range(1, steps + 1):
                if is_robot_busy():
                    break
                ratio = i / steps
                current_head = int(round(last_head + (target_head - last_head) * ratio))
                current_shoulder = int(round(last_shoulder + (target_shoulder - last_shoulder) * ratio))
                
                # Send to ESP32
                if controller.connect():
                    controller.send_head_angle(current_head)
                    controller.send_arm_offsets(
                        rest[0] + current_shoulder,
                        rest[1],
                        rest[2],
                        rest[3] + current_shoulder,
                        rest[4],
                        rest[5]
                    )
                    # Push to dashboard
                    try:
                        import dashboard_server
                        dashboard_server.update_status(
                            head_angle=current_head,
                            arms_offsets=[
                                rest[0] + current_shoulder,
                                rest[1],
                                rest[2],
                                rest[3] + current_shoulder,
                                rest[4],
                                rest[5]
                            ]
                        )
                    except ImportError:
                        pass
                time.sleep(0.12)
                
            if not is_robot_busy():
                last_head = target_head
                last_shoulder = target_shoulder
                
        except Exception:
            time.sleep(3.0)


def start_idle_motion_thread():
    t = threading.Thread(target=idle_motion_loop, name="idle-motion", daemon=True)
    t.start()
    print("[MOVEMENT] Idle motion thread started successfully.")


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os as _os
    # Disable serial for dry-run
    _os.environ.setdefault("ESP32_SERIAL_ENABLED", "false")

    def _check_arms(arms, *, rs=None, re=None, rw=None, ls=None, le=None, lw=None):
        """Assert specific joints are non-zero and others are zero."""
        expected_nonzero = {
            0: rs, 1: re, 2: rw, 3: ls, 4: le, 5: lw
        }
        errors = []
        for idx, expected in expected_nonzero.items():
            if expected is True:
                if arms[idx] == 0:
                    errors.append(f"  joint[{idx}] should be non-zero, got 0")
            elif expected is False or expected is None:
                if arms[idx] != 0:
                    errors.append(f"  joint[{idx}] should be 0, got {arms[idx]}")
        return errors

    _TESTS = [
        # (description, input_text, expect_match, joint_check_kwargs)
        # ── Shoulder only ──────────────────────────────────────────────────
        ("right arm raise — shoulder only",
         "o'ng qo'limni ko'tar",
         True, {"rs": True, "re": False, "rw": False, "ls": False, "le": False, "lw": False}),

        ("right arm raise STT variant",
         "o\u02bbng qo\u02bblimni ko\u02bbtar",
         True, {"rs": True, "re": False, "rw": False, "ls": False, "le": False, "lw": False}),

        ("right arm raise no-apostrophe",
         "ong qolimni kotar",
         True, {"rs": True, "re": False, "rw": False, "ls": False, "le": False, "lw": False}),

        ("left arm raise — shoulder only",
         "chap qo'limni ko'tar",
         True, {"rs": False, "re": False, "rw": False, "ls": True, "le": False, "lw": False}),

        ("both arms raise — shoulders only",
         "ikkala qo'lingni ko'tar",
         True, {"rs": True, "re": False, "rw": False, "ls": True, "le": False, "lw": False}),

        ("both arms raise — qo'llaring",
         "qo'llaringni ko'tar",
         True, {"rs": True, "re": False, "rw": False, "ls": True, "le": False, "lw": False}),

        # ── Elbow only ─────────────────────────────────────────────────────
        ("right elbow bend — elbow only",
         "o'ng tirsagingni buk",
         True, {"rs": False, "re": True, "rw": False, "ls": False, "le": False, "lw": False}),

        ("left elbow bend — elbow only",
         "chap tirsagingni buk",
         True, {"rs": False, "re": False, "rw": False, "ls": False, "le": True, "lw": False}),

        ("both elbows bend",
         "ikkala tirsagingni buk",
         True, {"rs": False, "re": True, "rw": False, "ls": False, "le": True, "lw": False}),

        # ── Wrist only ─────────────────────────────────────────────────────
        ("right wrist turn — wrist only",
         "o'ng bilagingni aylantir",
         True, {"rs": False, "re": False, "rw": True, "ls": False, "le": False, "lw": False}),

        ("left wrist turn — wrist only",
         "chap bilagingni aylantir",
         True, {"rs": False, "re": False, "rw": False, "ls": False, "le": False, "lw": True}),

        # ── Neutral ────────────────────────────────────────────────────────
        ("neutral reset",
         "neytral holatga qayt",
         True, {"rs": False, "re": False, "rw": False, "ls": False, "le": False, "lw": False}),

        # ── Greeting / wave ────────────────────────────────────────────────
        ("salom ber — shoulder raises, wrist oscillates, elbow=0",
         "salom ber",
         True, None),  # multi-step, checked separately below

        ("right arm wave — shoulder+wrist, elbow=0",
         "o'ng qo'lingni silkit",
         True, None),

        # ── Head ───────────────────────────────────────────────────────────
        ("head left", "boshni chapga bur", True, None),
        ("head right", "boshni o'ngga bur", True, None),
        ("head center", "boshni to'g'riga qara", True, None),

        # ── Chest (compound) ───────────────────────────────────────────────
        ("right arm to chest — shoulder+elbow",
         "o'ng qo'lingni ko'ksingga qo'y",
         True, {"rs": True, "re": True, "rw": False, "ls": False, "le": False, "lw": False}),

        ("both arms to chest",
         "ikkala qo'lingni ko'ksingga qo'y",
         True, {"rs": True, "re": True, "rw": False, "ls": True, "le": True, "lw": False}),

        # ── Lower ──────────────────────────────────────────────────────────
        ("lower arms", "qo'llaringni tushir", True, None),

        # ── Non-movement (should return None) ──────────────────────────────
        ("weather query — no match", "bugun qanday ob-havo", False, None),
        ("greeting — no match", "salom, ismingiz nima", False, None),
    ]

    print("=" * 70)
    print("movement_commands.py — anatomical self-test")
    print("=" * 70)
    passed = failed = 0

    for desc, text, expect_match, joint_check in _TESTS:
        result = parse_movement_command(text)
        matched = result is not None
        ok = matched == expect_match
        errors = []

        if ok and result and joint_check is not None:
            # Check first non-neutral step for joint isolation
            first_action_step = None
            for s in result["movements"]:
                if s["arms"] != NEUTRAL_ARMS:
                    first_action_step = s
                    break
            if first_action_step is None:
                # All steps are neutral — check that all joints are 0
                first_action_step = result["movements"][0]
            errors = _check_arms(first_action_step["arms"], **joint_check)
            if errors:
                ok = False

        # Validate all steps in range
        if result:
            for i, step in enumerate(result["movements"]):
                arms = step["arms"]
                head = step["head"]
                if len(arms) != 6:
                    errors.append(f"Step {i}: arms length {len(arms)} != 6")
                    ok = False
                if any(v < _OFFSET_MIN or v > _OFFSET_MAX for v in arms):
                    errors.append(f"Step {i}: arms out of range: {arms}")
                    ok = False
                if not (0 <= head <= 180):
                    errors.append(f"Step {i}: head out of range: {head}")
                    ok = False

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"  [{status}] {desc}")
        print(f"         input:  {text!r}")
        if result:
            print(f"         speech: {result['speech']}")
            print(f"         steps:  {len(result['movements'])}")
            for i, s in enumerate(result["movements"]):
                print(f"           [{i}] head={s['head']} arms={s['arms']} wait={s['wait']}")
        if errors:
            for e in errors:
                print(f"         ERROR: {e}")

    print()
    print(f"Results: {passed} passed, {failed} failed out of {len(_TESTS)} tests.")

    # ── Wave/salom elbow=0 check ───────────────────────────────────────────
    print()
    print("Wave elbow=0 check:")
    wave_result = parse_movement_command("salom ber")
    if wave_result:
        elbow_violations = [
            (i, s["arms"]) for i, s in enumerate(wave_result["movements"])
            if s["arms"][1] != 0 or s["arms"][4] != 0  # re or le non-zero
        ]
        if elbow_violations:
            print(f"  FAIL: elbow non-zero in steps: {elbow_violations}")
        else:
            print("  PASS: all steps have elbow=0 (anatomically correct)")

    # ── Validation edge cases ──────────────────────────────────────────────
    print()
    print("Validation edge cases:")
    r1 = validate_arm_offsets([0, 0, 0, 0, 0])
    print(f"  Wrong length (5): {r1}")  # None
    r2 = validate_arm_offsets([200, -200, 0, 0, 0, 0])
    print(f"  Out of range clamped: {r2}")  # [90, -90, 0, 0, 0, 0]
    r3 = validate_step({"arms": [0, 0, 0, 0, 0], "head": 90, "wait": 0.5})
    print(f"  Bad step (arms len 5): {r3}")  # None
    r4 = validate_movements([
        {"head": 90, "arms": [55, 0, 0, 0, 0, 0], "wait": 0.6},
        {"head": 200, "arms": [0, 0, 0, 0, 0, 0], "wait": 99.0},
        {"head": 90, "arms": [0, 0, 0], "wait": 0.3},
        "not a dict",
    ])
    print(f"  Validated sequence ({len(r4)} steps):")
    for s in r4:
        print(f"    head={s['head']} arms={s['arms']} wait={s['wait']}")

    # ── is_movement_intent() tests ─────────────────────────────────────────
    print()
    print("is_movement_intent tests:")
    intent_cases = [
        ("o'ng qo'lingni ko'tar", True),
        ("chap tirsagingni buk", True),
        ("boshingni chapga bur", True),
        ("ikki qo'lingni silkit", True),
        ("salom ber", True),
        ("o'ng qo'lingni 3 soniyadan keyin ko'tar", True),
        ("bugun qanday ob-havo", False),
        ("ismingiz nima", False),
        ("salom, ismingiz nima", False),
        ("matematikani tushuntirib ber", False),
    ]
    intent_pass = intent_fail = 0
    for text, expected in intent_cases:
        actual = is_movement_intent(text)
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        if ok:
            intent_pass += 1
        else:
            intent_fail += 1
        print(f"  [{status}] is_movement_intent({text!r}) = {actual} "
              f"(expected {expected})")
    print(f"  {intent_pass}/{len(intent_cases)} intent tests passed.")

    # ── parse_movement_sequence() compound tests ───────────────────────────
    print()
    print("parse_movement_sequence compound tests:")
    seq_cases = [
        # (description, text, expect_match, min_steps)
        ("single clause (raise right)", "o'ng qo'lingni ko'tar", True, 1),
        ("compound: raise + bend elbow",
         "o'ng qo'lingni ko'tarib tirsagingni buk", True, 2),
        ("head left then right",
         "boshingni chapga, o'ngga bur", True, 2),
        ("avval ... keyin",
         "avval o'ng qo'lingni ko'tar, keyin chap qo'lingni tushir", True, 2),
        ("two arms wave",
         "ikki qo'lingni ko'tarib salom ber", True, 2),
        ("compound: bend + rotate wrist",
         "o'ng tirsagingni bukib bilagingni aylantir", True, 2),
        ("delay: 3 soniyadan keyin",
         "chap qo'lingni 3 soniyadan keyin ko'tar", True, 2),  # delay+raise
        ("non-movement text → None",
         "bugun qanday ob-havo", False, 0),
        ("unknown clause inside compound → None",
         "o'ng qo'lingni ko'tar va sandalga otir", False, 0),
    ]
    seq_pass = seq_fail = 0
    for desc, text, expect_match, min_steps in seq_cases:
        result = parse_movement_sequence(text)
        matched = result is not None
        ok = matched == expect_match
        if ok and result and min_steps:
            ok = len(result.get("movements", [])) >= min_steps
        status = "PASS" if ok else "FAIL"
        if ok:
            seq_pass += 1
        else:
            seq_fail += 1
        print(f"  [{status}] {desc}: {text!r}")
        if result:
            print(f"         steps={len(result['movements'])} "
                  f"speech={result['speech']!r}")
    print(f"  {seq_pass}/{len(seq_cases)} sequence tests passed.")

    # ── parse_ai_movement_plan() tests ─────────────────────────────────────
    print()
    print("parse_ai_movement_plan tests:")
    ai_cases = [
        # valid: raise right_arm
        ('{"is_movement": true, "speech": "Mayli.", '
         '"commands": [{"action": "raise", "target": "right_arm"}]}',
         True, "raise right_arm"),
        # valid: wait then raise
        ('{"is_movement": true, "speech": "Hozir.", '
         '"commands": [{"wait": 2}, {"action": "raise", "target": "left_arm"}]}',
         True, "wait + raise"),
        # valid with code fence
        ('```json\n{"is_movement": true, "speech": "Ok.", '
         '"commands": [{"action": "wave", "target": "right_arm"}]}\n```',
         True, "fenced JSON"),
        # invalid: is_movement false
        ('{"is_movement": false, "speech": "Yo\'q.", "commands": []}',
         False, "is_movement=false"),
        # invalid: bad JSON
        ('not json at all', False, "bad JSON"),
        # invalid: empty commands
        ('{"is_movement": true, "speech": "...", "commands": []}',
         False, "empty commands"),
        # invalid: unknown action
        ('{"is_movement": true, "speech": "...", '
         '"commands": [{"action": "fly", "target": "right_arm"}]}',
         False, "unknown action"),
    ]
    ai_pass = ai_fail = 0
    for plan_json, expect_match, desc in ai_cases:
        result = parse_ai_movement_plan(plan_json)
        matched = result is not None
        ok = matched == expect_match
        status = "PASS" if ok else "FAIL"
        if ok:
            ai_pass += 1
        else:
            ai_fail += 1
        print(f"  [{status}] {desc}: matched={matched} (expected {expect_match})")
        if result:
            print(f"         steps={len(result['movements'])} "
                  f"source={result.get('source')}")
    print(f"  {ai_pass}/{len(ai_cases)} AI plan tests passed.")

    # ── Final tally ────────────────────────────────────────────────────────
    print()
    total_pass = passed + intent_pass + seq_pass + ai_pass
    total = len(_TESTS) + len(intent_cases) + len(seq_cases) + len(ai_cases)
    print(f"OVERALL: {total_pass}/{total} tests passed.")
    if total_pass != total:
        sys.exit(1)
