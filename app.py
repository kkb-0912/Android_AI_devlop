# -*- coding: utf-8 -*-
"""
AI 비서 (하이브리드) — Flask 백엔드
=======================================
- 규칙 기반 명령(시간/날짜/위키백과/앱 실행/스크린샷/음악/시스템 제어)은 즉시 로컬에서 처리
- 그 외 자유 대화는 Claude API로 전달해 응답
- 노트북에서 서버를 띄우고, 같은 브라우저(웹) UI를 노트북/안드로이드(같은 Wi-Fi) 양쪽에서 그대로 사용
- 시스템 제어(스크린샷/앱 실행/음악 재생/종료·재시작)는 "이 노트북"에서 접속했을 때만 허용됨(보안)

이 파일 하나로 백엔드 전체를 구성한다. 프론트엔드는 templates/index.html + static/app.js.
"""

import datetime
import json
import os
import re
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request

try:
    import requests
except ImportError:
    requests = None

try:
    import wikipedia
except ImportError:
    wikipedia = None

try:
    import pyjokes
except ImportError:
    pyjokes = None

try:
    import pyautogui
except Exception:
    # 리눅스 서버(디스플레이 없음) 등에서는 pyautogui import 자체가 실패할 수 있음
    pyautogui = None

try:
    from langdetect import DetectorFactory, detect

    DetectorFactory.seed = 0  # 결과를 일정하게 만듦
except ImportError:
    detect = None


# ───────────────────────────────────────────────
#  경로 / 설정
# ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "api_key": "",
    "assistant_name": "나만의 AI 비서",
    "system_prompt": "",  # 비어 있으면 DEFAULT_SYSTEM_PROMPT 사용
    "port": 5050,
    "claude_model": "claude-sonnet-5",
}

# 역할 모드를 따로 두지 않고, 하나의 인격이 대화 맥락에 맞춰 알아서
# 업무/학습/창작/감정 케어/일상 대화 사이를 자연스럽게 넘나들도록 설계.
DEFAULT_SYSTEM_PROMPT = (
    "당신은 사용자의 개인 AI 비서입니다. 고정된 역할 모드 없이, 매 순간 사용자의 요청과 "
    "말투에서 필요한 태도를 스스로 파악해서 자연스럽게 대응하세요.\n"
    "- 업무 요청(이메일, 일정, 문서 요약, 전략 등)이면 전문적이고 간결하게.\n"
    "- 학습/개념 질문이면 쉬운 말과 예시로 차근차근.\n"
    "- 창작 요청(글쓰기, 아이디어, 카피 등)이면 풍부한 표현으로 자유롭게.\n"
    "- 힘든 감정이나 고민을 이야기하면 조언보다 공감을 먼저, 조언은 요청할 때만.\n"
    "- 그 외 일상 대화는 친근하고 따뜻하게.\n"
    "사용자가 모드를 명시하지 않아도 대화 흐름을 보고 알아서 톤과 접근 방식을 바꾸세요. "
    "여러 성격이 섞인 요청이면 자연스럽게 함께 반영하면 됩니다."
)

LANGUAGE_RULE = (
    "\n\n[언어 규칙] 사용자가 방금 보낸 메시지와 같은 언어로만 답하세요. "
    "한국어로 물으면 한국어로, 영어로 물으면 영어로 답합니다. 다른 언어가 섞여 있으면 "
    "가장 비중이 큰 언어를 기준으로 답하세요."
)

# 세션(접속자)별 대화 기록 / 확인 대기 상태 — 서버 메모리에만 저장 (재시작하면 초기화)
_HISTORY = {}       # {client_key: [{"role":..,"content":..}, ...]}
_PENDING = {}       # {client_key: {"action": "shutdown"/"restart", "expires": ts}}
MAX_HISTORY_TURNS = 20
CONFIRM_TIMEOUT_SEC = 25


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_system_prompt(cfg):
    base = cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    name = cfg.get("assistant_name", "AI 비서")
    return f"당신의 이름은 '{name}' 입니다. {base}{LANGUAGE_RULE}"


