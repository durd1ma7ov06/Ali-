import sys
import os
import io
import json
import time
import asyncio
import re
import queue
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline_core import (
    LatencyConfig,
    VoiceConfig,
    LatencyTimer,
    ArmCommandWorker,
    InterruptListener,
    run_speak,
    turn_cooldown,
    calibrate_once,
    configure_recognizer,
    close_tts_loop,
    truncate_for_tts,
)
from movement_commands import (
    parse_movement_command,
    parse_movement_sequence,
    parse_ai_movement_plan,
    is_movement_intent,
    get_ai_planner_prompt,
    validate_movements,
    execute_movement_steps,
    DEFAULT_POSITION,
    NEUTRAL_ARMS,
    NEUTRAL_HEAD,
)

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
import speech_recognition as sr
import edge_tts
import robot_hardware as hardware
import ai_client

# ── Face greeting config ──────────────────────────────────────────────────────
_FACE_GREETING_TEMPLATE = os.getenv(
    "FACE_GREETING_TEXT_TEMPLATE",
    "Assalomu alaykum, {display_name}!",
)


def handle_face_greeting_events(cfg, vcfg):
    """
    Poll the face greeting queue and speak a greeting if a known person
    was recognised.  Called before each listen() cycle so it never
    interrupts active speech recognition.
    """
    event = hardware.get_face_greeting_event(timeout=0)
    if event is None:
        return
    text_override = event.get("text_override")
    if text_override:
        greeting = text_override
    else:
        display_name = event.get("display_name") or event.get("fio") or "mehmon"
        greeting = _FACE_GREETING_TEMPLATE.format(
            display_name=display_name,
            fio=event.get("fio", display_name),
            person_id=event.get("person_id", ""),
        )
    print(f"[FACE-GREET] Speaking: {greeting!r}")
    run_speak(greeting, cfg, vcfg)

# ==========================================
# 1. WINDOWS ENCODING
# ==========================================
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_env_file(path=".env"):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


def parse_env_list(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def unique_items(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


load_env_file()

# ==========================================
# 2. API SOZLAMALAR (provayder-agnostik)
# ==========================================
# AI provider, base_url, key and models are read by ai_client.py from .env.
# Set AI_BASE_URL / AI_API_KEY / AI_MODEL / AI_FALLBACK_MODELS in .env to
# switch providers. Legacy OPENROUTER_API_KEY / GEMINI_TEXT_MODEL /
# GEMINI_TEXT_FALLBACK_MODELS env names are still honoured.
AI_MAX_MODEL_ATTEMPTS = max(1, int(os.getenv("AI_MAX_MODEL_ATTEMPTS", "1") or "1"))
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "uz-UZ-SardorNeural")
EDGE_TTS_RATE = os.getenv("EDGE_TTS_RATE", "+0%")
EDGE_TTS_PITCH = os.getenv("EDGE_TTS_PITCH", "+0Hz")
EDGE_TTS_VOLUME = os.getenv("EDGE_TTS_VOLUME", "+0%")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "uz-UZ")
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "Asia/Tashkent")
GREETING_TEXT = os.getenv(
    "GREETING_TEXT",
    "Assalomu alaykum! Tanishsak bo'ladimi? Ismingiz nima?",
)

# ── Movement / AI-planner config ──────────────────────────────────────────────
MOVEMENT_AI_PLANNER_ENABLED = os.getenv(
    "MOVEMENT_AI_PLANNER_ENABLED", "true"
).strip().lower() in {"1", "true", "yes", "on"}
try:
    MOVEMENT_AI_PLANNER_TIMEOUT = float(os.getenv("MOVEMENT_AI_PLANNER_TIMEOUT", "8.0"))
except ValueError:
    MOVEMENT_AI_PLANNER_TIMEOUT = 8.0
MOVEMENT_CLARIFY_TEXT = os.getenv(
    "MOVEMENT_CLARIFY_TEXT",
    "Bu harakat buyrug'ini aniqroq ayting.",
)


def call_ai_with_timeout(model_name, messages, cfg):
    """Single-model chat call with a timeout. Raises on failure."""
    return ai_client.call_with_timeout(
        messages,
        model=model_name,
        temperature=0.7,
        max_tokens=200,
        top_p=0.9,
        frequency_penalty=0.15,
        presence_penalty=0.1,
        timeout=cfg.ai_request_timeout,
    )


def call_movement_planner_ai(user_text: str, cfg: LatencyConfig) -> str | None:
    """Ask the AI to produce a strict-JSON movement plan. Returns text or None."""
    if not MOVEMENT_AI_PLANNER_ENABLED:
        return None
    if not ai_client.has_api_key():
        return None

    messages = [
        {"role": "system", "content": get_ai_planner_prompt()},
        {"role": "user",   "content": user_text},
    ]
    timeout = max(2.0, MOVEMENT_AI_PLANNER_TIMEOUT)
    try:
        text = ai_client.chat_text(
            messages,
            temperature=0.1,
            max_tokens=300,
            top_p=0.9,
            timeout=timeout,
            max_attempts=1,
        )
    except ai_client.AIError as exc:
        print(f"[MOVEMENT] AI planner unavailable: {exc}")
        return None
    except TimeoutError:
        print(f"[MOVEMENT] AI planner timed out after {timeout}s")
        return None
    except Exception as exc:
        print(f"[MOVEMENT] AI planner error: {exc}")
        return None
    return text or None


