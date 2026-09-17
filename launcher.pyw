# -*- coding: utf-8 -*-
"""
launcher.pyw — 부팅 시 실행되는 진입점.
- Flask 서버를 백그라운드 스레드로 띄우고
- pywebview로 "팝업창" 형태의 네이티브 창을 연다 (설치 안 돼 있으면 기본 브라우저로 대체)

더블클릭 실행: pythonw launcher.pyw
자동 시작 등록: setup_autostart.bat 실행
"""

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import app as backend  # noqa: E402


def wait_for_server(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main():
    backend.create_default_config_if_missing()
    cfg = backend.load_config()
    port = cfg.get("port", 5050)
    name = cfg.get("assistant_name", "AI 비서")

    server_thread = threading.Thread(
        target=lambda: backend.app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False),
        daemon=True,
    )
    server_thread.start()

    wait_for_server(port)
    url = f"http://127.0.0.1:{port}"

    try:
        import webview  # pywebview

        window = webview.create_window(name, url, width=420, height=700, resizable=True, min_size=(360, 480))
        webview.start()
    except Exception:
        # pywebview가 없거나 실패하면 기본 브라우저 새 창으로 대체
        webbrowser.open(url)
        # 브라우저로 실행한 경우, 서버가 계속 떠 있도록 메인 스레드를 유지
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
