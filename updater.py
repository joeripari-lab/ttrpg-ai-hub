"""
In-app updater for TTRPG AI Hub.
- Installed (frozen) mode: checks GitHub Releases for a newer TTRPG_AI_Hub_Setup.exe,
  downloads it to %TEMP%, launches silent Inno Setup upgrade, and exits cleanly.
- Source (dev) mode: also supports checking/pulling the current git branch.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

APP_VERSION = "1.0.0"
GITHUB_REPO = "joeripari-lab/ttrpg-ai-hub"
INSTALLER_ASSET_PREFIX = "TTRPG_AI_Hub_Setup"


def _parse_version(ver: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", ver or "")
    return tuple(int(n) for n in nums) if nums else (0,)


def _github_headers(token: str = "", accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": f"TTRPG-AI-Hub/{APP_VERSION}",
    }
    if token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


def check_for_updates(github_token: str = "") -> dict:
    is_frozen = getattr(sys, "frozen", False)
    repo_root = Path(__file__).resolve().parent
    has_git = (not is_frozen) and (repo_root / ".git").exists()

    result = {
        "ok": True,
        "current_version": APP_VERSION,
        "repo": GITHUB_REPO,
        "is_frozen": is_frozen,
        "has_git": has_git,
        "update_available": False,
        "latest_version": APP_VERSION,
        "release_name": "",
        "release_notes": "",
        "download_url": "",
        "asset_name": "",
        "html_url": f"https://github.com/{GITHUB_REPO}/releases",
        "error": "",
    }

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    req = urllib.request.Request(api_url, headers=_github_headers(github_token))
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            result["error"] = (
                "No GitHub Release found yet (or repository is private — add a GitHub Token below if private)."
            )
        elif e.code in (401, 403):
            result["error"] = f"GitHub API auth/rate-limit error (HTTP {e.code}). Check your GitHub Token."
        else:
            result["error"] = f"GitHub API error (HTTP {e.code})."
        return result
    except Exception as e:
        result["error"] = f"Could not reach GitHub: {e}"
        return result

    tag = (data.get("tag_name") or "").strip()
    latest = tag.lstrip("vV") or APP_VERSION
    result["latest_version"] = latest
    result["release_name"] = data.get("name") or tag
    result["release_notes"] = (data.get("body") or "").strip()
    result["html_url"] = data.get("html_url") or result["html_url"]

    assets = data.get("assets") or []
    chosen = None
    for a in assets:
        name = a.get("name") or ""
        if name.lower().endswith(".exe") and INSTALLER_ASSET_PREFIX.lower() in name.lower():
            chosen = a
            break
    if not chosen:
        for a in assets:
            if (a.get("name") or "").lower().endswith(".exe"):
                chosen = a
                break

    if chosen:
        result["asset_name"] = chosen.get("name") or "TTRPG_AI_Hub_Setup.exe"
        # Use API asset URL when token is provided (required for private repos), else browser_download_url
        result["download_url"] = (
            chosen.get("url") if github_token.strip() else chosen.get("browser_download_url")
        ) or chosen.get("browser_download_url") or ""

    if _parse_version(latest) > _parse_version(APP_VERSION):
        result["update_available"] = True

    return result


def download_and_apply_update(download_url: str, asset_name: str = "TTRPG_AI_Hub_Setup.exe", github_token: str = "") -> dict:
    if not download_url:
        return {"ok": False, "error": "No installer download URL found in the latest release."}

    safe_name = os.path.basename(asset_name) or "TTRPG_AI_Hub_Setup.exe"
    if not safe_name.lower().endswith(".exe"):
        safe_name += ".exe"

    upd_dir = Path(tempfile.gettempdir()) / "TTRPG_AI_Hub_Update"
    upd_dir.mkdir(parents=True, exist_ok=True)
    dest = upd_dir / safe_name

    accept = "application/octet-stream" if "api.github.com" in download_url else "*/*"
    req = urllib.request.Request(download_url, headers=_github_headers(github_token, accept=accept))
    try:
        with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        return {"ok": False, "error": f"Failed to download update: {e}"}

    if not dest.exists() or dest.stat().st_size < 100_000:
        return {"ok": False, "error": "Downloaded installer file is invalid or incomplete."}

    # Launch silent Inno Setup upgrade after short delay, then exit current process so files aren't locked
    cmd_str = (
        f'ping -n 2 127.0.0.1 >nul && '
        f'start "" "{dest}" /SILENT /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS'
    )
    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    subprocess.Popen(
        ["cmd.exe", "/c", cmd_str],
        creationflags=creationflags,
        close_fds=True,
    )

    threading.Timer(0.6, lambda: os._exit(0)).start()
    return {
        "ok": True,
        "restarting": True,
        "installer_path": str(dest),
        "message": f"Downloaded {safe_name}. Installing update and restarting...",
    }


def git_pull_update() -> dict:
    repo_root = Path(__file__).resolve().parent
    if not (repo_root / ".git").exists():
        return {"ok": False, "error": "Not a git source checkout."}
    try:
        proc = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (proc.stdout + "\n" + proc.stderr).strip()
        if proc.returncode != 0:
            return {"ok": False, "error": out or "git pull failed"}
        return {"ok": True, "output": out, "updated": "Already up to date." not in out}
    except Exception as e:
        return {"ok": False, "error": str(e)}