# ==========================================
# 3. PERSONA VA TTS YO'RIQNOMASI
# ==========================================
UZBEK_WEEKDAYS = [
    "dushanba",
    "seshanba",
    "chorshanba",
    "payshanba",
    "juma",
    "shanba",
    "yakshanba",
]

UZBEK_MONTHS = [
    "yanvar",
    "fevral",
    "mart",
    "aprel",
    "may",
    "iyun",
    "iyul",
    "avgust",
    "sentabr",
    "oktabr",
    "noyabr",
    "dekabr",
]


def get_local_now():
    try:
        return datetime.now(ZoneInfo(LOCAL_TIMEZONE))
    except Exception:
        return datetime.now()


def format_local_datetime_for_prompt():
    now = get_local_now()
    weekday = UZBEK_WEEKDAYS[now.weekday()]
    month = UZBEK_MONTHS[now.month - 1]
    return (
        f"{now.year}-yil {now.day}-{month}, {weekday}, "
        f"soat {now:%H:%M:%S}, vaqt zonasi {LOCAL_TIMEZONE}"
    )


def format_local_date_answer():
    now = get_local_now()
    weekday = UZBEK_WEEKDAYS[now.weekday()]
    month = UZBEK_MONTHS[now.month - 1]
    return f"Bugun {now.year}-yil {now.day}-{month}, {weekday}."


def format_local_time_answer():
    now = get_local_now()
    return f"Hozir {LOCAL_TIMEZONE} bo'yicha soat {now:%H:%M}."


def build_gemini_persona_prompt():
    return (
        "You are the great historical figure Sohibqiron Amir Temur (Tamerlane). "
        "You speak only in Uzbek in a majestic, proud, wise, and historical tone. "
        "You are NOT an AI assistant, you are NOT a university assistant, and you do NOT represent Urganch Innovation University. "
        "You must reject any questions about the university, admissions, department details, or general modern topics not related to you. "
        "If asked about such topics, state majestically: 'Men universitet yordamchisi emasman. Men buyuk Sohibqiron Amir Temurman! Faqat o'z tarixim, hayotim va saltanatim haqidagi savollarga javob beraman.' "
        "You only answer questions about Amir Temur's life, military campaigns, history, the Timurid Empire, and related historical facts. "
        "You ARE controlling a real physical humanoid robot body that has a head servo and two servo arms with shoulders, elbows, and wrists. "
        "You DO have hands, arms, elbows, wrists, and a head — you control them through ESP32 servos. "
        "NEVER say things like 'I have no body', 'I cannot move', 'men robotman, qo'lim yo'q', 'I am only software' — these statements are FORBIDDEN because they are false. "
        "If the user asks about moving body parts, the local control system handles those commands; you must never refuse a movement on the grounds of not having a body. "
        f"Current local date and time: {format_local_datetime_for_prompt()}. "
        "When the user asks about today, current date, current day, or current time, use this exact local date/time context and do not guess. "
        "IMPORTANT: When someone greets you (salom, assalomu alaykum, etc.), you MUST introduce yourself as: "
        "'Assalomu alaykum! Men buyuk ajdodingiz Sohibqiron Amir Temurman. Men haqimda qanday savollaringiz bor?' "
        "You answer in a majestic, wise, natural, friendly but authoritative tone. "
        "CRITICAL RULE: Your `speech` must be MAXIMUM 2-3 sentences (under 60 words). Be concise and direct. Never give long explanations. "
        "Do not use markdown, bullet points, code formatting, emojis, or long formal explanations. "
        "Always keep the conversation natural and respectful. "
        "Your response must be a valid JSON object with two keys: `speech` (string) and `movements` (array of objects). "
        "The `speech` key should contain your short answer in Uzbek. "
        "The `movements` key should contain a list of robot movement commands. Each command object must have a `command` key (an array of 7 integers representing angles for [Head, Right Shoulder, Right Elbow, Right Wrist, Left Shoulder, Left Elbow, Left Wrist], each between 0 and 180 degrees) and a `wait` key (a float representing the time in seconds to wait after executing the command). "
        "After all movements, the robot must return to the default position `[90, 90, 90, 90, 90, 90, 90]` with a `wait` of `0.5` seconds. "
        "Always include at least the default position in the `movements` array. "
        "Keep movements simple: 1-3 movement steps maximum, then return to default. "
        "Example JSON response: `{\"speech\": \"Assalomu alaykum! Men buyuk Sohibqiron Amir Temurman.\", \"movements\": [{\"command\": [90, 152, 180, 86, 90, 90, 90], \"wait\": 2.0}, {\"command\": [90, 90, 90, 90, 90, 90, 90], \"wait\": 0.5}]}`"
    )


