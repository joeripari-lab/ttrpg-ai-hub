import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

_PULL_LOCK = threading.Lock()
_PULL_STATE: Dict[str, Any] = {
    "pulling": False,
    "model": "",
    "status": "",
    "percent": 0,
    "error": "",
}


def _http_get_json(url: str, timeout: float = 4.0, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(url: str, payload: Dict[str, Any], timeout: float = 180.0, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err_body[:400]}") from e


# ============================================================================
# OLLAMA STATUS & MODEL PULL (FOR SETUP WIZARD)
# ============================================================================
def check_ollama_status(ollama_url: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
    base = ollama_url.rstrip("/").removesuffix("/v1")
    try:
        res = _http_get_json(f"{base}/api/tags", timeout=2.0)
        models = [m.get("name") for m in res.get("models", []) if m.get("name")]
        return {"online": True, "models": models, "pull": dict(_PULL_STATE)}
    except Exception:
        return {"online": False, "models": [], "pull": dict(_PULL_STATE)}


def pull_ollama_model_bg(model_name: str = "qwen2.5:7b", ollama_url: str = "http://127.0.0.1:11434") -> bool:
    if _PULL_STATE["pulling"]:
        return False
    base = ollama_url.rstrip("/").removesuffix("/v1")

    def _run():
        if not _PULL_LOCK.acquire(blocking=False):
            return
        _PULL_STATE.update({"pulling": True, "model": model_name, "status": "Starting pull...", "percent": 0, "error": ""})
        try:
            req = urllib.request.Request(
                f"{base}/api/pull",
                data=json.dumps({"name": model_name, "stream": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3600) as resp:
                for raw_line in resp:
                    if not raw_line.strip():
                        continue
                    try:
                        obj = json.loads(raw_line.decode("utf-8"))
                        _PULL_STATE["status"] = obj.get("status", "Downloading...")
                        tot = obj.get("total") or 0
                        comp = obj.get("completed") or 0
                        if tot > 0:
                            _PULL_STATE["percent"] = min(100, int((comp / tot) * 100))
                    except Exception:
                        pass
            _PULL_STATE["status"] = f"Ready ({model_name})"
            _PULL_STATE["percent"] = 100
        except Exception as e:
            _PULL_STATE["error"] = str(e)
            _PULL_STATE["status"] = f"Failed: {e}"
        finally:
            _PULL_STATE["pulling"] = False
            _PULL_LOCK.release()

    threading.Thread(target=_run, daemon=True).start()
    return True


# ============================================================================
# CLOUD TEXT / VISION PROVIDERS (OPENAI, CLAUDE, GEMINI)
# ============================================================================
def _split_openai_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return messages


def call_openai_api(messages: List[Dict[str, Any]], api_key: str, model: str = "gpt-4o-mini", temperature: float = 0.7, max_tokens: int = 1600) -> str:
    payload = {
        "model": model or "gpt-4o-mini",
        "messages": _split_openai_messages(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = _http_post_json(
        "https://api.openai.com/v1/chat/completions",
        payload,
        timeout=120,
        headers={"Authorization": f"Bearer {api_key.strip()}"},
    )
    return resp["choices"][0]["message"]["content"]


def call_anthropic_api(messages: List[Dict[str, Any]], api_key: str, model: str = "claude-sonnet-4-5", temperature: float = 0.7, max_tokens: int = 1600) -> str:
    sys_parts: List[str] = []
    conv_msgs: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            if isinstance(content, str):
                sys_parts.append(content)
            continue
        if isinstance(content, str):
            conv_msgs.append({"role": "assistant" if role == "assistant" else "user", "content": content})
        elif isinstance(content, list):
            blocks = []
            for item in content:
                if item.get("type") == "text":
                    blocks.append({"type": "text", "text": item.get("text", "")})
                elif item.get("type") == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    if url.startswith("data:") and ";base64," in url:
                        hdr, b64 = url.split(";base64,", 1)
                        mime = hdr.replace("data:", "") or "image/jpeg"
                        blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
            conv_msgs.append({"role": "assistant" if role == "assistant" else "user", "content": blocks})

    payload: Dict[str, Any] = {
        "model": model or "claude-sonnet-4-5",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": conv_msgs or [{"role": "user", "content": "Hello"}],
    }
    if sys_parts:
        payload["system"] = "\n\n".join(sys_parts)

    resp = _http_post_json(
        "https://api.anthropic.com/v1/messages",
        payload,
        timeout=120,
        headers={
            "x-api-key": api_key.strip(),
            "anthropic-version": "2023-06-01",
        },
    )
    texts = [b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text"]
    return "\n".join(texts).strip()


# ============================================================================
# CLOUD IMAGE GENERATION FALLBACK (OPENAI / GEMINI IMAGEN)
# ============================================================================
def generate_cloud_image(prompt: str, cfg: Dict[str, Any], output_dir: Path, size: str = "1024x1024") -> Dict[str, Any]:
    pref = cfg.get("cloud_image_provider", "auto")
    openai_key = (cfg.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")).strip()
    gemini_key = (cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")).strip()

    if openai_key and pref in ("auto", "openai"):
        allowed_sizes = {"1024x1024", "1024x1536", "1536x1024"}
        img_size = size if size in allowed_sizes else "1024x1024"
        resp = _http_post_json(
            "https://api.openai.com/v1/images/generations",
            {"model": "gpt-image-1", "prompt": prompt, "n": 1, "size": img_size},
            timeout=120,
            headers={"Authorization": f"Bearer {openai_key}"},
        )
        b64 = resp["data"][0].get("b64_json")
        if b64:
            fname = f"cloud_openai_{int(time.time())}.png"
            (output_dir / fname).write_bytes(base64.b64decode(b64))
            return {"images": [f"/outputs/images/{fname}"], "seed": 0, "provider": "OpenAI (gpt-image-1)"}

    if gemini_key and pref in ("auto", "gemini"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={gemini_key}"
        resp = _http_post_json(
            url,
            {"instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1}},
            timeout=120,
        )
        preds = resp.get("predictions") or []
        if preds and preds[0].get("bytesBase64Encoded"):
            fname = f"cloud_imagen_{int(time.time())}.png"
            (output_dir / fname).write_bytes(base64.b64decode(preds[0]["bytesBase64Encoded"]))
            return {"images": [f"/outputs/images/{fname}"], "seed": 0, "provider": "Google Imagen 3"}

    raise RuntimeError("No Cloud Image API key configured (add an OpenAI or Gemini API key in Settings or Setup Wizard).")
