import os
import threading
import time
import urllib.request

import webview

import hub_server


def _wait_for_server(url: str) -> None:
    status_url = f"{url}/api/status"
    for _ in range(50):
        try:
            urllib.request.urlopen(status_url, timeout=1.0)
            return
        except Exception:
            time.sleep(0.25)


def main() -> None:
    port = int(os.environ.get("AI_HUB_PORT", "7860"))
    url = f"http://127.0.0.1:{port}"

    server_thread = threading.Thread(target=hub_server.main, daemon=True)
    server_thread.start()

    _wait_for_server(url)

    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.create_window(
        "TTRPG AI Hub",
        url,
        width=1440,
        height=920,
        min_size=(1024, 700),
    )
    webview.start()


if __name__ == "__main__":
    main()