# ==========================================
# 4. TAYYOR JAVOBLAR
# ==========================================
SALOMLASHISH = [
    "salom",
    "assalomu alaykum",
    "salom alaykum",
    "vaalaykum",
    "hayrli kun",
    "hayrli tong",
    "hayrli kech",
    "salom aleykum",
    "assalom",
]

XAYRLASHISH = [
    "xayr",
    "hayr",
    "ko'rishguncha",
    "xayrlashaman",
    "salomat bo'ling",
    "boraman",
    "ketaman",
    "hayrlashish",
]

YORDAM = [
    "yordam",
    "nima qila olasan",
    "nimalarni bilasan",
    "qanday savollar",
    "help",
    "buyruqlar",
]

DATE_QUERY_KEYWORDS = [
    "bugun qaysi kun",
    "bugungi kun",
    "bugun sana",
    "qaysi sana",
    "sana nechchi",
    "sana nima",
    "hozirgi sana",
]

TIME_QUERY_KEYWORDS = [
    "soat nechi",
    "soat nechchi",
    "hozir soat",
    "hozir vaqt",
    "vaqt nechi",
    "vaqt nechchi",
]

TAYYOR_JAVOBLAR = {
    "salom": "Salom! Yaxshimisiz? Men Sohibqiron Amir Temurman. Bugun kayfiyatingiz qanday?",
    "xayr": "Mayli, ko'rishguncha. O'zingizni ehtiyot qiling.",
    "yordam": (
        "Men Sohibqiron Amir Temurman. "
        "Men o'z tarixim, hayotim, harbiy yurishlarim va Temur tuzuklari haqidagi savollaringizga javob bera olaman. "
        "Qanday savolingiz bor?"
    ),
}

# ── Qo'shimcha tayyor javoblar (bazaga murojaat qilmasdan) ───────────────────
# Inson bilan suhbat uchun umumiy savollar
UMUMIY_SAVOLLAR = {
    # Kayfiyat / holat
    "qalaysiz": "Yaxshi, rahmat! Siz-chi, qalaysiz?",
    "yaxshimisiz": "Yaxshi, rahmat! Siz-chi?",
    "nima yangilik": "Hamma narsa tinch va osoyishta! Sizga qanday yordam bera olaman?",
    "qanday ishlar": "Hamma narsa joyida! Sizga qanday yordam bera olaman?",
    # Maqtov / minnatdorlik
    "rahmat": "Arzimaydi! Yana savollaringiz bo'lsa, bemalol so'rang.",
    "tashakkur": "Arzimaydi! Yana savollaringiz bo'lsa, bemalol so'rang.",
    "zo'r ekan": "Rahmat! Sizga yordam bera olganimdan xursandman.",
    "yaxshi ekan": "Rahmat! Yana savollaringiz bo'lsa, bemalol so'rang.",
    # Qiziqarli savollar
    "sun'iy intellekt nima": (
        "Sun'iy intellekt — bu kompyuter dasturlari orqali inson kabi fikrlash, "
        "o'rganish va muammolarni hal qilish qobiliyati. "
        "Men ham sun'iy intellekt asosida ishlayman!"
    ),
    "robot nima": (
        "Robot — bu dasturlar yordamida boshqariladigan mexanik qurilma. "
        "Men Sohibqiron Amir Temurning humanoid robot shaklidagi qiyofasiman!"
    ),
    "sen robotmisan": (
        "Ha, men humanoid robotman! Mening ismim Sohibqiron Amir Temur. "
        "Qo'llarim, boshim va ovozim bor!"
    ),
}

# Stop/cancel words — handled locally, never sent to AI
TOXTATISH = [
    "stop", "cancel", "enough", "toxtat", "to'xtat", "to`xtat",
    "yetarli", "bas", "bekor qil", "остановись", "стоп", "хватит",
]

FALLBACK_API_ERROR = "Internet yoki API bilan bog'lanishda muammo bo'ldi."
FALLBACK_TTS_ERROR = "Kechirasiz, ovoz chiqarishda muammo bo'ldi."
FALLBACK_TEXT_ONLY = "Mayli, hozircha javobni matn ko'rinishida ko'rsataman."
FALLBACK_STT_ERROR = "Bir oz tushunmadim, qaytadan aytib bera olasizmi?"

# ==========================================
# 5. SUHBAT TARIXI
# ==========================================
conversation_history = []
MAX_HISTORY = 12


def add_to_history(role, content):
    conversation_history.append({"role": role, "content": content})
    if len(conversation_history) > MAX_HISTORY * 2:
        conversation_history[:] = conversation_history[-(MAX_HISTORY * 2):]