def detect_lang(text, hint="ko"):
    """text의 언어를 감지. 실패하거나 너무 짧으면 hint(브라우저 인식 언어)로 대체."""
    if not text or len(text.strip()) < 2:
        return hint
    if detect is None:
        # 아주 단순한 휴리스틱: 한글 포함 여부
        return "ko" if re.search(r"[가-힣]", text) else "en"
    try:
        lang = detect(text)
        return "ko" if lang == "ko" else ("en" if lang == "en" else lang)
    except Exception:
        return hint


def get_lan_ip():
    """안드로이드 폰에서 접속할 때 안내할 이 노트북의 LAN IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def is_local_request(req):
    """이 노트북 자신에게서 온 요청인지(=localhost) 확인. 시스템 제어 명령은 이 경우에만 허용."""
    remote = req.remote_addr or ""
    return remote in ("127.0.0.1", "::1", "localhost")


# ───────────────────────────────────────────────
#  Claude API 호출
# ───────────────────────────────────────────────
def call_claude(api_key, model, system_prompt, history):
    if requests is None:
        raise RuntimeError("requests 패키지가 설치되어 있지 않습니다. `pip install requests`")

    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": history,
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            err = resp.text
        raise RuntimeError(f"API 오류 ({resp.status_code}): {err}")
    data = resp.json()
    return data["content"][0]["text"]


# ───────────────────────────────────────────────
#  규칙 기반 명령(의도) 처리
#  반환값: None(해당 없음, Claude로 넘어감) 또는
#          {"kind": "text", "text": "...", "lang": "ko"} 또는
#          {"kind": "action", "action": "open_url", "url": "...", "text": "...", "lang": "ko"}
# ───────────────────────────────────────────────
LOCAL_ONLY_MSG = {
    "ko": "이 명령은 이 노트북에서 직접 실행할 때만 가능해요. 노트북 창에서 다시 말씀해주세요.",
    "en": "This command only works when you're using the assistant directly on this laptop.",
}


def _t(lang, ko, en):
    return ko if lang != "en" else en


def handle_command(text, lang, is_local, client_key):
    q = text.strip()
    ql = q.lower()

    # ── 시스템 제어 확인 대기 처리(최우선) ─────────────
    pending = _PENDING.get(client_key)
    if pending and pending["expires"] > time.time():
        yes = ql in ("네", "응", "yes", "y", "확인", "맞아", "그래", "ok", "okay")
        no = ql in ("아니", "아니요", "no", "n", "취소", "cancel")
        if yes or no:
            del _PENDING[client_key]
            if no:
                return {"kind": "text", "text": _t(lang, "취소했어요.", "Cancelled."), "lang": lang}
            action = pending["action"]
            if not is_local:
                return {"kind": "text", "text": LOCAL_ONLY_MSG[lang if lang in LOCAL_ONLY_MSG else "ko"], "lang": lang}
            if action == "shutdown":
                subprocess.Popen(["shutdown", "/s", "/f", "/t", "3"] if os.name == "nt" else ["shutdown", "-h", "now"])
                return {"kind": "text", "text": _t(lang, "네, 컴퓨터를 종료할게요. 안녕히 가세요!", "Shutting down. Goodbye!"), "lang": lang}
            if action == "restart":
                subprocess.Popen(["shutdown", "/r", "/f", "/t", "3"] if os.name == "nt" else ["shutdown", "-r", "now"])
                return {"kind": "text", "text": _t(lang, "네, 컴퓨터를 재시작할게요.", "Restarting now."), "lang": lang}
        # 대기 중인데 네/아니오가 아니면 대기를 취소하고 일반 처리로 진행
        del _PENDING[client_key]

    # ── 시간 ──
    if re.search(r"(지금\s*몇\s*시|현재\s*시간|몇\s*시(야|예요|입니까)?\b)", q) or re.search(r"\bwhat.?s?\s+(the\s+)?time\b|\bcurrent time\b|\btime\s+is\s+it\b", ql):
        now = datetime.datetime.now().strftime("%H:%M:%S") if lang == "en" else datetime.datetime.now().strftime("%p %I시 %M분").replace("AM", "오전").replace("PM", "오후")
        return {"kind": "text", "text": _t(lang, f"지금은 {now} 예요.", f"It's currently {now}."), "lang": lang}

    # ── 날짜 ──
    if re.search(r"(오늘\s*날짜|며칠|무슨\s*요일)", q) or re.search(r"\bwhat.?s?\s+(today.?s\s+)?date\b|\btoday.?s date\b|\bdate\s+is\s+it\b", ql):
        now = datetime.datetime.now()
        weekdays_ko = ["월", "화", "수", "목", "금", "토", "일"]
        if lang == "en":
            txt = now.strftime("%A, %B %d, %Y")
        else:
            txt = f"{now.year}년 {now.month}월 {now.day}일 {weekdays_ko[now.weekday()]}요일"
        return {"kind": "text", "text": _t(lang, f"오늘은 {txt} 이에요.", f"Today is {txt}."), "lang": lang}

    # ── 농담 ──
    if re.search(r"(농담|재밌는\s*얘기|웃긴)", q) or "joke" in ql:
        jokes_ko = [
            "개발자가 제일 좋아하는 계절은? 겨울! 버그(bug)가 겨울잠을 자거든요.",
            "컴퓨터가 감기에 걸리면? 바이러스에 걸렸다고 하죠.",
            "왜 프로그래머들은 안경을 쓸까요? C#을 보기 위해서요.",
        ]
        if lang == "en" and pyjokes is not None:
            try:
                return {"kind": "text", "text": pyjokes.get_joke(), "lang": lang}
            except Exception:
                pass
        import random

        return {"kind": "text", "text": random.choice(jokes_ko), "lang": lang}

    # ── 위키백과 ──
    m = re.search(r"위키(백과)?(에서)?\s*(.+?)\s*(찾아줘|검색해줘|알려줘|검색|찾아|알려)?$", q)
    m2 = re.search(r"wikipedia\s+(.+)", ql)
    topic = None
    if m and m.group(3):
        topic = m.group(3).strip()
    elif m2:
        topic = m2.group(1).strip()
    if topic:
        if wikipedia is None:
            return {"kind": "text", "text": _t(lang, "위키백과 검색 기능을 쓰려면 `pip install wikipedia`가 필요해요.", "Wikipedia search needs `pip install wikipedia`."), "lang": lang}
        try:
            wikipedia.set_lang("ko" if lang != "en" else "en")
            summary = wikipedia.summary(topic, sentences=2, auto_suggest=True)
            return {"kind": "text", "text": summary, "lang": lang}
        except Exception:
            try:
                wikipedia.set_lang("en")
                summary = wikipedia.summary(topic, sentences=2, auto_suggest=True)
                return {"kind": "text", "text": summary, "lang": lang}
            except Exception:
                return {"kind": "text", "text": _t(lang, f"'{topic}'에 대한 위키백과 검색 결과를 찾지 못했어요.", f"I couldn't find a Wikipedia result for '{topic}'."), "lang": lang}

    # ── 웹사이트 열기 / 구글·유튜브 검색 (클라이언트가 자신의 브라우저에서 열도록 URL만 전달) ──
    if re.search(r"(유튜브)\s*(열어|틀어|켜)", q) or "open youtube" in ql:
        return {"kind": "action", "action": "open_url", "url": "https://www.youtube.com", "text": _t(lang, "유튜브를 열게요.", "Opening YouTube."), "lang": lang}
    if re.search(r"(구글|google)\s*(열어|켜)", q) or ql.strip() in ("open google",):
        return {"kind": "action", "action": "open_url", "url": "https://www.google.com", "text": _t(lang, "구글을 열게요.", "Opening Google."), "lang": lang}
    m = re.search(r"(구글|google)(에서)?\s*(.+?)\s*(검색해줘|검색|찾아줘|search)$", q, re.IGNORECASE)
    if m:
        query = m.group(3).strip()
        url = "https://www.google.com/search?q=" + requests.utils.quote(query) if requests else "https://www.google.com/search?q=" + query.replace(" ", "+")
        return {"kind": "action", "action": "open_url", "url": url, "text": _t(lang, f"'{query}' 구글 검색 결과를 열게요.", f"Opening Google search for '{query}'."), "lang": lang}

    # ── 스크린샷 (이 노트북 전용) ──
    if re.search(r"스크린샷|화면\s*캡처", q) or "screenshot" in ql:
        if not is_local:
            return {"kind": "text", "text": LOCAL_ONLY_MSG[lang if lang in LOCAL_ONLY_MSG else "ko"], "lang": lang}
        if pyautogui is None:
            return {"kind": "text", "text": _t(lang, "스크린샷 기능을 쓰려면 `pip install pyautogui`가 필요해요.", "Screenshot needs `pip install pyautogui`."), "lang": lang}
        try:
            pictures_dir = Path.home() / "Pictures"
            pictures_dir.mkdir(parents=True, exist_ok=True)
            fname = pictures_dir / f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            img = pyautogui.screenshot()
            img.save(fname)
            return {"kind": "text", "text": _t(lang, f"스크린샷을 저장했어요: {fname}", f"Screenshot saved: {fname}"), "lang": lang}
        except Exception as e:
            return {"kind": "text", "text": _t(lang, f"스크린샷 저장에 실패했어요: {e}", f"Failed to save screenshot: {e}"), "lang": lang}

    # ── 앱 실행 (이 노트북 전용, 화이트리스트) ──
    m = re.search(r"(계산기|메모장|탐색기|크롬|엣지|notepad|calculator|explorer|chrome|edge)\s*(실행|열어|켜)?", ql)
    APP_MAP = {
        "계산기": "calc", "calculator": "calc",
        "메모장": "notepad", "notepad": "notepad",
        "탐색기": "explorer", "explorer": "explorer",
        "크롬": "chrome", "chrome": "chrome",
        "엣지": "msedge", "edge": "msedge",
    }
    if m and (re.search(r"(실행|열어|켜)", q) or "open" in ql):
        key = m.group(1)
        cmd = APP_MAP.get(key)
        if cmd:
            if not is_local:
                return {"kind": "text", "text": LOCAL_ONLY_MSG[lang if lang in LOCAL_ONLY_MSG else "ko"], "lang": lang}
            try:
                if os.name == "nt":
                    os.startfile(cmd) if cmd in ("calc", "notepad", "explorer") else subprocess.Popen([cmd])
                else:
                    subprocess.Popen([cmd])
                return {"kind": "text", "text": _t(lang, f"{key}을(를) 실행할게요.", f"Opening {key}."), "lang": lang}
            except Exception as e:
                return {"kind": "text", "text": _t(lang, f"{key} 실행에 실패했어요: {e}", f"Failed to open {key}: {e}"), "lang": lang}

    # ── 음악 재생 (이 노트북 전용) ──
    if re.search(r"음악\s*(틀어|재생)", q) or "play music" in ql:
        if not is_local:
            return {"kind": "text", "text": LOCAL_ONLY_MSG[lang if lang in LOCAL_ONLY_MSG else "ko"], "lang": lang}
        music_dir = Path.home() / "Music"
        try:
            songs = [f for f in music_dir.iterdir() if f.suffix.lower() in (".mp3", ".wav", ".m4a", ".flac")]
        except Exception:
            songs = []
        if not songs:
            return {"kind": "text", "text": _t(lang, "Music 폴더에서 재생할 곡을 찾지 못했어요.", "No songs found in your Music folder."), "lang": lang}
        import random

        song = random.choice(songs)
        try:
            if os.name == "nt":
                os.startfile(song)
            else:
                subprocess.Popen(["xdg-open", str(song)])
            return {"kind": "text", "text": _t(lang, f"'{song.name}'을(를) 재생할게요.", f"Playing '{song.name}'."), "lang": lang}
        except Exception as e:
            return {"kind": "text", "text": _t(lang, f"재생 실패: {e}", f"Playback failed: {e}"), "lang": lang}

    # ── 종료 / 재시작 (확인 필요) ──
    if re.search(r"(컴퓨터|노트북|시스템)?\s*(종료|꺼줘|shutdown)", q) and not re.search(r"대화|채팅|chat", q):
        if not is_local:
            return {"kind": "text", "text": LOCAL_ONLY_MSG[lang if lang in LOCAL_ONLY_MSG else "ko"], "lang": lang}
        _PENDING[client_key] = {"action": "shutdown", "expires": time.time() + CONFIRM_TIMEOUT_SEC}
        return {"kind": "text", "text": _t(lang, "정말 컴퓨터를 종료할까요? '네'라고 답해주세요. (25초 이내)", "Really shut down the computer? Reply 'yes' within 25 seconds."), "lang": lang}
    if re.search(r"(컴퓨터|노트북|시스템)?\s*(재시작|restart)", q):
        if not is_local:
            return {"kind": "text", "text": LOCAL_ONLY_MSG[lang if lang in LOCAL_ONLY_MSG else "ko"], "lang": lang}
        _PENDING[client_key] = {"action": "restart", "expires": time.time() + CONFIRM_TIMEOUT_SEC}
        return {"kind": "text", "text": _t(lang, "정말 컴퓨터를 재시작할까요? '네'라고 답해주세요. (25초 이내)", "Really restart the computer? Reply 'yes' within 25 seconds."), "lang": lang}

    # ── 대화 초기화 ──
    if re.search(r"(대화\s*초기화|채팅\s*지워)", q) or "clear chat" in ql:
        _HISTORY[client_key] = []
        return {"kind": "text", "text": _t(lang, "대화 기록을 초기화했어요.", "Chat history cleared."), "lang": lang}

    return None  # Claude로 위임


# ───────────────────────────────────────────────
#  Flask 앱
# ───────────────────────────────────────────────
app = Flask(__name__)


@app.route("/")
def index():
    cfg = load_config()
    safe_cfg = {k: v for k, v in cfg.items() if k != "api_key"}
    safe_cfg["has_api_key"] = bool(cfg.get("api_key"))
    safe_cfg["lan_url"] = f"http://{get_lan_ip()}:{cfg.get('port', 5050)}"
    return render_template("index.html", cfg=safe_cfg)


@app.route("/api/health")
def health():
    cfg = load_config()
    return jsonify({"ok": True, "lan_ip": get_lan_ip(), "port": cfg.get("port", 5050)})


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    cfg = load_config()
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        for key in ("api_key", "assistant_name", "system_prompt"):
            if key in data:
                cfg[key] = data[key]
        save_config(cfg)
        return jsonify({"ok": True})
    safe_cfg = {k: v for k, v in cfg.items() if k != "api_key"}
    safe_cfg["has_api_key"] = bool(cfg.get("api_key"))
    return jsonify(safe_cfg)


@app.route("/api/command", methods=["POST"])
def command():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    lang_hint = data.get("lang_hint", "ko")
    if not text:
        return jsonify({"kind": "text", "text": "", "lang": lang_hint})

    client_key = request.remote_addr or "unknown"
    is_local = is_local_request(request)
    lang = detect_lang(text, hint=lang_hint)

    # 1) 규칙 기반 처리 먼저 시도
    result = handle_command(text, lang, is_local, client_key)
    if result is not None:
        return jsonify(result)

    # 2) 자유 대화 -> Claude API
    cfg = load_config()
    if not cfg.get("api_key"):
        return jsonify({
            "kind": "text",
            "lang": lang,
            "text": _t(lang, "⚙️ 설정에서 Anthropic API 키를 먼저 입력해주세요. (자유 대화를 하려면 필요해요)",
                       "⚙️ Please set your Anthropic API key in Settings first (needed for free conversation)."),
        })

    history = _HISTORY.setdefault(client_key, [])
    history.append({"role": "user", "content": text})
    history[:] = history[-MAX_HISTORY_TURNS * 2:]

    try:
        system_prompt = get_system_prompt(cfg)
        reply = call_claude(cfg["api_key"], cfg.get("claude_model", "claude-sonnet-5"), system_prompt, history)
        history.append({"role": "assistant", "content": reply})
        return jsonify({"kind": "text", "text": reply, "lang": lang})
    except Exception as e:
        history.pop()  # 실패한 사용자 턴 되돌리기
        return jsonify({"kind": "text", "text": _t(lang, f"⚠️ 오류: {e}", f"⚠️ Error: {e}"), "lang": lang})


def create_default_config_if_missing():
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG.copy())


def run_server(open_browser=False):
    create_default_config_if_missing()
    cfg = load_config()
    port = cfg.get("port", 5050)
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    import threading

    run_server(open_browser=True)