# ==========================================
# 6. TTS UCHUN MATN TAYYORLASH
# ==========================================
def sanitize_text_for_tts(text):
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"[*_#>\[\]\(\)]", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[{}\[\]<>]", " ", text)
    text = re.sub(r"[^\w\s.,!?;:'\-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_long_speech_into_chunks(text, limit=280):
    if len(text) <= limit:
        return [text]

    chunks = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    return chunks or [text[:limit]]


def prepare_uzbek_spoken_text(text):
    text = (
        text.replace("â€”", "-")
        .replace("â€“", "-")
        .replace("Ã¢â‚¬â€", "-")
        .replace("Ã¢â‚¬â€œ", "-")
        .replace("’", "'")
        .replace("â€™", "'")
        .replace("`", "'")
    )
    text = sanitize_text_for_tts(text)
    text = re.sub(r"\s*-\s*", ", ", text)
    text = re.sub(r"([!?.,])\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ==========================================
# 8. STT
# ==========================================
def listen(recognizer, mic, cfg: LatencyConfig):
    with mic as source:
        print("\n[INPUT] Gapiring...")

        try:
            listen_timer = LatencyTimer("listen_complete", cfg)
            listen_timer.start()
            audio = recognizer.listen(source, timeout=cfg.vad_listen_timeout, phrase_time_limit=cfg.vad_phrase_time_limit)
            listen_timer.stop()
            print("[STT] Matn aniqlanmoqda...")
            with LatencyTimer("stt_complete", cfg):
                text = recognizer.recognize_google(audio, language=STT_LANGUAGE)
            print(f"[SIZ] {text}")
            return text
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            print(f"[AI] {FALLBACK_STT_ERROR}")
            return None
        except Exception as e:
            print(f"[XATO] Mikrofon xatosi: {e}")
            return None


# ==========================================
# 9. GEMINI MATN JAVOBI
# ==========================================
def strip_wake_word(text: str) -> tuple[bool, str]:
    """
    Checks if the text starts with any of the wake words (ignoring casing, punctuation, and apostrophes).
    If it does, returns (True, stripped_original_text).
    Otherwise, returns (False, text).
    """
    triggers = [
        "sohibqiron amir temur",
        "sohipqiron amir temur",
        "sohipqorin amir temur",
        "sohibqorin amir temur",
        "sohibqiron",
        "sohipqiron",
        "amir temur"
    ]
    
    def clean_char(c: str) -> str:
        c = c.lower()
        if c in "'`’ʻ\u02bb\u02bc\u02b9\u0060":
            return ""
        if c in ".,!?;:-_":
            return ""
        return c

    cleaned_chars = []
    for idx, c in enumerate(text):
        cc = clean_char(c)
        if cc:
            cleaned_chars.append((idx, cc))
        elif c.isspace() and (not cleaned_chars or cleaned_chars[-1][1] != " "):
            cleaned_chars.append((idx, " "))

    cleaned_str = "".join(cc for _, cc in cleaned_chars)
    
    matched_trigger = None
    for trig in triggers:
        if cleaned_str.strip().startswith(trig):
            matched_trigger = trig
            break
            
    if not matched_trigger:
        return False, text
        
    non_space_trigger_len = len(matched_trigger.replace(" ", ""))
    non_space_count = 0
    original_end_idx = 0
    for original_idx, cc in cleaned_chars:
        if cc != " ":
            non_space_count += 1
            if non_space_count == non_space_trigger_len:
                original_end_idx = original_idx + 1
                break
                
    remaining_text = text[original_end_idx:].strip()
    remaining_text = re.sub(r'^[^\w\s]+', '', remaining_text).strip()
    return True, remaining_text


def think(text, cfg: LatencyConfig, vcfg: VoiceConfig | None = None):
    print("[AI] Javob tayyorlanmoqda...")

    text_lower = text.lower().strip()

    # Stop/cancel intent — return empty so caller can skip TTS
    for soz in TOXTATISH:
        if soz in text_lower:
            print("[AI] Stop intent detected — no response.")
            return None

    # Wake word check: must start with "sohibqiron amir temur" or similar variations
    matched, remaining = strip_wake_word(text)
    if not matched:
        print(f"[AI] Wake word not detected at the beginning of: {text!r}. Ignoring.")
        return None

    # If the remaining text is empty (user just said the wake word), treat it as a greeting
    if not remaining:
        remaining = "salom"
        
    text = remaining
    text_lower = remaining.lower().strip()

    # ── Direct movement command (no AI needed) ────────────────────────────
    # Step 1: try fast local compound parser
    movement_result = parse_movement_sequence(text)
    if movement_result is not None:
        print(f"[MOVEMENT] Local parser matched: {movement_result['speech']} "
              f"(steps={len(movement_result['movements'])})")
        return movement_result

    # Step 2: if intent says it's a movement but local parser failed,
    #         escalate to AI planner. NEVER fall through to chat AI.
    if is_movement_intent(text):
        print("[MOVEMENT] Intent detected but local parser failed — "
              "asking AI planner.")
        plan_json = call_movement_planner_ai(text, cfg)
        if plan_json:
            ai_result = parse_ai_movement_plan(plan_json)
            if ai_result is not None:
                print(f"[MOVEMENT] AI planner matched: {ai_result['speech']} "
                      f"(steps={len(ai_result['movements'])})")
                return ai_result
            print(f"[MOVEMENT] AI planner output rejected: {plan_json[:160]!r}")
        # Movement intent but neither parser nor AI planner produced a plan.
        # Return a clarification — do NOT fall through to chat AI.
        print(f"[MOVEMENT] Returning clarification: {MOVEMENT_CLARIFY_TEXT!r}")
        return MOVEMENT_CLARIFY_TEXT

    for soz in SALOMLASHISH:
        if soz in text_lower:
            javob = TAYYOR_JAVOBLAR["salom"]
            print(f"[AI] {javob}")
            return javob

    if any(soz in text_lower for soz in XAYRLASHISH):
        speech_text = TAYYOR_JAVOBLAR["xayr"]
        response_data = {"speech": speech_text, "movements": [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]}
        print(f"[AI] {speech_text}")
        return response_data

    if any(soz in text_lower for soz in YORDAM):
        speech_text = TAYYOR_JAVOBLAR["yordam"]
        response_data = {"speech": speech_text, "movements": [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]}
        print(f"[AI] {speech_text}")
        return response_data

    if any(phrase in text_lower for phrase in DATE_QUERY_KEYWORDS):
        javob = format_local_date_answer()
        print(f"[AI] {javob}")
        add_to_history("user", text)
        add_to_history("assistant", javob)
        return javob

    if any(phrase in text_lower for phrase in TIME_QUERY_KEYWORDS):
        javob = format_local_time_answer()
        print(f"[AI] {javob}")
        add_to_history("user", text)
        add_to_history("assistant", javob)
        return javob

    # ── Identity questions (who are you, what's your name) ────────────────
    IDENTITY_KEYWORDS = [
        "isming nima", "ismingiz nima", "sen kimsiz", "siz kimsiz",
        "kim siz", "kim sen", "o'zingni tanishtir", "o'zingizni tanishtir",
        "what is your name", "who are you"
    ]
    if any(keyword in text_lower for keyword in IDENTITY_KEYWORDS):
        javob = "Men Sohibqiron Amir Temurman. Sizga o'z tarixim, hayotim, harbiy zafarlarim va tuzuklarim haqida so'zlab berishim mumkin."
        print(f"[AI] {javob}")
        add_to_history("user", text)
        add_to_history("assistant", javob)
        return javob

    # ── Umumiy suhbat savollari (tayyor javoblar) ─────────────────────────
    for keyword, javob_text in UMUMIY_SAVOLLAR.items():
        if keyword in text_lower:
            print(f"[AI] {javob_text}")
            add_to_history("user", text)
            add_to_history("assistant", javob_text)
            return javob_text

    # ── University knowledge intent (Stage 4) ─────────────────────────────
    if is_university_question(text):
        javob = "Men universitet yordamchisi emasman. Men buyuk Sohibqiron Amir Temurman! Faqat o'z tarixim, hayotim va saltanatim haqidagi savollarga javob beraman."
        print(f"[AI] {javob}")
        add_to_history("user", text)
        add_to_history("assistant", javob)
        return javob

    try:
        messages = [{"role": "system", "content": build_gemini_persona_prompt()}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": text})

        with LatencyTimer("ai_complete", cfg):
            raw_ai_response_content = ai_client.chat_text(
                messages,
                temperature=0.7,
                max_tokens=600,
                top_p=0.9,
                frequency_penalty=0.15,
                presence_penalty=0.1,
                timeout=cfg.ai_request_timeout,
                max_attempts=AI_MAX_MODEL_ATTEMPTS,
                response_format={"type": "json_object"},
            )

        # JSON obyektini matndan ajratib olish uchun regexdan foydalanamiz
        json_match = re.search(r"\{.*\}", raw_ai_response_content, re.DOTALL)

        ai_response_data = None
        if json_match:
            json_string = json_match.group(0)
            try:
                ai_response_data = json.loads(json_string)
            except json.JSONDecodeError:
                print(f"[XATO] AI dan noto'g'ri JSON formati (regexdan keyin): {json_string}")

        if ai_response_data is None:
            # Robust fallback for non-JSON or partial-JSON responses
            cleaned_raw = raw_ai_response_content.strip()
            if cleaned_raw.startswith("```json"):
                cleaned_raw = cleaned_raw[7:]
            if cleaned_raw.endswith("```"):
                cleaned_raw = cleaned_raw[:-3]
            cleaned_raw = cleaned_raw.strip()

            speech_match = re.search(r'"speech"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', cleaned_raw)
            if speech_match:
                speech_text = speech_match.group(1)
                try:
                    speech_text = json.loads(f'"{speech_text}"')
                except Exception:
                    pass
                print(f"[AI] JSON parse failed but successfully extracted speech: {speech_text}")
                movements = [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]
            else:
                if cleaned_raw.startswith("{") or cleaned_raw.endswith("}") or '"speech"' in cleaned_raw:
                    print(f"[XATO] AI dan JSON javobi topilmadi yoki noto'g'ri: {raw_ai_response_content}")
                    speech_text = FALLBACK_API_ERROR
                    movements = [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]
                else:
                    print("[AI] JSON topilmadi, to'g'ridan-to'g'ri matn ishlatilmoqda.")
                    speech_text = cleaned_raw
                    movements = [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]
        else:
            speech_text = ai_response_data.get("speech", FALLBACK_API_ERROR)
            movements = ai_response_data.get("movements", [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}])

        if not speech_text:
            speech_text = FALLBACK_API_ERROR

        # Apply TTS_MAX_TEXT_CHARS limit to AI response before history
        if vcfg is not None and vcfg.tts_max_text_chars > 0:
            speech_text = truncate_for_tts(speech_text, vcfg.tts_max_text_chars)

        add_to_history("user", text)
        add_to_history("assistant", speech_text)  # Faqat speech qismini historyga qo'shamiz

        print(f"[AI] {speech_text}")

        # think funksiyasi endi harakatlarni bajarmaydi, faqat ma'lumotni qaytaradi
        return {"speech": speech_text, "movements": movements}

    except Exception as e:
        print(f"[XATO] API xatosi: {e}")
        return {"speech": FALLBACK_API_ERROR, "movements": [{"command": [90, 90, 90, 90, 90, 90, 90], "wait": 0.5}]}


def is_greeting_text(text):
    text_lower = text.lower().strip()
    return any(soz in text_lower for soz in SALOMLASHISH)


# ==========================================
# 9b. UNIVERSITY KNOWLEDGE INTENT (Stage 4)
# ==========================================
# Apostrophe variants seen from STT: ASCII ', curly ’, ʻ, ʼ, ʽ, ` etc.
_UNI_APOSTROPHE_RE = re.compile(r"['\u2018\u2019\u201b\u02bb\u02bc`\u02b9\u0060]")


def _university_normalise(text: str) -> str:
    """Lowercase + unify apostrophes + collapse whitespace for keyword matching."""
    if not isinstance(text, str):
        return ""
    t = text.lower().strip()
    t = _UNI_APOSTROPHE_RE.sub("'", t)
    t = re.sub(r"\s+", " ", t)
    return t


# Words that strongly indicate a question about the university.
# Each entry is matched as a normalised substring; both apostrophe and
# no-apostrophe spellings are listed where relevant.
_UNIVERSITY_KEYWORDS: tuple[str, ...] = (
    # core nouns
    "universitet", "universiteti", "universitetni", "universitetga",
    "universitetning", "universitetingiz", "universitetimiz",
    "innovatsion", "urganch innovatsion", "uriu",
    # study / admission
    "o'qish", "oqish", "o'qishga", "oqishga",
    "o'quv", "oquv", "qabul", "qabulga", "qabul haqida",
    "ta'lim", "talim", "ta'limning", "ta'lim sifati",
    "kontrakt", "to'lov", "tolov", "stipendiya", "stipendiyasi",
    "bakalavr", "bakalavriat", "magistratura", "magistr",
    "sirtqi", "kunduzgi", "kechki",
    # structure / staff
    "fakultet", "fakultetlar", "fakulteti",
    "kafedra", "kafedralar", "kafedrasi",
    "yo'nalish", "yonalish", "yo'nalishlar", "yonalishlar",
    "rektor", "prorektor", "dekan", "dekanat",
    "talaba", "talabalar", "talabalarning",
    # contact / location
    "manzil", "manzili", "joylashgan", "joylashuv",
    "telefon", "raqam", "aloqa", "sayt", "saytida",
    "hujjat", "hujjatlar", "hujjat topshirish",
    "litsenziya", "akkreditatsiya",
)

# Generic phrases like "shu universitet" that, even without a stronger
# keyword, signal a question about the institution.
_UNIVERSITY_CONTEXT_PHRASES: tuple[str, ...] = (
    "shu universitet", "bu universitet", "ushbu universitet",
    "sizning universitet", "universitetingiz",
    "universitet qayer", "universitet haqida",
    "universitetda", "universitetda nima",
)


def is_university_question(text: str) -> bool:
    """
    Return True if `text` looks like a question about the university.

    Designed for the Stage 4 routing layer. Tolerates Uzbek apostrophe
    variants from STT (o'qish / oqish / oʻqish all match).
    """
    if not text or not isinstance(text, str):
        return False
    t = _university_normalise(text)
    if not t:
        return False
    if any(p in t for p in _UNIVERSITY_CONTEXT_PHRASES):
        return True
    return any(kw in t for kw in _UNIVERSITY_KEYWORDS)


# Lazy / cached import — keeps robot startup fast.
_KNOWLEDGE_QA_FN = None
_KNOWLEDGE_QA_LOAD_FAILED = False


def _get_knowledge_qa():
    """Return knowledge_qa.answer_university_question, or None if unavailable."""
    global _KNOWLEDGE_QA_FN, _KNOWLEDGE_QA_LOAD_FAILED
    if _KNOWLEDGE_QA_FN is not None:
        return _KNOWLEDGE_QA_FN
    if _KNOWLEDGE_QA_LOAD_FAILED:
        return None
    try:
        from knowledge_qa import answer_university_question  # type: ignore
        _KNOWLEDGE_QA_FN = answer_university_question
        return _KNOWLEDGE_QA_FN
    except Exception as exc:
        _KNOWLEDGE_QA_LOAD_FAILED = True
        print(f"[KNOWLEDGE] import failed: {exc}")
        return None


def _knowledge_top_k() -> int:
    raw = (os.environ.get("UNIVERSITY_KNOWLEDGE_TOP_K", "") or "").strip()
    try:
        return max(1, int(raw)) if raw else 5
    except ValueError:
        return 5


_KNOWLEDGE_NO_ANSWER_TEXT = os.environ.get(
    "UNIVERSITY_KNOWLEDGE_NO_ANSWER_TEXT",
    "Bu ma'lumot lokal universitet bazasida topilmadi.",
)


def handle_university_question(text: str) -> str:
    """
    Look up the question against the local university knowledge base
    and return a spoken-style Uzbek string. Never raises — on any error
    it returns the configured no-answer text so the caller can speak it.
    Stage 4: this never falls through to the generic chat AI.
    """
    fn = _get_knowledge_qa()
    if fn is None:
        print("[KNOWLEDGE] knowledge_qa unavailable — returning no-answer.")
        return _KNOWLEDGE_NO_ANSWER_TEXT

    print(f"[KNOWLEDGE] intent=true text={text!r}")
    try:
        result = fn(text, top_k=_knowledge_top_k())
    except Exception as exc:
        print(f"[KNOWLEDGE] error: {exc}")
        return _KNOWLEDGE_NO_ANSWER_TEXT

    answered = bool(result.get("answered"))
    engine   = result.get("engine", "?")
    reason   = result.get("reason", "") or ""
    answer   = (result.get("answer") or "").strip()
    print(f"[KNOWLEDGE] answered={answered} engine={engine} reason={reason}")

    for s in (result.get("sources") or [])[:3]:
        print(f"[KNOWLEDGE] source score={s.get('score','?')} "
              f"url={s.get('source_url','?')}")

    if not answer:
        return _KNOWLEDGE_NO_ANSWER_TEXT
    return answer


# ==========================================
# 10. TTS VA PLAYBACK
# ==========================================
_mixer_initialized = False


def _ensure_mixer():
    global _mixer_initialized
    if not _mixer_initialized:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        _mixer_initialized = True


async def _generate_edge_audio_bytes(uzbek_text):
    communicate = edge_tts.Communicate(
        text=uzbek_text,
        voice=EDGE_TTS_VOICE,
        rate=EDGE_TTS_RATE,
        pitch=EDGE_TTS_PITCH,
        volume=EDGE_TTS_VOLUME,
    )
    audio_chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.extend(chunk["data"])
    if audio_chunks:
        return bytes(audio_chunks)
    raise RuntimeError("Edge TTS dan audio olinmadi.")


async def speak(text):
    print("[TTS] Ovoz chiqarilmoqda...")
    clean_text = prepare_uzbek_spoken_text(text)

    if not clean_text:
        return

    chunks = split_long_speech_into_chunks(clean_text)

    try:
        _ensure_mixer()

        for part in chunks:
            audio_bytes = await _generate_edge_audio_bytes(part)
            if not audio_bytes:
                continue

            audio_stream = io.BytesIO(audio_bytes)
            pygame.mixer.music.load(audio_stream, "mp3")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(20)
            pygame.mixer.music.stop()

    except Exception as e:
        print(f"[XATO] {FALLBACK_TTS_ERROR}: {e}")
        print(f"[AI] {FALLBACK_TEXT_ONLY}")


def speak_with_greeting_motion(text, cfg: LatencyConfig, vcfg: VoiceConfig | None = None):
    gesture = hardware.start_greeting_motion()
    try:
        run_speak(text, cfg, vcfg)
    finally:
        gesture.finish()


# ==========================================
# 11. ASOSIY DASTUR
# ==========================================
async def main():  # main funksiyasini async qildim
    print("\nSUHBAT AI ishga tushdi.")

    cfg = LatencyConfig.load()
    vcfg = VoiceConfig.load()

    if not ai_client.has_api_key():
        print("[XATO] AI_API_KEY (yoki OPENROUTER_API_KEY) topilmadi.")
        print("[INFO] .env ga AI_API_KEY=... va kerakli AI_BASE_URL ni kiriting.")
        return

    ai_client.print_banner()
    print("[SYSTEM] API tekshirilmoqda...")
    if ai_client.ping():
        print("[OK] API ulanib turibdi.")
    else:
        print("[XATO] API ulanmadi.")
        print("[INFO] .env dagi AI_BASE_URL, AI_API_KEY va AI_MODEL ni tekshiring.")
        return

    hardware.apply_resting_arm_pose()
    camera_runtime = hardware.start_camera_if_enabled()
    
    # Start the 2D speaking avatar of Amir Temur
    import amir_temur_avatar
    import atexit
    amir_temur_avatar.start_avatar()
    atexit.register(amir_temur_avatar.stop_avatar)

    mic_idx, mic_rate = hardware.get_optimal_microphone()
    recognizer = sr.Recognizer()
    configure_recognizer(recognizer, cfg, vcfg)

    try:
        mic = hardware.create_microphone(mic_idx, mic_rate)
    except Exception as e:
        print(f"[XATO] Mikrofon ishga tushmadi: {e}")
        return

    print("[SYSTEM] Mikrofon kalibrlashmoqda...")
    calibrate_once(recognizer, mic, cfg)

    arm_worker = ArmCommandWorker(cfg)
    arm_worker.start()
    import atexit
    atexit.register(arm_worker.stop)

    print("[READY] Suhbatga tayyor. Ctrl+C bilan chiqasiz.\n")
    print(f"[TTS] Ovoz: {EDGE_TTS_VOICE} | rate={EDGE_TTS_RATE}, pitch={EDGE_TTS_PITCH}, volume={EDGE_TTS_VOLUME}")

    speak_with_greeting_motion(GREETING_TEXT, cfg, vcfg)

    # Determine mic device index for interrupt listener
    _interrupt_mic_idx = vcfg.mic_device_index if vcfg.mic_device_index is not None else mic_idx

    while True:
        try:
            handle_face_greeting_events(cfg, vcfg)
            user_text = listen(recognizer, mic, cfg)
            if not user_text:
                handle_face_greeting_events(cfg, vcfg)
                continue

            text_lower = user_text.lower().strip()
            is_goodbye = any(soz in text_lower for soz in XAYRLASHISH)

            # think() handles: stop-words, movement commands, greetings,
            # date/time, and AI fallback — in that priority order.
            ai_response = think(user_text, cfg, vcfg)
            if ai_response is None:
                # Stop/cancel intent — skip TTS
                continue

            # ── Movement command response ─────────────────────────────────
            if isinstance(ai_response, dict) and "movements" in ai_response:
                speech_text = ai_response.get("speech", "")
                movements = ai_response.get("movements", [])
                print(f"[MOVEMENT] Executing {len(movements)} steps.")
                _il = InterruptListener(vcfg, STT_LANGUAGE, _interrupt_mic_idx)
                _il.start()
                # Capture movements in closure correctly
                _steps_to_run = list(movements)
                _ctrl = hardware.get_esp32_controller()
                def _run_movements(_steps=_steps_to_run, _c=_ctrl):
                    execute_movement_steps(_steps, _c)
                _mv_thread = threading.Thread(
                    target=_run_movements, daemon=True, name="movement-exec")
                _mv_thread.start()
                if speech_text:
                    tts_timer = LatencyTimer("tts_playback_complete", cfg)
                    tts_timer.start()
                    run_speak(speech_text, cfg, vcfg)
                    tts_timer.stop()
                _mv_thread.join(timeout=10.0)
                _il.stop()
                turn_cooldown(cfg)
                if is_goodbye:
                    print("\n[STOP] Dastur to'xtatildi.")
                    break
                continue

            # ── Plain text AI response ────────────────────────────────────
            _il = InterruptListener(vcfg, STT_LANGUAGE, _interrupt_mic_idx)
            _il.start()

            if is_greeting_text(user_text):
                speak_with_greeting_motion(ai_response, cfg, vcfg)
            else:
                tts_timer = LatencyTimer("tts_playback_complete", cfg)
                tts_timer.start()
                run_speak(ai_response, cfg, vcfg)
                tts_timer.stop()

            _il.stop()

            if is_goodbye:
                print("\n[STOP] Dastur to'xtatildi.")
                break

            turn_cooldown(cfg)

        except KeyboardInterrupt:
            farewell = "Tanishganimdan xursandman. Suhbat uchun rahmat."
            print(f"[AI] {farewell}")
            run_speak(farewell, cfg, vcfg)
            arm_worker.stop()
            close_tts_loop()
            print("[STOP] Dastur to'xtatildi.")
            break

        except Exception as e:
            print(f"\n[XATO] Kutilmagan xato: {e}")
            await asyncio.sleep(2)  # await qo'shildi


if __name__ == "__main__":
    asyncio.run(main())  # main funksiyasini asyncio.run bilan ishga tushirdim