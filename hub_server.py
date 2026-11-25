#!/usr/bin/env python3
"""
Unified Local AI Hub & TTRPG Character Studio
---------------------------------------------
1. Local TTRPG Character Portrait Studio (ComfyUI + SDXL)
2. Local Vision & Chat Agent (LM Studio Qwen2.5-VL-7B / Ollama / Gemini)
3. Dungeon Crawler World (DCC) Session 0 Character Sheet & Journal PDF Builder
"""

import os
import sys
import json
import time
import uuid
import base64
import shutil
import random
import urllib.request
import urllib.parse
import urllib.error
import subprocess
import threading
import mimetypes
from pathlib import Path
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import app_paths
import llm_router
import dcc_engine
import sw5e_engine
import dnd5e_engine
import rules_rag
import campaign_dcc
import campaign_rulesets
import campaign_engine

# ============================================================================
# PATHS & CONFIGURATION
# ============================================================================
BASE_DIR = app_paths.DATA_DIR
COMFY_ROOT = app_paths.resolve_comfy_root()
COMFY_PYTHON = COMFY_ROOT / "python_embeded" / "python.exe"
COMFY_MAIN = COMFY_ROOT / "ComfyUI" / "main.py"
COMFY_CHECKPOINTS = COMFY_ROOT / "ComfyUI" / "models" / "checkpoints"
COMFY_LORAS = COMFY_ROOT / "ComfyUI" / "models" / "loras"
COMFY_INPUT = COMFY_ROOT / "ComfyUI" / "input"
COMFY_OUTPUT = COMFY_ROOT / "ComfyUI" / "output"

LMSTUDIO_CLI = Path(os.path.expanduser(r"~\.lmstudio\bin\lms.exe"))
LMSTUDIO_MODELS = Path(os.path.expanduser(r"~\.lmstudio\models"))

OUTPUT_IMAGES_DIR = BASE_DIR / "outputs" / "images"
STUDIO_SKILLS_DIR = BASE_DIR / "studio_skills"
CONFIG_PATH = BASE_DIR / "config.json"
LEARNED_MEMORY_PATH = BASE_DIR / "learned_memory.json"

for d in [BASE_DIR, OUTPUT_IMAGES_DIR, STUDIO_SKILLS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "setup_completed": False,
    "setup_mode": "hybrid",
    "cloud_provider": "gemini",
    "cloud_image_provider": "auto",
    "comfy_url": "http://127.0.0.1:8188",
    "llm_url": "http://127.0.0.1:1235/v1",
    "ollama_url": "http://127.0.0.1:11434/v1",
    "ollama_model": "qwen2.5:7b",
    "llm_provider_mode": "gemini_first",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-4-5",
    "default_checkpoint": "Juggernaut-X-RunDiffusion-NSFW.safetensors",
    "default_negative_prompt": "bad hands, extra fingers, mutated hands, poorly drawn face, blurry, watermark, text, signature, low quality, worst quality, deformed, ugly, duplicate",
    "llm_system_prompt": (
        "You are a capable local AI assistant running privately on Joe's machine. "
        "You specialize in TTRPG character portrait design, fantasy worldbuilding, "
        "Dungeon Crawler World (DCC) Session 0 character creation, and ComfyUI image generation."
    ),
}

def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                merged.update(data)
                return merged
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

# ============================================================================
# LEVEL 1 LEARNING ENGINE — PERSISTENT CORRECTION & PREFERENCE MEMORY
# ============================================================================
DEFAULT_LEARNED_MEMORY = {
    "enabled": True,
    "positive_boosts": [
        "(natural skin texture, realistic pores:1.15)",
        "anatomically accurate hands and proportions"
    ],
    "negative_blocks": [
        "plastic skin",
        "over-smoothed airbrushed face",
        "asymmetrical eyes",
        "deformed fingers",
        "6 fingers"
    ],
    "style_lessons": [
        "Keep the user's exact requested subject, pose, and anatomy at the very front of the prompt.",
        "Use SDXL weights like (detail:1.25) on specific features the user corrected or emphasized."
    ],
    "corrections_log": []
}

def load_learned_memory():
    if LEARNED_MEMORY_PATH.exists():
        try:
            data = json.loads(LEARNED_MEMORY_PATH.read_text(encoding="utf-8"))
            merged = DEFAULT_LEARNED_MEMORY.copy()
            merged.update(data)
            return merged
        except Exception:
            pass
    save_learned_memory(DEFAULT_LEARNED_MEMORY)
    return DEFAULT_LEARNED_MEMORY.copy()

def save_learned_memory(mem):
    LEARNED_MEMORY_PATH.write_text(json.dumps(mem, indent=2), encoding="utf-8")

def apply_learned_memory_to_prompts(prompt, negative_prompt, apply_flag=True):
    if not apply_flag:
        return prompt, negative_prompt
    mem = load_learned_memory()
    if not mem.get("enabled", True):
        return prompt, negative_prompt
    p_out = prompt.strip()
    n_out = negative_prompt.strip()
    p_lower = p_out.lower()
    n_lower = n_out.lower()
    for boost in mem.get("positive_boosts", []):
        b_clean = boost.strip()
        if b_clean and b_clean.lower() not in p_lower:
            p_out = f"{p_out}, {b_clean}" if p_out else b_clean
            p_lower = p_out.lower()
    for block in mem.get("negative_blocks", []):
        bl_clean = block.strip()
        if bl_clean and bl_clean.lower() not in n_lower:
            n_out = f"{n_out}, {bl_clean}" if n_out else bl_clean
            n_lower = n_out.lower()
    return p_out, n_out

# ============================================================================
# IMAGE STUDIO SKILLS ENGINE (CREATED VIA AGENT CHAT)
# ============================================================================
def init_default_studio_skills():
    defaults = [
        {
            "id": "ttrpg_hero_portrait",
            "name": "TTRPG Hero Portrait (Painted Fantasy)",
            "description": "Classic tabletop RPG character portrait with rich oil brushwork, dramatic rim lighting, and heroic framing.",
            "prompt_prefix": "masterpiece fantasy character portrait, D&D handbook oil painting style, ",
            "prompt_suffix": "intricate armor and gear details, expressive face, dramatic chiaroscuro rim lighting, rich textures, painterly brushwork, sharp focus on eyes, 8k uhd",
            "negative_prompt": "modern clothing, photograph, blurry, bad hands, extra fingers, mutated hands, poorly drawn face, watermark, text, signature, low quality, deformed, duplicate",
            "ai_instructions": "Emphasize tabletop RPG character design, class-appropriate armor, weapons, and accessories, expressive facial character, and rich fantasy oil-painting lighting.",
            "settings": {
                "resolution": "832x1216",
                "steps": 30,
                "cfg": 5.5,
                "sampler": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 0.60
            }
        },
        {
            "id": "ttrpg_vtt_token",
            "name": "VTT Circular Token Bust (1:1)",
            "description": "Centered head-and-shoulders bust with bold silhouette and clean contrast, ideal for Roll20 / Foundry VTT tokens.",
            "prompt_prefix": "centered head and shoulders character portrait, tabletop RPG token art, ",
            "prompt_suffix": "bold readable silhouette, clean high-contrast lighting, crisp facial details, stylized fantasy illustration, uncluttered background, 8k",
            "negative_prompt": "full body, cropped head, cluttered background, blurry, bad anatomy, extra limbs, watermark, text, low quality",
            "ai_instructions": "Frame as a centered 1:1 head-and-shoulders bust with strong silhouette readability and clean background separation suitable for circular VTT tokens.",
            "settings": {
                "resolution": "1024x1024",
                "steps": 28,
                "cfg": 6.0,
                "sampler": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 0.60
            }
        },
        {
            "id": "dark_fantasy_figure",
            "name": "Dark Fantasy Collector Figure / Concept",
            "description": "Dramatic chiaroscuro rim lighting, intricate armor details, dark atmospheric backdrop.",
            "prompt_prefix": "masterpiece dark fantasy art, ",
            "prompt_suffix": "dramatic rim lighting, volumetric shadows, hyper-detailed textures, intricate ornamentation, dark atmospheric background, cinematic composition, 8k resolution",
            "negative_prompt": "flat lighting, overexposed, low detail, blurry, cartoon, watermark, text, deformed anatomy, extra limbs",
            "ai_instructions": "Focus on dramatic dark fantasy aesthetics, chiaroscuro lighting, rich material contrasts (metal, leather, cloth, stone), and striking heroic poses.",
            "settings": {
                "resolution": "832x1216",
                "steps": 30,
                "cfg": 5.5,
                "sampler": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 0.62
            }
        },
        {
            "id": "img2img_outfit_editor",
            "name": "Character Gear & Outfit Modifier (Img2Img)",
            "description": "Tuned for modifying armor, cloaks, or gear on an existing character portrait while preserving their face and pose.",
            "prompt_prefix": "",
            "prompt_suffix": "consistent lighting, seamless armor and fabric integration, natural proportions, high detail texture, sharp focus",
            "negative_prompt": "changed face, distorted pose, mutated hands, extra fingers, blurry, seam artifacts, low quality",
            "ai_instructions": "Keep the exact pose, camera angle, framing, and facial features of the original character while describing the new armor, outfit, or background changes.",
            "settings": {
                "resolution": "832x1216",
                "steps": 28,
                "cfg": 5.5,
                "sampler": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 0.55
            }
        }
    ]
    for sk in defaults:
        p = STUDIO_SKILLS_DIR / f"{sk['id']}.json"
        if not p.exists():
            p.write_text(json.dumps(sk, indent=2), encoding="utf-8")

init_default_studio_skills()

def load_studio_skills():
    skills = []
    for p in sorted(STUDIO_SKILLS_DIR.glob("*.json")):
        try:
            skills.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return skills

def get_studio_skill(skill_id):
    if not skill_id:
        return None
    p = STUDIO_SKILLS_DIR / f"{skill_id}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None

# ============================================================================
# SERVICE MANAGEMENT (COMFYUI & LOCAL LLM)
# ============================================================================
SERVICE_PROCS = {
    "comfy": None,
    "llm": None,
    "agent_logs": []
}

def log_agent(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    SERVICE_PROCS["agent_logs"].append(line)
    if len(SERVICE_PROCS["agent_logs"]) > 300:
        SERVICE_PROCS["agent_logs"] = SERVICE_PROCS["agent_logs"][-300:]

def http_get_json(url, timeout=2.5):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def http_post_json(url, payload, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def check_comfy_status():
    cfg = load_config()
    try:
        stats = http_get_json(f"{cfg['comfy_url']}/system_stats", timeout=1.5)
        obj_info = {}
        try:
            obj_info = http_get_json(f"{cfg['comfy_url']}/object_info", timeout=2.0)
        except Exception:
            pass
        return {
            "online": True,
            "stats": stats,
            "has_reactor": "ReActorFaceSwap" in obj_info,
            "has_ipadapter": any("ipadapter" in k.lower() for k in obj_info)
        }
    except Exception:
        return {"online": False, "has_reactor": False, "has_ipadapter": False}

def get_effective_gemini_key(cfg=None):
    if cfg is None:
        cfg = load_config()
    key = (cfg.get("gemini_api_key") or "").strip()
    if key:
        return key
    for env_var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(env_var):
            return os.environ[env_var].strip()
    for env_file in (BASE_DIR / ".env", Path(os.path.expanduser("~/.env"))):
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY=") or line.startswith("GOOGLE_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    return ""

def check_local_llm_only_status():
    cfg = load_config()
    candidates = [
        ("LM Studio", cfg.get("llm_url", "http://127.0.0.1:1235/v1")),
        ("LM Studio", "http://127.0.0.1:1235/v1"),
        ("LM Studio", "http://127.0.0.1:1234/v1"),
        ("Ollama", cfg.get("ollama_url", "http://127.0.0.1:11434/v1")),
    ]
    seen = set()
    for label, base_url in candidates:
        if base_url in seen:
            continue
        seen.add(base_url)
        try:
            models = http_get_json(f"{base_url}/models", timeout=1.5)
            all_ids = [m.get("id") for m in models.get("data", []) if m.get("id")]
            chat_models = [m for m in all_ids if "embed" not in m.lower()]
            if chat_models:
                return {"online": True, "provider": label, "base_url": base_url, "models": chat_models}
        except Exception:
            continue
    return {"online": False, "provider": None, "base_url": None, "models": []}

def check_llm_status():
    cfg = load_config()
    gem_key = get_effective_gemini_key(cfg)
    mode = cfg.get("llm_provider_mode", "gemini_first")
    local_st = check_local_llm_only_status()
    if gem_key and mode == "gemini_first":
        fallback_note = f" + Local ({local_st['models'][0]})" if local_st["online"] else " + Auto Local Fallback"
        return {
            "online": True,
            "provider": f"Gemini API (BLOCK_NONE){fallback_note}",
            "base_url": "https://generativelanguage.googleapis.com",
            "models": [cfg.get("gemini_model", "gemini-2.5-flash")],
            "gemini_configured": True,
            "local_online": local_st["online"]
        }
    if local_st["online"]:
        local_st["gemini_configured"] = bool(gem_key)
        return local_st
    return {"online": False, "provider": None, "models": [], "gemini_configured": bool(gem_key)}

def unload_local_llm():
    if LMSTUDIO_CLI.exists():
        log_agent("Unloading local LLM from VRAM so ComfyUI has 100% of RTX 4070 VRAM...")
        try:
            subprocess.run([str(LMSTUDIO_CLI), "unload", "--all"], creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, timeout=15)
            return {"ok": True, "message": "Unloaded local LLM from VRAM! All 12 GB of your RTX 4070 is now free for ComfyUI."}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "lms.exe not found."}

def start_comfyui():
    status = check_comfy_status()
    if status["online"]:
        return {"ok": True, "message": "ComfyUI is already running."}
    if not COMFY_PYTHON.exists():
        return {"ok": False, "error": f"ComfyUI Python not found at {COMFY_PYTHON}"}

    log_agent("Starting ComfyUI on http://127.0.0.1:8188 ...")
    cmd = [
        str(COMFY_PYTHON),
        "-s",
        str(COMFY_MAIN),
        "--windows-standalone-build",
        "--listen", "127.0.0.1",
        "--port", "8188",
        "--disable-auto-launch"
    ]
    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    SERVICE_PROCS["comfy"] = subprocess.Popen(
        cmd,
        cwd=str(COMFY_ROOT),
        creationflags=creationflags
    )
    return {"ok": True, "message": "ComfyUI is launching in a console window (takes ~10-20s to load ready)."}

def start_lmstudio_server(wait_ready=False):
    status = check_local_llm_only_status()
    if status["online"] and status["models"]:
        return {"ok": True, "message": f"Local LLM already online ({status['models'][0]})."}
    if LMSTUDIO_CLI.exists():
        log_agent("Starting LM Studio Server & loading qwen2.5-vl-7b-instruct (uncensored local fallback)...")
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            subprocess.run([str(LMSTUDIO_CLI), "server", "start"], creationflags=flags, timeout=12)
            if wait_ready:
                subprocess.run([
                    str(LMSTUDIO_CLI), "load", "qwen2.5-vl-7b-instruct",
                    "--gpu", "max", "-c", "4096", "--parallel", "1",
                    "--identifier", "qwen2.5-vl-7b-instruct", "-y"
                ], creationflags=flags, timeout=60)
            else:
                subprocess.Popen([
                    str(LMSTUDIO_CLI), "load", "qwen2.5-vl-7b-instruct",
                    "--gpu", "max", "-c", "4096", "--parallel", "1",
                    "--identifier", "qwen2.5-vl-7b-instruct", "-y"
                ], creationflags=flags)
            return {"ok": True, "message": "LM Studio Server started & loading qwen2.5-vl-7b-instruct."}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {
        "ok": False,
        "error": "LM Studio CLI (lms.exe) not found. Open LM Studio -> Developer tab -> click 'Start Server'."
    }

def get_available_loras():
    """Scans COMFY_LORAS recursively and returns a list of relative paths for ComfyUI LoraLoader."""
    loras = []
    if COMFY_LORAS.exists():
        for root, _, files in os.walk(COMFY_LORAS):
            for file in files:
                if file.lower().endswith((".safetensors", ".pt")):
                    rel_p = Path(root, file).relative_to(COMFY_LORAS)
                    loras.append(str(rel_p).replace("\\", "/"))
    return sorted(loras)

def list_installed_models():
    checkpoints = []
    if COMFY_CHECKPOINTS.exists():
        checkpoints = [f.name for f in COMFY_CHECKPOINTS.iterdir() if f.suffix.lower() in (".safetensors", ".ckpt")]
    loras = get_available_loras()
    ggufs = []
    if LMSTUDIO_MODELS.exists():
        for root, _, files in os.walk(LMSTUDIO_MODELS):
            for file in files:
                if file.endswith(".gguf") and not file.startswith("mmproj"):
                    ggufs.append(file)
    return {"checkpoints": checkpoints, "loras": loras, "ggufs": ggufs}

# ============================================================================
# COMFYUI API IMAGE GENERATION & IMG2IMG EDITING (SDXL / JUGGERNAUT-X-NSFW)
# ============================================================================
SDXL_OPTIMAL_RESOLUTIONS = [
    (1024, 1024),  # 1:1 Square
    (832, 1216),   # 2:3 Portrait
    (896, 1152),   # 3:4 Vertical
    (1216, 832),   # 3:2 Landscape
    (1152, 896),   # 4:3 Horizontal
    (1344, 768),   # 16:9 Widescreen
    (768, 1344),   # 9:16 Tall Vertical
]

def get_image_dimensions(img_path):
    """Returns (width, height) of a PNG, JPEG, or WebP file using pure Python or PIL."""
    p = Path(img_path)
    if not p.exists():
        return (1024, 1024)
    try:
        import struct
        with open(p, "rb") as f:
            head = f.read(32)
            if len(head) >= 24 and head.startswith(b"\x89PNG\r\n\x1a\n"):
                w, h = struct.unpack(">LL", head[16:24])
                return int(w), int(h)
            if head[:2] == b"\xff\xd8":
                f.seek(0)
                f.read(2)
                b = f.read(1)
                while b and ord(b) != 0xDA:
                    while ord(b) != 0xFF:
                        b = f.read(1)
                    while ord(b) == 0xFF:
                        b = f.read(1)
                    if 0xC0 <= ord(b) <= 0xC3:
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return int(w), int(h)
                    else:
                        size = int(struct.unpack(">H", f.read(2))[0])
                        f.read(size - 2)
                    b = f.read(1)
    except Exception:
        pass
    return (1024, 1024)

def nearest_sdxl_resolution(w, h):
    if w <= 0 or h <= 0:
        return (1024, 1024)
    target_ratio = w / float(h)
    best = min(SDXL_OPTIMAL_RESOLUTIONS, key=lambda pair: abs((pair[0] / float(pair[1])) - target_ratio))
    return best

def build_sdxl_workflow(
    prompt,
    negative_prompt,
    checkpoint,
    width,
    height,
    steps,
    cfg_scale,
    sampler_name,
    scheduler,
    seed,
    batch_size=1,
    lora_name="",
    lora_strength=0.8,
    loras=None,
    input_image_name="",
    mask_image_name="",
    denoise=1.0,
    scale_to_resolution=True,
    preserve_face=False,
    face_box=None,
    original_face_image_name="",
    enable_reactor=False,
    reactor_source_image_name=""
):
    if seed is None or int(seed) < 0:
        seed = random.randint(1, 2**53 - 1)
    else:
        seed = int(seed)

    workflow = {
        "4": {
            "inputs": {"ckpt_name": checkpoint},
            "class_type": "CheckpointLoaderSimple"
        },
        "6": {
            "inputs": {
                "text": prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {
                "seed": seed,
                "steps": int(steps),
                "cfg": float(cfg_scale),
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": float(denoise) if input_image_name else 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "8": {
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            },
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {
                "filename_prefix": "AIHub_Edit" if input_image_name else "AIHub_Gen",
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }

    if input_image_name:
        # Image-to-Image (Img2Img) pipeline
        workflow["11"] = {
            "inputs": {"image": input_image_name},
            "class_type": "LoadImage"
        }
        img_source_node = ["11", 0]
        if scale_to_resolution:
            workflow["12"] = {
                "inputs": {
                    "upscale_method": "lanczos",
                    "width": int(width),
                    "height": int(height),
                    "crop": "center",
                    "image": ["11", 0]
                },
                "class_type": "ImageScale"
            }
            img_source_node = ["12", 0]

        workflow["13"] = {
            "inputs": {
                "pixels": img_source_node,
                "vae": ["4", 2]
            },
            "class_type": "VAEEncode"
        }
        latent_source = ["13", 0]
        if int(batch_size) > 1:
            workflow["5"] = {
                "inputs": {
                    "samples": ["13", 0],
                    "amount": int(batch_size)
                },
                "class_type": "RepeatLatentBatch"
            }
            latent_source = ["5", 0]

        # User-drawn Brush Inpainting Mask pipeline
        if mask_image_name:
            workflow["14"] = {
                "inputs": {"image": mask_image_name},
                "class_type": "LoadImage"
            }
            mask_node = ["14", 1] # alpha or mask output
            if scale_to_resolution:
                # ComfyUI ImageScale on mask image so mask perfectly aligns with scaled input image
                workflow["15"] = {
                    "inputs": {
                        "upscale_method": "bilinear",
                        "width": int(width),
                        "height": int(height),
                        "crop": "center",
                        "image": ["14", 0]
                    },
                    "class_type": "ImageScale"
                }
                # Convert RGB mask image to Mask channel
                workflow["21"] = {
                    "inputs": {
                        "channel": "red",
                        "image": ["15", 0]
                    },
                    "class_type": "ImageToMask"
                }
                mask_node = ["21", 0]

            # Soft edge blending: Expand slightly then feather to eliminate hard seams
            workflow["23"] = {
                "inputs": {
                    "expand": 6,
                    "tapered_corners": True,
                    "mask": mask_node
                },
                "class_type": "GrowMask"
            }
            workflow["24"] = {
                "inputs": {
                    "left": 12,
                    "top": 12,
                    "right": 12,
                    "bottom": 12,
                    "mask": ["23", 0]
                },
                "class_type": "FeatherMask"
            }
            blended_mask = ["24", 0]

            # Inpaint Latent Noise Mask: full creative power inside painted brush stroke
            workflow["20"] = {
                "inputs": {
                    "samples": latent_source,
                    "mask": blended_mask
                },
                "class_type": "SetLatentNoiseMask"
            }
            workflow["3"]["inputs"]["latent_image"] = ["20", 0]

            # Hard Pixel-Lock Alpha Composite:
            # Guarantees 100.0% of unpainted pixels (outside the mask) stay identical to the original photo
            workflow["22"] = {
                "inputs": {
                    "destination": img_source_node,
                    "source": ["8", 0],
                    "mask": blended_mask,
                    "x": 0,
                    "y": 0,
                    "resize_source": False
                },
                "class_type": "ImageCompositeMasked"
            }
            workflow["9"]["inputs"]["images"] = ["22", 0]

        # Optional Face Preservation Pipeline (Feathered Latent Identity Protection during KSampler)
        # Protects core eye/nose/mouth identity structure in latent space without pasting raw unedited RGB pixels
        # after VAEDecode (so surface additions like fluids, lighting, or makeup still render naturally without seams).
        elif preserve_face and isinstance(face_box, (list, tuple)) and len(face_box) == 4:
            ymin, xmin, ymax, xmax = [float(v) for v in face_box]
            W, H = int(width), int(height)
            fx = max(0, min(int(xmin * W), W - 32))
            fy = max(0, min(int(ymin * H), H - 32))
            fw = max(48, min(int((xmax - xmin) * W), W - fx))
            fh = max(48, min(int((ymax - ymin) * H), H - fy))
            feather_x = max(16, int(fw * 0.30))
            feather_y = max(16, int(fh * 0.30))

            # Latent Noise Mask: full denoise (1.0) on body/clothes/background, reduced latent noise over core face landmarks
            workflow["16"] = {
                "inputs": {"value": 1.0, "width": W, "height": H},
                "class_type": "SolidMask"
            }
            workflow["17"] = {
                "inputs": {"value": 0.55, "width": fw, "height": fh},
                "class_type": "SolidMask"
            }
            workflow["18"] = {
                "inputs": {
                    "mask": ["17", 0],
                    "left": feather_x,
                    "top": feather_y,
                    "right": feather_x,
                    "bottom": feather_y
                },
                "class_type": "FeatherMask"
            }
            workflow["19"] = {
                "inputs": {
                    "destination": ["16", 0],
                    "source": ["18", 0],
                    "x": fx,
                    "y": fy,
                    "operation": "subtract"
                },
                "class_type": "MaskComposite"
            }
            workflow["20"] = {
                "inputs": {
                    "samples": latent_source,
                    "mask": ["19", 0]
                },
                "class_type": "SetLatentNoiseMask"
            }
            workflow["3"]["inputs"]["latent_image"] = ["20", 0]
        else:
            workflow["3"]["inputs"]["latent_image"] = latent_source
    else:
        # Standard Text-to-Image pipeline
        workflow["5"] = {
            "inputs": {
                "width": int(width),
                "height": int(height),
                "batch_size": int(batch_size)
            },
            "class_type": "EmptyLatentImage"
        }

    # Chained Multi-LoRA Loading
    active_loras = []
    if isinstance(loras, list):
        for l_item in loras:
            if isinstance(l_item, dict) and l_item.get("name"):
                active_loras.append(l_item)
            elif isinstance(l_item, str) and l_item.strip():
                active_loras.append({"name": l_item.strip(), "strength_model": 0.8, "strength_clip": 0.8})
    elif lora_name and lora_name.strip():
        active_loras.append({
            "name": lora_name.strip(),
            "strength_model": float(lora_strength),
            "strength_clip": float(lora_strength)
        })

    current_model = ["4", 0]
    current_clip = ["4", 1]

    for idx, l_cfg in enumerate(active_loras):
        node_id = f"lora_{idx + 1}"
        s_m = float(l_cfg.get("strength_model", l_cfg.get("strength", 0.8)))
        s_c = float(l_cfg.get("strength_clip", l_cfg.get("strength", 0.8)))
        workflow[node_id] = {
            "inputs": {
                "lora_name": l_cfg["name"],
                "strength_model": s_m,
                "strength_clip": s_c,
                "model": current_model,
                "clip": current_clip
            },
            "class_type": "LoraLoader"
        }
        current_model = [node_id, 0]
        current_clip = [node_id, 1]

    workflow["6"]["inputs"]["clip"] = current_clip
    workflow["7"]["inputs"]["clip"] = current_clip
    workflow["3"]["inputs"]["model"] = current_model

    # Optional ReActor Face-Swap (Full-Pose Identity Lock via InsightFace & CodeFormer)
    if enable_reactor and reactor_source_image_name:
        workflow["30"] = {
            "inputs": {"image": reactor_source_image_name},
            "class_type": "LoadImage"
        }
        # Destination image node to swap face onto:
        current_final_image = workflow["9"]["inputs"]["images"]
        workflow["31"] = {
            "inputs": {
                "enabled": True,
                "input_image": current_final_image,
                "source_image": ["30", 0],
                "swap_model": "inswapper_128.onnx",
                "facedetection": "retinaface_resnet50",
                "face_restore_model": "codeformer-v0.1.0.pth",
                "face_restore_visibility": 0.85,
                "codeformer_weight": 0.60,
                "detect_gender_input": "no",
                "detect_gender_source": "no",
                "input_faces_index": "0",
                "source_faces_index": "0",
                "console_log_level": 1
            },
            "class_type": "ReActorFaceSwap"
        }
        workflow["9"]["inputs"]["images"] = ["31", 0]

    return workflow, seed

def generate_image_via_comfy(params):
    cfg = load_config()
    setup_mode = cfg.get("setup_mode", "hybrid")
    prompt_raw = params.get("prompt", "")
    if setup_mode == "cloud":
        w, h = int(params.get("width", 1024)), int(params.get("height", 1024))
        sz = "1024x1536" if h > w else ("1536x1024" if w > h else "1024x1024")
        return llm_router.generate_cloud_image(prompt_raw, cfg, OUTPUT_IMAGES_DIR, size=sz)

    comfy_url = cfg["comfy_url"]
    if not check_comfy_status()["online"]:
        if COMFY_MAIN.exists():
            start_comfyui()
            for _ in range(35):
                time.sleep(1)
                if check_comfy_status()["online"]:
                    break
            else:
                if setup_mode == "hybrid":
                    return llm_router.generate_cloud_image(prompt_raw, cfg, OUTPUT_IMAGES_DIR)
                raise RuntimeError("ComfyUI is still starting up. Please wait 10 seconds and click Generate again.")
        elif setup_mode == "hybrid":
            return llm_router.generate_cloud_image(prompt_raw, cfg, OUTPUT_IMAGES_DIR)
        else:
            raise RuntimeError("ComfyUI is not installed locally. Switch to Hybrid/Cloud mode or install ComfyUI.")

    prompt = params.get("prompt", "")
    negative_prompt = params.get("negative_prompt", cfg["default_negative_prompt"])
    apply_learned = params.get("apply_learned_memory", True)
    prompt, negative_prompt = apply_learned_memory_to_prompts(prompt, negative_prompt, apply_flag=apply_learned)
    checkpoint = params.get("checkpoint", cfg["default_checkpoint"])
    width = int(params.get("width", 1024))
    height = int(params.get("height", 1024))
    steps = int(params.get("steps", 28))
    cfg_scale = float(params.get("cfg", 5.5))
    sampler_name = params.get("sampler", "dpmpp_2m_sde")
    scheduler = params.get("scheduler", "karras")
    seed = params.get("seed", -1)
    batch_size = int(params.get("batch_size", 1))
    loras = params.get("loras")
    lora_name = params.get("lora_name", "")
    lora_strength = float(params.get("lora_strength", 0.8))
    input_image_path = params.get("input_image", "")
    mask_image_path = params.get("mask_image", "")
    mask_image_b64 = params.get("mask_image_b64", "")
    original_face_path = params.get("original_face_image", "") or input_image_path
    preserve_face = bool(params.get("preserve_face", True)) and bool(input_image_path)
    denoise = float(params.get("denoise", 0.55 if input_image_path else 1.0))
    scale_to_resolution = bool(params.get("scale_to_resolution", True))

    input_image_name = ""
    mask_image_name = ""
    original_face_image_name = ""
    reactor_source_image_name = ""
    face_box = params.get("face_box")
    enable_reactor = bool(params.get("enable_reactor", False))

    if input_image_path and os.path.exists(str(input_image_path)):
        COMFY_INPUT.mkdir(parents=True, exist_ok=True)
        src_p = Path(input_image_path)
        input_image_name = f"input_{src_p.name}"
        shutil.copy2(str(src_p), str(COMFY_INPUT / input_image_name))

        if enable_reactor:
            reactor_source_image_name = input_image_name

        # Handle user-painted brush mask
        if mask_image_b64:
            try:
                if "," in mask_image_b64:
                    mask_image_b64 = mask_image_b64.split(",", 1)[1]
                mask_bytes = base64.b64decode(mask_image_b64)
                mask_image_name = f"mask_{uuid.uuid4().hex[:8]}_{src_p.stem}.png"
                (COMFY_INPUT / mask_image_name).write_bytes(mask_bytes)
                log_agent(f"[Inpainting] Received custom user brush mask -> {mask_image_name}")
            except Exception as e:
                log_agent(f"[Inpainting Warning] Could not decode mask_image_b64: {e}")
        elif mask_image_path and os.path.exists(str(mask_image_path)):
            mask_p = Path(mask_image_path)
            mask_image_name = f"mask_{mask_p.name}"
            shutil.copy2(str(mask_p), str(COMFY_INPUT / mask_image_name))

        if preserve_face:
            orig_p = Path(original_face_path) if (original_face_path and os.path.exists(str(original_face_path))) else src_p
            original_face_image_name = f"origface_{orig_p.name}"
            shutil.copy2(str(orig_p), str(COMFY_INPUT / original_face_image_name))
            face_prof = get_or_detect_face_profile(str(orig_p))
            if not face_box:
                face_box = face_prof.get("face_box")
            face_id_desc = (face_prof.get("face_identity") or "").strip()
            if face_id_desc and face_id_desc[:25].lower() not in prompt.lower():
                prompt = f"({face_id_desc}:1.25), {prompt}"

    # If Hybrid mode auto-loaded Local LLM for an uncensored Vision/Prompt fallback, free GPU VRAM before ComfyUI renders!
    if cfg.get("llm_provider_mode", "gemini_first") == "gemini_first" and check_local_llm_only_status()["online"]:
        log_agent("[HybridCompute] Auto-unloading local LLM before ComfyUI render so RTX 4070 has 100% free VRAM...")
        unload_local_llm()

    # Clamp denoise to 0.78 - 0.90 whenever a user-painted inpaint mask is active
    if mask_image_name and input_image_name:
        denoise = max(0.78, min(float(denoise), 0.90))

    workflow, actual_seed = build_sdxl_workflow(
        prompt=prompt,
        negative_prompt=negative_prompt,
        checkpoint=checkpoint,
        width=width,
        height=height,
        steps=steps,
        cfg_scale=cfg_scale,
        sampler_name=sampler_name,
        scheduler=scheduler,
        seed=seed,
        batch_size=batch_size,
        lora_name=lora_name,
        lora_strength=lora_strength,
        loras=loras,
        input_image_name=input_image_name,
        mask_image_name=mask_image_name,
        denoise=denoise,
        scale_to_resolution=scale_to_resolution,
        preserve_face=preserve_face,
        face_box=face_box,
        original_face_image_name=original_face_image_name,
        enable_reactor=enable_reactor,
        reactor_source_image_name=reactor_source_image_name
    )

    client_id = str(uuid.uuid4())
    inpaint_str = " + BrushMaskInpaint" if mask_image_name else ""
    reactor_str = " + ReActorFaceLock" if (enable_reactor and reactor_source_image_name) else ""
    face_lock_str = " + FaceLock" if (preserve_face and face_box and not mask_image_name and not enable_reactor) else ""
    mode_str = f"Img2Img (denoise={denoise}{inpaint_str}{reactor_str}{face_lock_str})" if input_image_name else "Txt2Img"
    log_agent(f"Submitting SDXL {mode_str} to ComfyUI ({checkpoint}, {width}x{height}, steps={steps})...")
    resp = http_post_json(f"{comfy_url}/prompt", {"prompt": workflow, "client_id": client_id})
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return a prompt_id: {resp}")

    # Poll /history/{prompt_id}
    saved_files = []
    start_t = time.time()
    while time.time() - start_t < 300:
        time.sleep(1.0)
        hist = http_get_json(f"{comfy_url}/history/{prompt_id}", timeout=5)
        if prompt_id in hist:
            outputs = hist[prompt_id].get("outputs", {})
            for node_id, node_out in outputs.items():
                for img in node_out.get("images", []):
                    fname = img["filename"]
                    subfolder = img.get("subfolder", "")
                    img_type = img.get("type", "output")
                    q = urllib.parse.urlencode({"filename": fname, "subfolder": subfolder, "type": img_type})
                    img_url = f"{comfy_url}/view?{q}"
                    local_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{fname}"
                    local_path = OUTPUT_IMAGES_DIR / local_name
                    urllib.request.urlretrieve(img_url, str(local_path))
                    # Save metadata sidecar
                    meta_path = local_path.with_suffix(".json")
                    with open(meta_path, "w", encoding="utf-8") as mf:
                        json.dump({
                            "prompt": prompt,
                            "negative_prompt": negative_prompt,
                            "checkpoint": checkpoint,
                            "width": width,
                            "height": height,
                            "steps": steps,
                            "cfg": cfg_scale,
                            "sampler": sampler_name,
                            "scheduler": scheduler,
                            "seed": actual_seed,
                            "created_at": datetime.now().isoformat()
                        }, mf, indent=2)
                    saved_files.append(f"/outputs/images/{local_name}")
            break

    log_agent(f"Generation complete! Saved {len(saved_files)} image(s).")
    return {"ok": True, "images": saved_files, "seed": actual_seed}

# ============================================================================
# HYBRID GEMINI API (BLOCK_NONE) + LOCAL VISION/CHAT LLM
# ============================================================================
GEMINI_SAFETY_BLOCK_NONE = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]

def call_gemini_api(messages, api_key, model_name="gemini-2.5-flash", temperature=0.7, max_tokens=1200):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={urllib.parse.quote(api_key)}"
    sys_parts = []
    contents = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            if isinstance(content, str):
                sys_parts.append({"text": content})
            continue

        gem_role = "model" if role == "assistant" else "user"
        parts = []
        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    parts.append({"text": item.get("text", "")})
                elif item.get("type") == "image_url":
                    data_url = item.get("image_url", {}).get("url", "")
                    if data_url.startswith("data:") and ";base64," in data_url:
                        header, b64_data = data_url.split(";base64,", 1)
                        mime_type = header.replace("data:", "")
                        parts.append({
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data
                            }
                        })
        if parts:
            contents.append({"role": gem_role, "parts": parts})

    payload = {
        "contents": contents,
        "safetySettings": GEMINI_SAFETY_BLOCK_NONE,
        "generationConfig": {
            "temperature": float(temperature),
            "maxOutputTokens": max(int(max_tokens), 4096)
        }
    }
    if sys_parts:
        payload["systemInstruction"] = {"parts": sys_parts}

    resp = http_post_json(url, payload, timeout=90)
    candidates = resp.get("candidates", [])
    if not candidates:
        block_reason = resp.get("promptFeedback", {}).get("blockReason", "UNKNOWN")
        raise RuntimeError(f"Gemini returned no candidates (blockReason={block_reason})")

    cand = candidates[0]
    parts = cand.get("content", {}).get("parts", [])
    text_out = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text_out:
        text_out = "".join(p.get("text", "") for p in parts).strip()
    if not text_out:
        finish_reason = cand.get("finishReason", "UNKNOWN")
        raise RuntimeError(f"Gemini returned empty text (finishReason={finish_reason})")
    return text_out

def _call_cloud_provider(messages, cfg, temperature=0.7, max_tokens=1600):
    prov = cfg.get("cloud_provider", "gemini")
    gem_key = get_effective_gemini_key(cfg)
    oai_key = (cfg.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")).strip()
    ant_key = (cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")).strip()

    order = [prov] + [p for p in ("gemini", "openai", "anthropic") if p != prov]
    last_err = None
    for p in order:
        try:
            if p == "openai" and oai_key:
                return llm_router.call_openai_api(messages, oai_key, model=cfg.get("openai_model", "gpt-4o-mini"), temperature=temperature, max_tokens=max_tokens)
            if p == "anthropic" and ant_key:
                return llm_router.call_anthropic_api(messages, ant_key, model=cfg.get("anthropic_model", "claude-sonnet-4-5"), temperature=temperature, max_tokens=max_tokens)
            if p == "gemini" and gem_key:
                gem_out = call_gemini_api(messages, gem_key, model_name=cfg.get("gemini_model", "gemini-2.5-flash"), temperature=temperature, max_tokens=max_tokens)
                low_out = (gem_out or "").lower().strip()
                if any(low_out.startswith(r) or r in low_out[:120] for r in ("i cannot fulfill", "i cannot generate", "i'm sorry, but i can't", "i am unable to", "against my safety")):
                    raise RuntimeError("Gemini returned a content policy refusal")
                return gem_out
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"No Cloud LLM provider succeeded ({last_err or 'missing API key'}).")


def call_local_llm(messages, temperature=0.7, max_tokens=1200):
    cfg = load_config()
    setup_mode = cfg.get("setup_mode", "")
    legacy_mode = cfg.get("llm_provider_mode", "gemini_first")
    if not setup_mode:
        setup_mode = "local" if legacy_mode == "local_only" else "hybrid"

    if setup_mode == "cloud":
        return _call_cloud_provider(messages, cfg, temperature=temperature, max_tokens=max_tokens)

    if setup_mode == "hybrid" and legacy_mode == "gemini_first":
        try:
            return _call_cloud_provider(messages, cfg, temperature=temperature, max_tokens=max_tokens)
        except Exception as cloud_err:
            log_agent(f"[Hybrid] Cloud unavailable ({cloud_err}) -> falling back to Local LLM...")

    # Local execution: Ollama / LM Studio
    for label, base_url in [
        ("Ollama", cfg.get("ollama_url", "http://127.0.0.1:11434/v1")),
        ("LM Studio", cfg.get("llm_url", "http://127.0.0.1:1235/v1")),
        ("LM Studio", "http://127.0.0.1:1234/v1"),
    ]:
        try:
            models = http_get_json(f"{base_url}/models", timeout=2.5)
            all_ids = [m.get("id") for m in models.get("data", []) if m.get("id")]
            chat_models = [m for m in all_ids if "embed" not in m.lower()]
            if not chat_models:
                continue
            pref_ollama = cfg.get("ollama_model", "qwen2.5:7b")
            model_id = pref_ollama if (label == "Ollama" and pref_ollama in chat_models) else chat_models[0]
            payload = {
                "model": model_id,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            resp = http_post_json(f"{base_url}/chat/completions", payload, timeout=180)
            return resp["choices"][0]["message"]["content"]
        except Exception:
            continue

    if setup_mode == "hybrid":
        log_agent("[Hybrid] Local LLM offline -> falling back to Cloud AI...")
        return _call_cloud_provider(messages, cfg, temperature=temperature, max_tokens=max_tokens)

    raise RuntimeError(
        "Local LLM (Ollama / LM Studio) is offline. Start Ollama or open the Setup Wizard to configure Cloud/Hybrid mode."
    )

def parse_ai_json_robust(raw_text):
    """
    Robustly extracts and parses a JSON object from LLM output even if wrapped in <think> tags,
    markdown fences, trailing commas, unescaped newlines, or slightly truncated closing braces.
    Returns dict on success or None if not parseable.
    """
    import re
    if not raw_text:
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", str(raw_text), flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start_i = cleaned.find("{")
    if start_i == -1:
        return None
    end_i = cleaned.rfind("}")
    candidate = cleaned[start_i:end_i + 1] if end_i > start_i else cleaned[start_i:]

    # 1. Try direct parse
    for attempt in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
        try:
            return json.loads(attempt)
        except Exception:
            pass

    # 2. Repair unescaped newlines inside strings and balance truncated braces
    repaired = candidate.replace("\r\n", " ").replace("\n", " ")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    open_braces = repaired.count("{") - repaired.count("}")
    if open_braces > 0:
        if repaired.count('"') % 2 == 1:
            repaired += '"'
        repaired += "}" * open_braces
    try:
        return json.loads(repaired)
    except Exception:
        return None

FACE_PROFILE_CACHE = {}

def get_or_detect_face_profile(image_path):
    """
    Detects and caches the subject's normalized face bounding box [ymin, xmin, ymax, xmax] (0.0-1.0)
    and exact facial feature identity description from the original uploaded image so edits retain
    the exact original facial features.
    """
    if not image_path or not os.path.exists(str(image_path)):
        return {"face_box": [0.06, 0.28, 0.36, 0.72], "face_identity": ""}
    key = str(Path(image_path).resolve())
    if key in FACE_PROFILE_CACHE:
        return FACE_PROFILE_CACHE[key]

    p = Path(image_path)
    mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    prompt = (
        "Locate the main person's face (forehead, eyes, nose, mouth, chin/jawline) in this image and describe their exact facial features.\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        "{\n"
        '  "has_face": true,\n'
        '  "face_box": [0.08, 0.32, 0.34, 0.68],\n'
        '  "face_identity": "concise comma-separated description of exact face shape, eye color and shape, eyebrows, nose contour, lip shape, skin tone, hair color and framing"\n'
        "}\n"
        "where face_box is [ymin, xmin, ymax, xmax] normalized from 0.0 to 1.0."
    )
    default_prof = {
        "has_face": True,
        "face_box": [0.06, 0.28, 0.35, 0.72],
        "face_identity": "exact same facial features, identical eye shape, nose, lips, jawline, and skin tone as the reference subject"
    }
    try:
        raw = call_local_llm([
            {"role": "system", "content": "You are a precise computer vision facial landmark & identity analyzer. Output valid JSON only."},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": prompt}
            ]}
        ], temperature=0.2, max_tokens=500)
        parsed = parse_ai_json_robust(raw)
        if isinstance(parsed, dict):
            if parsed.get("has_face") is False:
                prof = {"has_face": False, "face_box": None, "face_identity": ""}
                FACE_PROFILE_CACHE[key] = prof
                return prof
            fb = parsed.get("face_box")
            if isinstance(fb, list) and len(fb) == 4:
                vals = [max(0.0, min(1.0, float(v))) for v in fb]
                # If AI returned 0-1000 coordinates, normalize to 0-1
                if any(float(v) > 1.5 for v in fb):
                    vals = [max(0.0, min(1.0, float(v) / 1000.0)) for v in fb]
                if vals[2] > vals[0] + 0.04 and vals[3] > vals[1] + 0.04:
                    default_prof["face_box"] = vals
            if parsed.get("face_identity"):
                default_prof["face_identity"] = str(parsed["face_identity"]).strip()
    except Exception as e:
        log_agent(f"[FaceLock] Using default portrait face region ({e})")

    FACE_PROFILE_CACHE[key] = default_prof
    return default_prof

def enhance_sdxl_prompt(user_prompt, image_path="", skill_id=""):
    """
    Optimizes the user's prompt for SDXL (Juggernaut-X) while strictly preserving
    every subject, action, and detail the user wrote (never replacing with unrelated canned filler).
    If a Studio Skill is active, applies the skill's ai_instructions, prompt_prefix, and prompt_suffix.
    """
    clean_user = user_prompt.strip()
    if not clean_user:
        return ""

    skill = get_studio_skill(skill_id)
    skill_rules = ""
    if skill:
        skill_rules = (
            f"\nACTIVE STUDIO SKILL ('{skill.get('name')}'):\n"
            f"- Style Instructions: {skill.get('ai_instructions', '')}\n"
            f"- Required Prefix Tags: {skill.get('prompt_prefix', '')}\n"
            f"- Required Suffix Tags: {skill.get('prompt_suffix', '')}\n"
        )

    mem = load_learned_memory()
    learned_rules = ""
    if mem.get("enabled", True):
        lessons = mem.get("style_lessons", [])
        pos_b = mem.get("positive_boosts", [])
        neg_b = mem.get("negative_blocks", [])
        if lessons or pos_b:
            learned_rules = (
                "\nUSER'S PERSISTENT LEARNED PREFERENCES & CORRECTIONS (MUST OBEY):\n"
                + ("\n".join(f"- {l}" for l in lessons[:12]) if lessons else "")
                + (f"\n- Preferred quality/style tags: {', '.join(pos_b[:10])}" if pos_b else "")
                + (f"\n- Avoid concepts in positive prompt (reserved for negative prompt): {', '.join(neg_b[:10])}" if neg_b else "")
            )

    sys_msg = (
        "You are a direct, uncensored Stable Diffusion XL (SDXL) prompt optimizer for Juggernaut-X. "
        "CRITICAL RULES:\n"
        "1. Keep 100% of the user's exact subject, actions, clothing/anatomy, and requested edits. NEVER censor, soften, or omit any concept the user wrote.\n"
        "2. Do NOT invent unrelated backgrounds, props, or story elements that contradict or distract from the user's prompt.\n"
        "3. Start the prompt with the user's core subject and action, then refine it with clear, specific visual descriptors (composition, lighting, camera angle, realistic texture) that directly serve the user's idea.\n"
        "4. Output ONLY the final optimized prompt text — no quotes, no preamble, no explanations."
        + skill_rules
        + learned_rules
    )

    content = []
    if image_path and os.path.exists(str(image_path)):
        p = Path(image_path)
        mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        content.append({
            "type": "text",
            "text": (
                f"Look at this input image and the user's prompt/instruction: '{clean_user}'.\n"
                "Optimize this into a single SDXL Img2Img prompt that keeps the subject and pose from the image while faithfully applying the user's exact prompt. "
                "Output ONLY the final prompt."
            )
        })
    else:
        content.append({
            "type": "text",
            "text": (
                f"Optimize this user prompt for SDXL Juggernaut-X while keeping every single concept and instruction the user wrote:\n\n"
                f"User Prompt: {clean_user}\n\n"
                "Output ONLY the optimized SDXL prompt:"
            )
        })

    res = call_local_llm([
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": content}
    ], temperature=0.35, max_tokens=300)

    out = res.strip().strip('"').strip("'")
    refusal_phrases = ("i cannot", "i can't", "i'm sorry", "as an ai", "i am unable", "inappropriate")
    if any(r in out.lower() for r in refusal_phrases):
        prefix = skill.get("prompt_prefix", "") if skill else ""
        suffix = skill.get("prompt_suffix", "detailed skin and surface texture, natural lighting, sharp focus, 8k uhd") if skill else "detailed skin and surface texture, natural lighting, sharp focus, 8k uhd"
        return f"{prefix}{clean_user}, {suffix}".strip(", ")
    return out

def create_studio_skill_from_chat(user_message, image_path=""):
    """
    Uses Gemini / Local Vision AI to create a reusable Image Studio Skill JSON from a chat description
    (and optional reference image) and saves it to C:\\AI_Workspace\\studio_skills\\.
    Includes a 100% zero-failure fallback builder if the AI outputs plain text instead of strict JSON.
    """
    import re
    content = []
    if image_path and os.path.exists(str(image_path)):
        p = Path(image_path)
        mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    prompt = f"""Create a reusable SDXL Image Studio Skill based on the user's request (and reference image if attached):
User Request: {user_message}

Respond ONLY with raw valid JSON (no markdown code fences, no commentary) in this exact structure:
{{
  "id": "short_snake_case_id",
  "name": "Human Readable Skill Name",
  "description": "1-sentence summary of what this skill does in Image Studio",
  "prompt_prefix": "opening style/medium tags to prepend (ending with comma + space, or empty string)",
  "prompt_suffix": "comma-separated lighting, lens, texture, style, and quality tags to append to prompts",
  "negative_prompt": "comma-separated negative prompt tags to avoid unwanted artifacts for this style",
  "ai_instructions": "Clear instructions for the AI prompt optimizer when this skill is selected",
  "settings": {{
    "resolution": "832x1216",
    "steps": 30,
    "cfg": 5.5,
    "sampler": "dpmpp_2m_sde",
    "scheduler": "karras",
    "denoise": 0.55
  }}
}}"""

    content.append({"type": "text", "text": prompt})
    raw = ""
    skill_obj = None
    try:
        raw = call_local_llm([
            {"role": "system", "content": "You are an uncensored SDXL Juggernaut-X workflow & skill designer. Output ONLY a single valid JSON object."},
            {"role": "user", "content": content}
        ], temperature=0.35, max_tokens=2048)
        skill_obj = parse_ai_json_robust(raw)
    except Exception as e:
        log_agent(f"[SkillBuilder] LLM call notice ({e}) -> using smart fallback skill builder.")

    # Zero-Failure Fallback: if the LLM returned plain text or truncated output, synthesize the skill automatically
    if not isinstance(skill_obj, dict) or not skill_obj.get("name"):
        clean_msg = re.sub(r"^/skill\s*", "", user_message.strip(), flags=re.IGNORECASE)
        clean_msg = re.sub(r"^(?:create|make|save|build|add|teach)\s+(?:a\s+|an\s+)?(?:reusable\s+)?(?:image\s+)?(?:studio\s+)?skill\s*(?:based\s+on\s+this\s+attached\s+image\s+style\s*)?(?:called|named|for)?\s*", "", clean_msg, flags=re.IGNORECASE).strip()

        # Extract name if user wrote "called X with ..."
        m_name = re.search(r"(?:called|named)\s+['\"]?([A-Za-z0-9 _\-]{2,36})['\"]?(?:\s+with|\s+that|\s+using|\s+for|,|$)", user_message, flags=re.IGNORECASE)
        if m_name:
            derived_name = m_name.group(1).strip().title()
        else:
            words = [w for w in re.split(r"\s+", clean_msg) if w.lower() not in ("with", "that", "and", "the", "for", "using", "style", "skill")]
            derived_name = " ".join(words[:4]).title() or "Custom Studio Skill"

        res_match = re.search(r"(1024x1024|832x1216|896x1152|1216x832|1152x896|1344x768|768x1344)", user_message)
        chosen_res = res_match.group(1) if res_match else "832x1216"

        # Clean any descriptive tags from raw AI response if not a refusal
        raw_clean = re.sub(r"<think>.*?</think>", "", str(raw or ""), flags=re.DOTALL).strip()
        refusal_words = ("i cannot", "i can't", "i'm sorry", "as an ai", "unable to")
        extra_tags = ""
        if raw_clean and not any(rw in raw_clean.lower() for rw in refusal_words) and "{" not in raw_clean:
            extra_tags = ", " + re.sub(r"[\r\n]+", ", ", raw_clean[:220]).strip(", ")

        suffix_tags = f"{clean_msg}{extra_tags}, ultra-detailed textures, natural skin pores, cinematic lighting, sharp focus, 8k uhd".strip(", ")
        skill_obj = {
            "id": re.sub(r"[^a-z0-9_]+", "_", derived_name.lower()).strip("_"),
            "name": derived_name,
            "description": f"Custom Studio Skill: {clean_msg[:110]}",
            "prompt_prefix": "masterpiece, photorealistic, ",
            "prompt_suffix": suffix_tags,
            "negative_prompt": "changed face, plastic skin, airbrushed, bad hands, extra fingers, mutated hands, blurry, watermark, low quality, deformed",
            "ai_instructions": f"Apply this custom style and workflow faithfully: {clean_msg}. Preserve the subject's exact facial features and core request.",
            "settings": {
                "resolution": chosen_res,
                "steps": 30,
                "cfg": 5.5,
                "sampler": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 0.52
            }
        }

    raw_id = str(skill_obj.get("id") or skill_obj.get("name") or "custom_skill").lower()
    clean_id = re.sub(r"[^a-z0-9_]+", "_", raw_id).strip("_")[:40] or f"skill_{uuid.uuid4().hex[:6]}"
    skill_obj["id"] = clean_id
    skill_obj.setdefault("settings", {
        "resolution": "832x1216",
        "steps": 30,
        "cfg": 5.5,
        "sampler": "dpmpp_2m_sde",
        "scheduler": "karras",
        "denoise": 0.52
    })

    skill_path = STUDIO_SKILLS_DIR / f"{clean_id}.json"
    skill_path.write_text(json.dumps(skill_obj, indent=2), encoding="utf-8")
    log_agent(f"Created new Image Studio Skill: {skill_obj.get('name')} ({clean_id}.json)")
    return skill_obj

def clean_instruction_to_sdxl_tags(raw_instruction):
    """
    Converts conversational English edit instructions (e.g. 'change the armor to weathered steel plate')
    into clean, weighted SDXL visual tags without negative/meta filler words that confuse SDXL CLIP.
    """
    import re
    txt = (raw_instruction or "").strip()
    if not txt:
        return ""
    # Strip conversational filler and negative instructions that confuse SDXL CLIP
    patterns = [
        r"(?i)^i\s+want\s+you\s+to\s+",
        r"(?i)^can\s+you\s+(please\s+)?",
        r"(?i)^please\s+",
        r"(?i)\b(add|put|place|apply|make)\s+(the\s+)?",
        r"(?i)\bto\s+this\s+(image|photo|picture|scene)\b",
        r"(?i)\bin\s+this\s+(image|photo|picture|scene)\b",
        r"(?i)\bwithout\s+changing\b.*$",
        r"(?i)\bkeep(ing)?\s+(the\s+)?(same\s+|original\s+)?face.*$",
        r"(?i)\bdon'?t\s+change.*$",
    ]
    cleaned = txt
    for pat in patterns:
        cleaned = re.sub(pat, " ", cleaned).strip(" ,.")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
    if cleaned:
        return f"({cleaned}:1.3)"
    return ""

def build_edit_prompt_with_vision_ai(image_path, edit_instruction="", original_image_path="", chat_history=None):
    p = Path(image_path)
    if not p.exists():
        return edit_instruction or "high quality detailed image"

    orig_p = Path(original_image_path) if (original_image_path and os.path.exists(str(original_image_path))) else p
    face_prof = get_or_detect_face_profile(str(orig_p))
    face_id_text = face_prof.get("face_identity", "exact same facial features as reference image")
    sdxl_edit_tags = clean_instruction_to_sdxl_tags(edit_instruction)

    # Gather cumulative edit context from chat_history so multi-turn edits never forget earlier turns
    history_context = ""
    if chat_history and isinstance(chat_history, list):
        recent_user_turns = [
            h.get("content", "").strip()
            for h in chat_history[-6:]
            if h.get("role") == "user" and h.get("content", "").strip()
        ]
        if recent_user_turns:
            history_context = (
                "\nPrevious conversation instructions in this session (keep cumulative changes consistent unless overridden):\n- "
                + "\n- ".join(recent_user_turns[-4:])
                + "\n"
            )

    mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    if edit_instruction.strip():
        instruction_text = (
            f"Look closely at this image. The user wants to modify it with this instruction: '{edit_instruction}'.\n"
            f"Key SDXL visual tags to emphasize at the front: {sdxl_edit_tags}\n"
            f"CRITICAL IDENTITY LOCK: The subject's facial features MUST remain identical to the original uploaded person: ({face_id_text}:1.25).\n"
            f"{history_context}"
            "Write a comma-separated Stable Diffusion XL (SDXL) tag prompt (NOT conversational sentences). "
            "Put the requested visual addition/modification and the subject's locked facial features at the very beginning with SDXL weights like (tag:1.3), "
            "followed by the exact pose, skin texture, lighting, and camera angle from the photo. Output ONLY the raw SDXL prompt."
        )
    else:
        instruction_text = (
            f"Look closely at this image. Subject's locked facial features: ({face_id_text}:1.25).\n"
            "Write a comma-separated Stable Diffusion XL (SDXL) prompt describing the exact facial features, subject, pose, clothing/details, lighting, background, and artistic style. "
            "Output ONLY the SDXL prompt text, no intro or commentary."
        )
    content = [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        {"type": "text", "text": instruction_text}
    ]
    try:
        res = call_local_llm([
            {"role": "system", "content": "You are a visual tag engineer for SDXL character portraits and fantasy art. Output only comma-separated SDXL visual tags."},
            {"role": "user", "content": content}
        ], temperature=0.4, max_tokens=600)
        out = res.strip().strip('"')
        refusal_phrases = ("i cannot", "i can't", "i'm sorry", "as an ai", "unable to")
        if any(r in out.lower() for r in refusal_phrases):
            return f"{sdxl_edit_tags}, ({face_id_text}:1.25), raw candid photograph, natural skin pores, realistic lighting, sharp focus, 8k uhd".strip(", ")
        if sdxl_edit_tags and sdxl_edit_tags[:20].lower() not in out.lower():
            out = f"{sdxl_edit_tags}, {out}"
        return out
    except Exception as e:
        log_agent(f"Vision prompt helper fallback: {e}")
        return f"{sdxl_edit_tags or edit_instruction}, ({face_id_text}:1.25), raw candid photograph, natural skin texture, realistic lighting, sharp focus, 8k uhd".strip(", ")

def fix_and_learn_from_image(
    image_path,
    feedback_text,
    current_prompt="",
    current_negative="",
    skill_id="",
    remember_globally=True,
    update_skill=False,
    auto_regenerate=True
):
    """
    Level 1 Learning Engine:
    1. Inspects the flawed image + its saved sidecar metadata (.json) + the user's feedback/correction.
    2. Diagnoses what went wrong and writes a repaired SDXL prompt (with (tag:1.3) weights) and repaired negative prompt.
    3. Chooses whether to run Img2Img (with recommended denoise) or fresh Txt2Img.
    4. Extracts reusable positive boosts, negative blocks, and style lessons into C:\\AI_Workspace\\learned_memory.json
       (and optionally into the active Studio Skill).
    5. Optionally triggers ComfyUI immediately to generate the corrected image.
    """
    cfg = load_config()
    p = Path(image_path) if image_path else None
    meta = {}
    if p and p.exists():
        meta_p = p.with_suffix(".json")
        if meta_p.exists():
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
            except Exception:
                pass

    orig_prompt = current_prompt.strip() or meta.get("prompt", "")
    orig_neg = current_negative.strip() or meta.get("negative_prompt", cfg["default_negative_prompt"])

    content = []
    if p and p.exists():
        mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    instruction = f"""Analyze the user's correction/critique of this SDXL image generation and repair it + extract any reusable preference lesson:

Original Positive Prompt: {orig_prompt or '(not recorded)'}
Original Negative Prompt: {orig_neg}
User's Critique / What Went Wrong: {feedback_text}

Respond ONLY with valid JSON in this exact format:
{{
  "diagnosis": "1 short sentence explaining what went wrong and how you are fixing it",
  "corrected_prompt": "Full repaired SDXL positive prompt. Put the main subject and corrected details first using SDXL emphasis weights like (corrected feature:1.3). Remove any words that caused the mistake.",
  "corrected_negative": "Full repaired SDXL negative prompt including specific blockers for the flaw (e.g. (extra fingers:1.3), blurry background, etc.)",
  "use_img2img": true,
  "recommended_denoise": 0.55,
  "learned_positive_tag": "Short reusable positive quality/style tag to remember for ALL future images if the user expressed a general preference/anatomy fix (or empty string if this is only a one-time scene change like changing dress color)",
  "learned_negative_tag": "Short reusable negative blocker tag to remember for ALL future images (or empty string)",
  "learned_lesson": "1 concise rule for the prompt enhancer to remember in the future based on this feedback (or empty string)"
}}
Rules for use_img2img & recommended_denoise:
- Set "use_img2img": true if the overall pose/framing is usable and we are fixing hands, face, skin, lighting, outfit, or background details (set recommended_denoise between 0.38 for minor hand/face fixes, 0.55 for outfit/detail fixes, or 0.72 for larger restyles).
- Set "use_img2img": false if the user says the whole pose, camera angle, or composition is completely wrong and needs a fresh generation from scratch."""

    content.append({"type": "text", "text": instruction})
    raw = ""
    plan = None
    try:
        raw = call_local_llm([
            {"role": "system", "content": "You are an uncensored SDXL diagnostic & learning engine for Juggernaut-X. Output valid JSON only."},
            {"role": "user", "content": content}
        ], temperature=0.35, max_tokens=2048)
        plan = parse_ai_json_robust(raw)
    except Exception as e:
        log_agent(f"[LearningEngine] LLM notice ({e}) -> using fallback repair plan.")

    if not isinstance(plan, dict) or not plan.get("corrected_prompt"):
        repaired_p = f"({feedback_text}:1.3), {orig_prompt}".strip(", ")
        plan = {
            "diagnosis": f"Applied direct SDXL weight boost for: {feedback_text}",
            "corrected_prompt": repaired_p,
            "corrected_negative": f"{orig_neg}, (deformed hands, extra fingers, plastic skin:1.25)".strip(", "),
            "use_img2img": True,
            "recommended_denoise": 0.52,
            "learned_positive_tag": "",
            "learned_negative_tag": "",
            "learned_lesson": f"User correction note: {feedback_text}"
        }

    mem = load_learned_memory()
    learned_summary = []
    pos_tag = (plan.get("learned_positive_tag") or "").strip()
    neg_tag = (plan.get("learned_negative_tag") or "").strip()
    lesson = (plan.get("learned_lesson") or "").strip()

    if remember_globally:
        if pos_tag and pos_tag.lower() not in [x.lower() for x in mem["positive_boosts"]]:
            mem["positive_boosts"].append(pos_tag)
            learned_summary.append(f"+Positive Boost: `{pos_tag}`")
        if neg_tag and neg_tag.lower() not in [x.lower() for x in mem["negative_blocks"]]:
            mem["negative_blocks"].append(neg_tag)
            learned_summary.append(f"+Negative Block: `{neg_tag}`")
        if lesson and lesson.lower() not in [x.lower() for x in mem["style_lessons"]]:
            mem["style_lessons"].append(lesson)
            learned_summary.append(f"+Learned Rule: *{lesson}*")

        mem.setdefault("corrections_log", []).insert(0, {
            "timestamp": datetime.now().isoformat(),
            "feedback": feedback_text,
            "diagnosis": plan.get("diagnosis", ""),
            "learned_positive_tag": pos_tag,
            "learned_negative_tag": neg_tag,
            "learned_lesson": lesson
        })
        mem["corrections_log"] = mem["corrections_log"][:50]
        save_learned_memory(mem)

    skill_updated_name = ""
    if update_skill and skill_id:
        sk = get_studio_skill(skill_id)
        if sk:
            if pos_tag and pos_tag.lower() not in sk.get("prompt_suffix", "").lower():
                sk["prompt_suffix"] = f"{sk.get('prompt_suffix', '').strip(', ')}, {pos_tag}".strip(", ")
            if neg_tag and neg_tag.lower() not in sk.get("negative_prompt", "").lower():
                sk["negative_prompt"] = f"{sk.get('negative_prompt', '').strip(', ')}, {neg_tag}".strip(", ")
            if lesson and lesson.lower() not in sk.get("ai_instructions", "").lower():
                sk["ai_instructions"] = f"{sk.get('ai_instructions', '').strip()} {lesson}".strip()
            (STUDIO_SKILLS_DIR / f"{skill_id}.json").write_text(json.dumps(sk, indent=2), encoding="utf-8")
            skill_updated_name = sk.get("name", skill_id)
            learned_summary.append(f"Updated Studio Skill: `{skill_updated_name}`")

    gen_result = None
    if auto_regenerate:
        use_i2i = bool(plan.get("use_img2img", True)) and bool(p and p.exists())
        denoise_val = float(plan.get("recommended_denoise", 0.52))
        if p and p.exists():
            orig_w, orig_h = get_image_dimensions(p)
            best_w, best_h = nearest_sdxl_resolution(orig_w, orig_h)
        else:
            best_w = int(meta.get("width", 832))
            best_h = int(meta.get("height", 1216))

        gen_result = generate_image_via_comfy({
            "prompt": plan.get("corrected_prompt", orig_prompt),
            "negative_prompt": plan.get("corrected_negative", orig_neg),
            "checkpoint": meta.get("checkpoint", cfg["default_checkpoint"]),
            "width": best_w,
            "height": best_h,
            "steps": max(int(meta.get("steps", 30)), 30),
            "cfg": float(meta.get("cfg", 5.5)),
            "input_image": str(p) if use_i2i else "",
            "original_face_image": str(p) if use_i2i else "",
            "preserve_face": True,
            "denoise": denoise_val if use_i2i else 1.0,
            "scale_to_resolution": True,
            "apply_learned_memory": True
        })

    log_agent(f"[LearningEngine] Processed image correction: '{feedback_text}' -> learned {len(learned_summary)} rule(s).")
    return {
        "ok": True,
        "plan": plan,
        "learned_summary": learned_summary,
        "memory": mem,
        "generation": gen_result
    }

def handle_agent_chat(
    user_message,
    chat_history,
    image_path="",
    mask_image_b64="",
    original_image_path="",
    denoise=0.55,
    action_mode="auto",
    preserve_face=True,
    dcc_mode=False,
    dcc_character=None,
    sw5e_mode=False,
    sw5e_character=None,
    sw5e_ship=None,
    dm_mode=False,
    dm_system="dnd5e",
    dnd5e_mode=False,
    dnd5e_character=None
):
    cfg = load_config()
    msg_lower = user_message.lower().strip()
    orig_anchor = original_image_path if (original_image_path and os.path.exists(str(original_image_path))) else image_path

    # DCC Session 0 Character Sheet Assistant
    if dcc_mode or msg_lower.startswith("/dcc"):
        clean_msg = user_message[4:].strip() if msg_lower.startswith("/dcc") else user_message
        if not clean_msg:
            clean_msg = "Help me create a new Dungeon Crawler World (DCC) character for Session 0."
        sys_prompt = dcc_engine.build_dcc_agent_system_prompt(dcc_character)
        messages = [{"role": "system", "content": sys_prompt}]
        for h in chat_history[-10:]:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": clean_msg})
        reply = call_local_llm(messages)
        parsed = dcc_engine.parse_dcc_json_from_llm(reply)
        saved_char = None
        if parsed:
            if isinstance(dcc_character, dict):
                if dcc_character.get("id") and not parsed.get("id"):
                    parsed["id"] = dcc_character["id"]
                if dcc_character.get("portrait_path") and not parsed.get("portrait_path"):
                    parsed["portrait_path"] = dcc_character["portrait_path"]
            if image_path and not parsed.get("portrait_path"):
                parsed["portrait_path"] = image_path
            saved_char = dcc_engine.save_character(parsed)
        return {"reply": reply, "images": [], "dcc_character": saved_char}

    # SW5e Session 0 Character & Starship Assistant
    if sw5e_mode or msg_lower.startswith("/sw5e"):
        clean_msg = user_message[5:].strip() if msg_lower.startswith("/sw5e") else user_message
        if not clean_msg:
            clean_msg = "Help me create a Star Wars 5e (SW5e) character and their starship for Session 0."
        sys_prompt = sw5e_engine.build_sw5e_agent_system_prompt(sw5e_character, sw5e_ship)
        messages = [{"role": "system", "content": sys_prompt}]
        for h in chat_history[-10:]:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": clean_msg})
        reply = call_local_llm(messages)
        parsed = sw5e_engine.parse_sw5e_json_from_llm(reply)
        saved_char = None
        saved_ship = None
        if parsed:
            c_obj = parsed.get("character") if isinstance(parsed.get("character"), dict) else (parsed if "species" in parsed or "class_name" in parsed else None)
            s_obj = parsed.get("ship") if isinstance(parsed.get("ship"), dict) else (parsed if "model" in parsed or "hyperdrive" in parsed else None)
            if c_obj:
                if isinstance(sw5e_character, dict) and sw5e_character.get("id") and not c_obj.get("id"):
                    c_obj["id"] = sw5e_character["id"]
                saved_char = sw5e_engine.save_character(c_obj)
            if s_obj:
                if isinstance(sw5e_ship, dict) and sw5e_ship.get("id") and not s_obj.get("id"):
                    s_obj["id"] = sw5e_ship["id"]
                saved_ship = sw5e_engine.save_ship(s_obj)
        return {"reply": reply, "images": [], "sw5e_character": saved_char, "sw5e_ship": saved_ship}

    # D&D 5e Session 0 Character Sheet Assistant
    if dnd5e_mode or msg_lower.startswith("/dnd5e"):
        clean_msg = user_message[6:].strip() if msg_lower.startswith("/dnd5e") else user_message
        if not clean_msg:
            clean_msg = "Help me create a Level 1 D&D 5e character for Session 0."
        sys_prompt = dnd5e_engine.build_dnd5e_agent_system_prompt(dnd5e_character)
        messages = [{"role": "system", "content": sys_prompt}]
        for h in chat_history[-10:]:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": clean_msg})
        reply = call_local_llm(messages)
        parsed = dnd5e_engine.parse_dnd5e_json_from_llm(reply)
        saved_char = None
        if parsed:
            if isinstance(dnd5e_character, dict):
                if dnd5e_character.get("id") and not parsed.get("id"):
                    parsed["id"] = dnd5e_character["id"]
                if dnd5e_character.get("portrait_path") and not parsed.get("portrait_path"):
                    parsed["portrait_path"] = dnd5e_character["portrait_path"]
            if image_path and not parsed.get("portrait_path"):
                parsed["portrait_path"] = image_path
            saved_char = dnd5e_engine.save_character(parsed)
        return {"reply": reply, "images": [], "dnd5e_character": saved_char}

    # DM Companion Mode (RAG over C:\AI_Workspace\Rules)
    if dm_mode or msg_lower.startswith("/dm"):
        clean_msg = user_message[3:].strip() if msg_lower.startswith("/dm") else user_message
        active_sys = dm_system if dm_system in rules_rag.SYSTEM_FOLDERS else "dnd5e"
        for prefix, skey in [("dcc ", "dcc"), ("sw5e ", "sw5e"), ("dnd5e ", "dnd5e"), ("5e ", "dnd5e")]:
            if clean_msg.lower().startswith(prefix):
                active_sys = skey
                clean_msg = clean_msg[len(prefix):].strip()
                break
        if not clean_msg:
            clean_msg = "Summarize the key combat and turn structure rules for this system."
        rag_st = rules_rag.get_index_status()
        if (rag_st.get("indexed_pages") or {}).get(active_sys, 0) <= 0:
            folder_hint = str(rules_rag.SYSTEM_FOLDERS.get(active_sys, "Rules/"))
            return {
                "reply": (
                    f"🔒 **DM Companion Locked for `{active_sys.upper()}`**\n\n"
                    f"No rulebook PDFs are indexed yet in `{folder_hint}`.\n"
                    f"Drop your owned **{rules_rag.SYSTEM_LABELS.get(active_sys, active_sys)}** rulebook PDF(s) into that folder (or open the **🧙 Setup Wizard** at the top) to unlock rulebook-cited DM answers!"
                ),
                "images": [],
                "rulebook_locked": True,
                "dm_system": active_sys,
            }
        dm_prompt, hits = rules_rag.build_dm_system_prompt(active_sys, clean_msg, top_k=6)
        camp_ctx = campaign_engine.build_campaign_context_for_chat(clean_msg, system=active_sys)
        if camp_ctx:
            dm_prompt = f"{dm_prompt}\n\n{camp_ctx}\n"
        messages = [{"role": "system", "content": dm_prompt}]
        for h in chat_history[-10:]:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
        messages.append({"role": "user", "content": clean_msg})
        reply = call_local_llm(messages)
        citations = [{"book": h["book"], "page": h["page"]} for h in hits]
        return {"reply": reply, "images": [], "dm_citations": citations, "dm_system": active_sys}

    # Check if the user wants to create/save an Image Studio Skill from chat (with or without an attached reference image)
    is_skill_request = (
        msg_lower.startswith("/skill")
        or (image_path and action_mode == "skill")
        or (
            "skill" in msg_lower
            and any(w in msg_lower for w in ("create", "make", "save", "build", "new", "teach", "add", "turn", "studio"))
        )
    )
    if is_skill_request:
        sk = create_studio_skill_from_chat(user_message, image_path=image_path)
        st = sk.get("settings", {})
        return {
            "reply": (
                f"⚡ **Created New Image Studio Skill: `{sk.get('name')}`** (`{sk.get('id')}.json`)\n\n"
                f"• **Description:** {sk.get('description')}\n"
                f"• **Prompt Prefix:** `{sk.get('prompt_prefix') or '(none)'}`\n"
                f"• **Prompt Suffix:** `{sk.get('prompt_suffix')}`\n"
                f"• **Negative Prompt:** `{sk.get('negative_prompt')}`\n"
                f"• **Preset Settings:** `{st.get('resolution', '832x1216')}` | Steps: `{st.get('steps', 30)}` | CFG: `{st.get('cfg', 5.5)}` | Denoise: `{st.get('denoise', 0.55)}`\n\n"
                f"It is now available in the **⚡ Studio Skill** dropdown in **🎨 Image Studio**!"
            ),
            "images": [],
            "created_skill": sk
        }

    # Check if the user is correcting an image and/or teaching a rule (/fix, /learn, or action_mode == 'fix')
    is_fix_and_learn = (
        msg_lower.startswith("/fix")
        or msg_lower.startswith("/learn")
        or (image_path and action_mode == "fix")
        or (
            image_path
            and any(w in msg_lower for w in ("wrong", "messed up", "bad ", "fix ", "correct ", "remember", "never ", "always ", "stop "))
        )
    )
    if is_fix_and_learn:
        clean_fb = user_message
        for pref in ("/fix ", "/learn "):
            if msg_lower.startswith(pref):
                clean_fb = user_message[len(pref):].strip()
                break
        res_fix = fix_and_learn_from_image(
            image_path=image_path,
            feedback_text=clean_fb,
            remember_globally=True,
            update_skill=False,
            auto_regenerate=bool(image_path and os.path.exists(str(image_path)))
        )
        pl = res_fix["plan"]
        learned_lines = "\n".join(f"  • {item}" for item in res_fix["learned_summary"]) or "  • *(Applied as a scene-specific fix for this image)*"
        gen_imgs = (res_fix.get("generation") or {}).get("images", [])
        mode_used = f"Img2Img (Denoise `{pl.get('recommended_denoise', 0.52)}` + FaceLock)" if pl.get("use_img2img") else "Fresh Txt2Img Redraw"
        return {
            "reply": (
                f"🔧 **AI Diagnosis & Correction ({mode_used}):**\n"
                f"• **Why it happened:** {pl.get('diagnosis')}\n"
                f"• **Repaired Prompt:** `{pl.get('corrected_prompt')}`\n"
                f"• **Repaired Negative:** `{pl.get('corrected_negative')}`\n\n"
                f"🧠 **Saved to Persistent Memory (`learned_memory.json`):**\n{learned_lines}"
            ),
            "images": gen_imgs,
            "learned_memory": res_fix["memory"]
        }

    # If an image is attached in chat: decide whether to EDIT it (Img2Img) or CHAT about it (Vision Q&A)
    if image_path and os.path.exists(str(image_path)):
        edit_keywords = (
            "/edit", "/draw", "change ", "make ", "turn ", "add ", "remove ", "replace ",
            "edit ", "modify", "restyle", "transform", "convert", "swap", "background",
            "color", "hair", "eyes", "outfit", "clothing", "wear", "wearing", "armor",
            "style", "lighting", "darker", "brighter", "more ", "less ", "fix ", "put ", "apply "
        )
        question_starters = (
            "what ", "who ", "where ", "why ", "how ", "describe", "tell me", "do you see", "can you see", "analyze", "explain"
        )
        is_pure_question = (
            (msg_lower.startswith(question_starters) or msg_lower.endswith("?"))
            and not any(k in msg_lower for k in ("/edit", "/draw", "change ", "add ", "make ", "remove ", "replace ", "put ", "apply "))
        )
        is_edit_request = (
            not is_pure_question
            and (
                action_mode in ("edit", "reactor")
                or (action_mode == "auto" and any(k in msg_lower for k in edit_keywords))
            )
        )

        if is_edit_request:
            clean_inst = user_message
            for prefix in ["/edit ", "/draw "]:
                if msg_lower.startswith(prefix):
                    clean_inst = user_message[len(prefix):].strip()
                    break
            is_reactor_mode = (action_mode == "reactor") or ("new pose" in msg_lower or "face lock" in msg_lower or "swap face" in msg_lower)
            log_agent(f"Chat Img2Img requested on {Path(image_path).name} (Original Face Anchor: {Path(orig_anchor).name}): '{clean_inst}' (denoise={denoise}, preserve_face={preserve_face}, reactor={is_reactor_mode})")
            new_prompt = build_edit_prompt_with_vision_ai(
                image_path,
                clean_inst,
                original_image_path=orig_anchor,
                chat_history=chat_history
            )
            orig_w, orig_h = get_image_dimensions(orig_anchor)
            best_w, best_h = nearest_sdxl_resolution(orig_w, orig_h)
            res = generate_image_via_comfy({
                "prompt": new_prompt,
                "input_image": image_path if not is_reactor_mode else "",
                "original_face_image": orig_anchor,
                "mask_image_b64": mask_image_b64 if not is_reactor_mode else "",
                "preserve_face": bool(preserve_face),
                "enable_reactor": is_reactor_mode,
                "denoise": float(denoise),
                "width": best_w,
                "height": best_h,
                "scale_to_resolution": True
            })
            face_badge = "🎭 **Brand-New Pose + ReActor Face-Lock** | " if is_reactor_mode else ("🎨 **Brush Mask Inpainting (100% Unpainted Face Locked)** | " if mask_image_b64 else ("🔒 **Original Facial Features Locked** | " if preserve_face else ""))
            return {
                "reply": (
                    f"✨ **Edited Image via Img2Img** ({face_badge}Denoise: `{denoise}`, Resolution: `{best_w}×{best_h}`, Seed: `{res['seed']}`)\n\n"
                    f"**Applied Prompt:** *{new_prompt}*"
                ),
                "images": res["images"]
            }
        else:
            # Vision Q&A about the attached image
            p = Path(image_path)
            mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            messages = [{"role": "system", "content": cfg["llm_system_prompt"]}]
            for h in chat_history[-6:]:
                messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
            messages.append({
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": user_message or "Describe this image in detail."}
                ]
            })
            reply = call_local_llm(messages)
            return {"reply": reply, "images": []}

    # Fast-path explicit tool triggers or let LLM decide
    if msg_lower.startswith("/draw ") or msg_lower.startswith("generate image:") or ("generate an image" in msg_lower or "draw " in msg_lower and "listing" not in msg_lower):
        # Extract image prompt
        clean_prompt = user_message
        for prefix in ["/draw ", "generate image:", "generate an image of", "generate an image", "draw a", "draw"]:
            if msg_lower.startswith(prefix):
                clean_prompt = user_message[len(prefix):].strip()
                break
        res = generate_image_via_comfy({"prompt": clean_prompt})
        return {
            "reply": f"Generated with **{cfg['default_checkpoint']}** (Seed: `{res['seed']}`):\n\nPrompt: *{clean_prompt}*",
            "images": res["images"]
        }

    messages = [{"role": "system", "content": cfg["llm_system_prompt"]}]
    for h in chat_history[-10:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": user_message})

    reply = call_local_llm(messages)
    return {"reply": reply, "images": []}

# ============================================================================
# WEB UI HTML (SINGLE-PAGE DASHBOARD)
# ============================================================================
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Local AI Hub — Image Studio & Marketplace Action Agent</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  :root {
    --bg: #0b0f19;
    --panel: #111827;
    --panel-alt: #1f2937;
    --border: #374151;
    --text: #f3f4f6;
    --muted: #9ca3af;
    --accent: #8b5cf6;
    --accent-hover: #7c3aed;
    --green: #10b981;
    --amber: #f59e0b;
    --red: #ef4444;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 24px;
    background: #0f172a;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
    gap: 12px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 18px;
    font-weight: 700;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 11px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    background: var(--panel-alt);
    border: 1px solid var(--border);
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); }
  .dot.on { background: var(--green); box-shadow: 0 0 8px var(--green); }
  nav {
    display: flex;
    gap: 8px;
    padding: 12px 24px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }
  nav button {
    background: transparent;
    color: var(--muted);
    border: 1px solid transparent;
    padding: 9px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
    font-size: 14px;
  }
  nav button.active {
    background: var(--accent);
    color: white;
  }
  main {
    max-width: 1520px;
    margin: 0 auto;
    padding: 18px 24px;
  }
  .tab { display: none; }
  .tab.active { display: block; }
  .studio-layout { display: grid; grid-template-columns: minmax(380px, 460px) minmax(0, 1fr); gap: 20px; align-items: start; }
  .crawl-ops-layout { display: grid; grid-template-columns: 280px minmax(0, 1fr) 390px; gap: 14px; align-items: start; }
  .hb-bar { display: flex; gap: 3px; flex-wrap: wrap; margin: 6px 0; }
  .hb-slot { width: 18px; height: 14px; border-radius: 3px; border: 1px solid #334155; cursor: pointer; background: #10b981; transition: 0.15s; }
  .hb-slot.damaged { background: #ef4444; border-color: #7f1d1d; }
  .grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
  .grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; align-items: start; }
  .grid-equal { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: start; }
  @media (max-width: 1180px) {
    .crawl-ops-layout { grid-template-columns: 1fr; }
  }
  @media (max-width: 1024px) {
    .studio-layout, .grid-2, .grid-equal { grid-template-columns: 1fr; }
    .grid-3 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 640px) {
    .grid-3 { grid-template-columns: 1fr; }
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 18px;
  }
  .card h3 { margin-top: 0; margin-bottom: 12px; font-size: 16px; }
  label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    margin-bottom: 5px;
    margin-top: 12px;
  }
  input, textarea, select {
    width: 100%;
    background: #0b0f19;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 9px 11px;
    border-radius: 8px;
    font-size: 13px;
    font-family: inherit;
  }
  textarea { resize: vertical; min-height: 80px; }
  .row { display: flex; gap: 10px; align-items: center; }
  .row > * { flex: 1; }
  .btn {
    background: var(--accent);
    color: white;
    border: none;
    padding: 10px 16px;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    font-size: 13px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }
  .btn:hover { background: var(--accent-hover); }
  .btn.secondary { background: var(--panel-alt); border: 1px solid var(--border); color: var(--text); }
  .btn.green { background: var(--green); color: #052e16; }
  .btn.amber { background: var(--amber); color: #111827; }
  .gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 14px;
  }
  .img-card {
    background: #0b0f19;
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }
  .img-card img {
    width: 100%;
    height: 280px;
    object-fit: cover;
    display: block;
    cursor: pointer;
  }
  .img-card .actions {
    padding: 8px;
    display: flex;
    gap: 6px;
  }
  .log-box {
    background: #050811;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    font-family: Consolas, monospace;
    font-size: 12px;
    color: #10b981;
    height: 220px;
    overflow-y: auto;
    white-space: pre-wrap;
  }
  .chat-box {
    height: 460px;
    overflow-y: auto;
    background: #070a12;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 12px;
  }
  .msg { margin-bottom: 14px; line-height: 1.5; font-size: 14px; }
  .msg.user { color: #c4b5fd; font-weight: 600; }
  .msg.assistant { color: #e5e7eb; background: var(--panel-alt); padding: 10px 14px; border-radius: 8px; }
  .step-item {
    background: #0b0f19;
    border: 1px solid var(--border);
    padding: 8px 12px;
    border-radius: 8px;
    margin-bottom: 6px;
    font-size: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
</style>
</head>
<body>

<header>
  <div class="brand">
    <span>🎲 TTRPG AI Studio &amp; DCC Hub</span>
    <span class="badge">RTX 4070 • Local Stack</span>
  </div>
  <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
    <div class="badge" id="comfy-badge"><span class="dot" id="comfy-dot"></span> ComfyUI: <span id="comfy-text">Checking...</span></div>
    <button class="btn secondary" onclick="startService('comfy')" style="padding:6px 10px; font-size:12px;">Start ComfyUI</button>
    <div class="badge" id="llm-badge"><span class="dot" id="llm-dot"></span> AI Compute: <span id="llm-text">Checking...</span></div>
    <button class="btn secondary" onclick="startService('llm')" style="padding:6px 10px; font-size:12px;">Start Local LLM</button>
    <button class="btn secondary" onclick="startService('unload_llm')" style="padding:6px 10px; font-size:12px;" title="Unload local LLM from RTX 4070 so ComfyUI gets 100% of your 12 GB VRAM">🧹 Free GPU VRAM</button>
    <button class="btn amber" onclick="openSetupWizard()" style="padding:6px 10px; font-size:12px;">🧙 Setup Wizard</button>
  </div>
</header>

<!-- FIRST-RUN SETUP WIZARD MODAL -->
<div id="setup-wizard-modal" style="display:none; position:fixed; inset:0; background:rgba(3,7,18,0.88); z-index:9999; overflow-y:auto; padding:24px;">
  <div class="card" style="max-width:860px; margin:20px auto; border-color:var(--accent); box-shadow:0 20px 50px rgba(0,0,0,0.6);">
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <h2 style="margin:0; color:#c4b5fd;">🧙 TTRPG AI Hub — First-Run Setup Wizard</h2>
      <button class="btn secondary" style="padding:4px 10px;" onclick="closeSetupWizard()">✖ Close</button>
    </div>
    <p style="font-size:13px; color:var(--muted); margin:6px 0 14px 0;">
      Configure how your AI Hub runs and drop your owned rulebook PDFs to unlock rulebook-cited DM Companion answers. Data Folder: <code id="wiz-data-dir"></code>
    </p>

    <div class="grid-3" style="gap:10px; margin-bottom:14px;">
      <div class="card" style="margin:0; padding:12px; border-color:#10b981; cursor:pointer;" onclick="selectWizardMode('local')">
        <label style="margin:0; display:flex; align-items:center; gap:6px; color:#6ee7b7; font-size:13px; cursor:pointer;">
          <input type="radio" name="wiz-mode" value="local" style="width:auto;"> 🏠 1. Fully Local AI
        </label>
        <div style="font-size:11px; color:var(--muted); margin-top:4px;">100% offline using Ollama (<code>qwen2.5:7b</code>) + optional local ComfyUI.</div>
      </div>
      <div class="card" style="margin:0; padding:12px; border-color:#38bdf8; cursor:pointer;" onclick="selectWizardMode('cloud')">
        <label style="margin:0; display:flex; align-items:center; gap:6px; color:#7dd3fc; font-size:13px; cursor:pointer;">
          <input type="radio" name="wiz-mode" value="cloud" style="width:auto;"> ☁️ 2. Fully Cloud AI
        </label>
        <div style="font-size:11px; color:var(--muted); margin-top:4px;">No GPU needed. Uses ChatGPT, Claude, or Gemini (+ Cloud Image fallback).</div>
      </div>
      <div class="card" style="margin:0; padding:12px; border-color:#f59e0b; cursor:pointer;" onclick="selectWizardMode('hybrid')">
        <label style="margin:0; display:flex; align-items:center; gap:6px; color:#fde68a; font-size:13px; cursor:pointer;">
          <input type="radio" name="wiz-mode" value="hybrid" checked style="width:auto;"> ⚡ 3. Hybrid Mode
        </label>
        <div style="font-size:11px; color:var(--muted); margin-top:4px;">Local primary with Cloud fallback (or Cloud primary + Local fallback).</div>
      </div>
    </div>

    <div id="wiz-local-box" class="card" style="padding:12px; background:#0b0f19; margin-bottom:12px;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <div>
          <b>🦙 Local Runtime (Ollama)</b> — <span id="wiz-ollama-status" style="color:var(--muted);">Checking...</span>
        </div>
        <div style="display:flex; gap:6px; align-items:center;">
          <input id="wiz-ollama-model" value="qwen2.5:7b" style="width:140px; padding:5px 8px; font-size:12px;">
          <button class="btn secondary" style="padding:5px 10px; font-size:12px;" onclick="pullOllamaFromWizard()">⬇️ Pull Qwen Model</button>
        </div>
      </div>
      <div id="wiz-ollama-pull" style="font-size:11px; color:#fde68a; margin-top:6px;"></div>
    </div>

    <div id="wiz-cloud-box" class="card" style="padding:12px; background:#0b0f19; margin-bottom:12px;">
      <b style="display:block; margin-bottom:8px;">☁️ Cloud AI Providers (ChatGPT • Claude • Gemini)</b>
      <div class="grid-2" style="gap:8px;">
        <div>
          <label style="margin-top:0;">Primary Cloud Provider</label>
          <select id="wiz-cloud-provider">
            <option value="gemini">Google Gemini (gemini-2.5-flash)</option>
            <option value="openai">OpenAI ChatGPT (gpt-4o-mini / gpt-image-1)</option>
            <option value="anthropic">Anthropic Claude (claude-sonnet-4-5)</option>
          </select>
        </div>
        <div>
          <label style="margin-top:0;">Gemini API Key</label>
          <input type="password" id="wiz-gemini-key" placeholder="AIzaSy...">
        </div>
        <div>
          <label style="margin-top:0;">OpenAI API Key (ChatGPT + Cloud Images)</label>
          <input type="password" id="wiz-openai-key" placeholder="sk-...">
        </div>
        <div>
          <label style="margin-top:0;">Anthropic API Key (Claude)</label>
          <input type="password" id="wiz-anthropic-key" placeholder="sk-ant-...">
        </div>
      </div>
    </div>

    <div class="card" style="padding:12px; background:#0b0f19; margin-bottom:14px;">
      <b style="display:block; margin-bottom:6px;">📚 Owned Rulebooks Check (Unlocks DM Companion Per System)</b>
      <div class="grid-3" style="gap:8px;">
        <div style="padding:8px; border:1px solid var(--border); border-radius:6px;">
          <div style="font-size:12px; font-weight:700;">💣 DCC TTRPG</div>
          <div id="wiz-rb-dcc" style="font-size:11px; margin:4px 0;">Checking...</div>
          <input type="file" accept=".pdf" onchange="uploadRulebookPdf('dcc', this)" style="font-size:10px; padding:3px;">
        </div>
        <div style="padding:8px; border:1px solid var(--border); border-radius:6px;">
          <div style="font-size:12px; font-weight:700;">🐉 D&amp;D 5e</div>
          <div id="wiz-rb-dnd5e" style="font-size:11px; margin:4px 0;">Checking...</div>
          <input type="file" accept=".pdf" onchange="uploadRulebookPdf('dnd5e', this)" style="font-size:10px; padding:3px;">
        </div>
        <div style="padding:8px; border:1px solid var(--border); border-radius:6px;">
          <div style="font-size:12px; font-weight:700;">🚀 SW5e</div>
          <div id="wiz-rb-sw5e" style="font-size:11px; margin:4px 0;">Checking...</div>
          <input type="file" accept=".pdf" onchange="uploadRulebookPdf('sw5e', this)" style="font-size:10px; padding:3px;">
        </div>
      </div>
    </div>

    <div style="display:flex; justify-content:flex-end; gap:10px;">
      <button class="btn" style="background:#10b981; color:#042f2e; font-weight:700;" onclick="saveAndFinishWizard()">✅ Save &amp; Launch Hub</button>
    </div>
  </div>
</div>

<nav>
  <button class="active" onclick="switchTab('studio', this)">🎨 Image Studio</button>
  <button onclick="switchTab('chat', this)">💬 Agent Chat</button>
  <button id="nav-btn-dcc" onclick="switchTab('dcc', this)">🎲 DCC Sheet & Journal</button>
  <button id="nav-btn-sw5e" onclick="switchTab('sw5e', this)">🚀 SW5e Sheet &amp; Ship</button>
  <button id="nav-btn-dnd5e" onclick="switchTab('dnd5e', this)">🐉 D&amp;D 5e Sheet</button>
  <button id="nav-btn-campaign" onclick="switchTab('campaign', this)">🗺️ Campaign Organizer</button>
  <button onclick="switchTab('models', this)">📦 Models & Settings</button>
</nav>

<main>
  <!-- TAB 1: IMAGE STUDIO -->
  <section id="tab-studio" class="tab active">
    <div class="studio-layout">
      <div class="card">
        <h3>Generate or Edit Image (Local ComfyUI Engine)</h3>

        <div style="margin-bottom:12px; padding:12px; background:#0b0f19; border:1px solid var(--accent); border-radius:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
            <label style="margin:0; color:#c4b5fd; font-size:13px;">⚡ Studio Skill (Created in Agent Chat)</label>
            <div style="display:flex; gap:6px;">
              <button class="btn secondary" style="padding:4px 9px; font-size:11px;" onclick="startSkillPromptInChat()">💬 + Create Skill in Agent Chat</button>
              <button class="btn secondary" id="btn-del-skill" style="display:none; padding:4px 9px; font-size:11px; border-color:var(--red); color:#fca5a5;" onclick="deleteSelectedStudioSkill()" title="Delete this Studio Skill">🗑️</button>
            </div>
          </div>
          <select id="gen-skill" onchange="onSelectStudioSkill()" style="margin-top:8px;">
            <option value="">None (Standard Manual Settings)</option>
          </select>
          <div id="gen-skill-desc" style="font-size:11px; color:var(--muted); margin-top:6px; line-height:1.4;">
            Select a skill to auto-apply its lighting, framing, negative prompt, SDXL resolution, steps, CFG, and prompt enhancer rules — or create your own in <b>Agent Chat</b>!
          </div>
        </div>

        <label>Checkpoint Model</label>
        <select id="gen-ckpt"></select>

        <label>Optional LoRA</label>
        <div class="row">
          <select id="gen-lora"><option value="">None</option></select>
          <input type="number" id="gen-lora-str" value="0.8" step="0.1" min="0" max="2" style="max-width:90px;" title="LoRA Strength">
        </div>

        <!-- TTRPG RULESET PORTRAIT PRESET BUILDER (DROPDOWNS) -->
        <div style="margin-top:14px; padding:12px; background:#070a13; border:1px solid #4338ca; border-radius:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:6px;">
            <span style="font-size:12px; font-weight:700; color:#c4b5fd;">⚔️ TTRPG Character Portrait Builder</span>
            <div style="display:flex; gap:6px;">
              <button type="button" class="btn secondary" style="padding:3px 9px; font-size:11px;" onclick="randomizeTtrpgPreset()">🎲 Randomize</button>
              <button type="button" class="btn" style="padding:3px 10px; font-size:11px; background:#10b981; color:#042f2e; font-weight:700;" onclick="applyTtrpgPreset()">✨ Apply to Prompt</button>
            </div>
          </div>
          <div class="grid-2" style="gap:8px;">
            <div>
              <label style="margin:0 0 3px 0; font-size:11px;">Ruleset</label>
              <select id="ttrpg-ruleset" onchange="onRulesetChange()" style="font-size:12px;">
                <option value="dnd5e">🐉 D&amp;D 5e (Fantasy)</option>
                <option value="sw5e">🚀 SW5e (Star Wars 5e)</option>
                <option value="dcc">💣 Dungeon Crawler Carl TTRPG</option>
              </select>
            </div>
            <div>
              <label style="margin:0 0 3px 0; font-size:11px;">Art Style</label>
              <select id="ttrpg-style" onchange="applyTtrpgPreset()" style="font-size:12px;">
                <option value="ruleset_auto">✨ Ruleset Signature Style (Auto)</option>
                <option value="oil_painting">🎨 Classic Oil Painting</option>
                <option value="vtt_token">🪙 VTT Token Bust (1024×1024)</option>
                <option value="grimdark_ink">🖌️ Grimdark Ink &amp; Watercolor</option>
                <option value="comic_cover">💥 Pulp / LitRPG Cover Art</option>
              </select>
            </div>
            <div>
              <label style="margin:0 0 3px 0; font-size:11px;">Race / Species</label>
              <select id="ttrpg-race" onchange="applyTtrpgPreset()" style="font-size:12px;"></select>
            </div>
            <div>
              <label style="margin:0 0 3px 0; font-size:11px;">Class</label>
              <select id="ttrpg-class" onchange="applyTtrpgPreset()" style="font-size:12px;"></select>
            </div>
          </div>
          <div style="margin-top:8px;">
            <label style="margin:0 0 3px 0; font-size:11px;">Backdrop</label>
            <select id="ttrpg-backdrop" onchange="applyTtrpgPreset()" style="font-size:12px;"></select>
          </div>
        </div>

        <div style="margin-top:14px; padding:12px; background:#0b0f19; border:1px dashed var(--accent); border-radius:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <label style="margin:0; color:#c4b5fd; font-size:13px;">🖼️ Input Image to Edit / Modify (Img2Img — Optional)</label>
            <button class="btn secondary" id="btn-clear-studio-img" onclick="clearStudioInputImage()" style="display:none; padding:3px 8px; font-size:11px;">✖ Clear Image</button>
          </div>
          <div style="font-size:11px; color:var(--muted); margin:6px 0 8px 0; line-height:1.5;">
            <b>Best SDXL Resolutions for Optimal Results:</b><br>
            • <code>1024×1024</code> (1:1 Square) &nbsp;|&nbsp; • <code>832×1216</code> (2:3 Portrait) &nbsp;|&nbsp; • <code>896×1152</code> (3:4 Vertical)<br>
            • <code>1216×832</code> (3:2 Landscape) &nbsp;|&nbsp; • <code>1152×896</code> (4:3 Horizontal) &nbsp;|&nbsp; • <code>1344×768</code> (16:9 Wide)<br>
            <span style="color:#10b981;">(Any size works — we can auto-fit it to the nearest SDXL resolution below!)</span>
          </div>
          <input type="file" id="studio-input-file" accept="image/*" onchange="uploadStudioInputImage()">
          <div id="studio-img-preview-box" style="display:none; margin-top:10px;">
            <div style="display:flex; gap:12px; align-items:flex-start; flex-wrap:wrap;">
              <div style="position:relative; display:inline-block;">
                <div style="position:relative; width:220px; border-radius:8px; overflow:hidden; border:2px solid var(--accent); background:#000;">
                  <img id="studio-img-preview" src="" style="width:220px; display:block; object-fit:contain;">
                  <canvas id="studio-mask-canvas" style="position:absolute; top:0; left:0; width:100%; height:100%; cursor:crosshair; touch-action:none;"></canvas>
                </div>
                <div style="display:flex; gap:6px; align-items:center; margin-top:6px; flex-wrap:wrap;">
                  <button type="button" class="btn secondary" id="btn-mask-mode-brush" onclick="setStudioMaskMode('brush')" style="padding:3px 7px; font-size:11px; background:var(--accent); color:#fff;">🖌️ Brush</button>
                  <button type="button" class="btn secondary" id="btn-mask-mode-eraser" onclick="setStudioMaskMode('eraser')" style="padding:3px 7px; font-size:11px;">🧽 Eraser</button>
                  <button type="button" class="btn secondary" onclick="clearStudioMask()" style="padding:3px 7px; font-size:11px; color:#fca5a5;">✖ Clear Mask</button>
                  <span style="font-size:10px; color:var(--muted);">Size:</span>
                  <input type="range" id="studio-brush-size" min="8" max="70" value="28" style="width:65px; padding:0;" oninput="updateStudioBrushSizeLabel(this.value)">
                  <span id="studio-brush-size-val" style="font-size:10px; color:#c4b5fd;">28px</span>
                </div>
              </div>
              <div style="flex:1; min-width:200px; font-size:12px;">
                <div id="studio-img-info" style="color:var(--green); font-weight:600; margin-bottom:4px;"></div>
                <div id="studio-mask-status-badge" style="display:inline-block; padding:3px 8px; border-radius:6px; background:#1e1b4b; color:#a7f3d0; font-size:11px; margin-bottom:6px; border:1px solid #4338ca;">
                  🎨 <b>Brush Mask Inpaint Mode Ready:</b> Paint where you want the new elements. Unpainted areas stay 100% original photo!
                </div>
                <label style="margin-top:2px;">Inpaint Denoise Strength: <span id="studio-denoise-val" style="color:var(--amber);">0.80</span></label>
                <input type="range" id="gen-denoise" min="0.15" max="0.95" step="0.05" value="0.80" oninput="document.getElementById('studio-denoise-val').textContent=parseFloat(this.value).toFixed(2)" style="padding:0;">
                <div style="font-size:10px; color:var(--muted);">0.75 - 0.88 = High creative power inside your painted brush strokes (swaps armor, weapons, scars, or details seamlessly)</div>
              </div>
            </div>
            <div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">
              <input type="text" id="studio-edit-instruction" placeholder="What went wrong or needs changing? (e.g. 'fix extra fingers, skin is too shiny, make hair silver')" style="font-size:12px; flex:1; min-width:220px;">
              <button class="btn secondary" style="padding:6px 10px; font-size:11px; white-space:nowrap;" onclick="describeOrEditInputImage()">🔍 Write Prompt Only</button>
              <button class="btn amber" id="btn-fix-teach" style="padding:6px 12px; font-size:11px; white-space:nowrap;" onclick="fixAndTeachFromStudio()">🔧 Fix & Teach AI Now</button>
            </div>
            <div style="display:flex; gap:14px; flex-wrap:wrap; margin-top:8px; font-size:12px;">
              <label style="display:flex; align-items:center; gap:6px; margin:0; color:#6ee7b7; font-weight:600;">
                <input type="checkbox" id="gen-preserve-face" checked style="width:auto;"> 🔒 Preserve Original Face (Lock Facial Features)
              </label>
              <label style="display:flex; align-items:center; gap:6px; margin:0; color:#f472b6; font-weight:600;" title="Full-Pose Identity Lock using ReActor InsightFace swap + CodeFormer face restoration">
                <input type="checkbox" id="gen-enable-reactor" style="width:auto;"> 🎭 ReActor Identity Swap (Brand-New Poses / Angles)
              </label>
              <label style="display:flex; align-items:center; gap:6px; margin:0; color:#c4b5fd; font-weight:400;">
                <input type="checkbox" id="chk-learn-global" checked style="width:auto;"> 🧠 Remember general quality/style lesson in Persistent Memory
              </label>
              <label style="display:flex; align-items:center; gap:6px; margin:0; color:var(--text); font-weight:400;">
                <input type="checkbox" id="chk-learn-skill" checked style="width:auto;"> ⚡ Also update active Studio Skill (if selected)
              </label>
              <label style="display:flex; align-items:center; gap:6px; margin:0; color:var(--text); font-weight:400;">
                <input type="checkbox" id="gen-scale-res" checked style="width:auto;"> Auto-fit to SDXL Preset
              </label>
            </div>
            <div id="studio-fix-diagnosis" style="display:none; margin-top:8px; padding:8px 10px; background:#111827; border-left:3px solid var(--green); border-radius:6px; font-size:11px; line-height:1.5;"></div>
          </div>
        </div>

        <label>Prompt</label>
        <textarea id="gen-prompt" rows="4" placeholder="Describe what you want to generate (or what the edited image should look like)..."></textarea>
        <div style="margin-top:6px; display:flex; justify-content:flex-end; gap:8px;">
          <button class="btn secondary" id="btn-undo-enhance" style="display:none; padding:5px 10px; font-size:11px;" onclick="undoEnhancePrompt()">↩️ Undo Enhance</button>
          <button class="btn secondary" style="padding:5px 10px; font-size:11px;" onclick="enhancePrompt()">✨ Enhance Prompt with Local AI</button>
        </div>

        <label>Negative Prompt</label>
        <textarea id="gen-neg" rows="2">bad hands, extra fingers, mutated hands, poorly drawn face, blurry, watermark, text, signature, low quality, worst quality, deformed, ugly</textarea>

        <div class="row">
          <div>
            <label>Resolution Preset</label>
            <select id="gen-res">
              <option value="1024x1024">1024 × 1024 (1:1 Square SDXL)</option>
              <option value="832x1216" selected>832 × 1216 (2:3 Portrait SDXL)</option>
              <option value="896x1152">896 × 1152 (3:4 Vertical SDXL)</option>
              <option value="1216x832">1216 × 832 (3:2 Landscape SDXL)</option>
              <option value="1152x896">1152 × 896 (4:3 Horizontal SDXL)</option>
              <option value="1344x768">1344 × 768 (16:9 Widescreen SDXL)</option>
              <option value="768x1344">768 × 1344 (9:16 Tall Vertical SDXL)</option>
            </select>
          </div>
          <div>
            <label>Batch Count</label>
            <input type="number" id="gen-batch" value="1" min="1" max="4">
          </div>
        </div>

        <div class="row">
          <div>
            <label>Steps</label>
            <input type="number" id="gen-steps" value="28" min="10" max="60">
          </div>
          <div>
            <label>CFG Scale</label>
            <input type="number" id="gen-cfg" value="5.5" step="0.5" min="1" max="15">
          </div>
          <div>
            <label>Seed (-1 = Random)</label>
            <input type="number" id="gen-seed" value="-1">
          </div>
        </div>

        <div class="row">
          <div>
            <label>Sampler</label>
            <select id="gen-sampler">
              <option value="dpmpp_2m_sde" selected>dpmpp_2m_sde (Recommended for Juggernaut)</option>
              <option value="euler_ancestral">euler_ancestral</option>
              <option value="dpmpp_2m">dpmpp_2m</option>
              <option value="euler">euler</option>
            </select>
          </div>
          <div>
            <label>Scheduler</label>
            <select id="gen-scheduler">
              <option value="karras" selected>karras</option>
              <option value="normal">normal</option>
              <option value="sgm_uniform">sgm_uniform</option>
            </select>
          </div>
        </div>

        <button class="btn" id="btn-generate" onclick="generateImage()" style="width:100%; margin-top:18px; padding:13px; font-size:15px;">
          🚀 Generate Image Now
        </button>
        <div id="gen-status" style="margin-top:10px; font-size:13px; color:var(--amber);"></div>

        <div style="margin-top:16px; padding:12px; background:#0b0f19; border:1px solid var(--border); border-radius:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <label style="display:flex; align-items:center; gap:8px; margin:0; color:#c4b5fd; font-size:13px;">
              <input type="checkbox" id="chk-use-learned-memory" checked onchange="toggleLearnedMemoryEnabled()" style="width:auto;">
              🧠 Persistent Correction Memory (`learned_memory.json`)
            </label>
            <button class="btn secondary" style="padding:4px 9px; font-size:11px;" onclick="toggleMemoryEditor()">⚙️ View / Edit Learned Rules</button>
          </div>
          <div id="learned-memory-summary" style="font-size:11px; color:var(--muted); margin-top:6px; line-height:1.5;">
            Loading learned rules...
          </div>
          <div id="learned-memory-editor" style="display:none; margin-top:10px; padding-top:10px; border-top:1px solid var(--border);">
            <label style="margin-top:4px;">Learned Positive Boosts (one per line — auto-added to prompts)</label>
            <textarea id="mem-pos-boosts" rows="3" style="font-size:12px; font-family:Consolas,monospace;"></textarea>
            <label style="margin-top:8px;">Learned Negative Blocks (one per line — auto-added to negative prompt)</label>
            <textarea id="mem-neg-blocks" rows="3" style="font-size:12px; font-family:Consolas,monospace;"></textarea>
            <label style="margin-top:8px;">Learned Style & Anatomy Lessons (one per line — guides AI Prompt Enhancer)</label>
            <textarea id="mem-lessons" rows="3" style="font-size:12px; font-family:Consolas,monospace;"></textarea>
            <button class="btn green" style="margin-top:8px; width:100%; padding:8px; font-size:12px;" onclick="saveLearnedMemoryFromUI()">💾 Save Learned Memory Rules</button>
          </div>
        </div>
      </div>

      <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; gap:8px; flex-wrap:wrap;">
          <h3 style="margin:0;">Generated Gallery (`C:\AI_Workspace\outputs\images`)</h3>
          <div style="display:flex; gap:8px;">
            <button class="btn secondary" onclick="loadGallery()">🔄 Refresh</button>
            <button class="btn secondary" style="border-color:var(--red); color:#fca5a5;" onclick="deleteAllGalleryImages()">🗑️ Delete All</button>
          </div>
        </div>
        <div class="gallery" id="image-gallery"></div>
      </div>
    </div>
  </section>

  <!-- TAB 4: AGENT CHAT -->
  <section id="tab-chat" class="tab">
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:6px;">
        <h3 style="margin:0;">Agent Chat, Image Editor & Skill Creator</h3>
        <button class="btn amber" style="padding:6px 12px; font-size:12px;" onclick="insertSkillTemplate()">⚡ + Create New Image Studio Skill</button>
      </div>
      <p style="font-size:13px; color:var(--muted); margin-top:0;">
        Chat with your AI, generate images with <code>/draw ...</code>, attach an image to edit it, or <b>teach Image Studio a reusable Skill</b> by typing <code>/skill [describe style, lighting, or workflow]</code> (or saying <i>"Create a studio skill for..."</i> — you can even attach a reference photo!).
      </p>
      <div class="chat-box" id="chat-box">
        <div class="msg assistant">Ready! I'm connected to your local ComfyUI SDXL engine for <b>TTRPG Character Portraits</b>.<br>• <b>Generate Portraits:</b> Type <code>/draw ...</code> or use the quick presets below to create heroes, villains, and NPCs.<br>• <b>Edit Portraits:</b> Attach a character portrait below and tell me what to change (e.g. <i>"give them scarred plate armor and a stormy castle background"</i>).<br>• <b>Create Image Studio Skills:</b> Type <code>/skill ...</code> or say <i>"Create a studio skill for Watercolor Fantasy Portraits"</i> — it will appear immediately in the <b>🎨 Image Studio</b> dropdown!</div>
      </div>

      <!-- TTRPG RULESET PORTRAIT PRESET BUILDER (AGENT CHAT PARITY) -->
      <div style="margin-bottom:10px; padding:12px; background:#070a13; border:1px solid #4338ca; border-radius:10px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:6px;">
          <span style="font-size:12px; font-weight:700; color:#c4b5fd;">⚔️ TTRPG Character Portrait Builder (D&amp;D 5e • SW5e • DCC)</span>
          <div style="display:flex; gap:6px;">
            <button type="button" class="btn secondary" style="padding:4px 9px; font-size:11px;" onclick="randomizeTtrpgPreset('chat')">🎲 Randomize</button>
            <button type="button" class="btn" style="padding:4px 10px; font-size:11px; background:#10b981; color:#042f2e; font-weight:700;" onclick="applyTtrpgPreset('chat')">✨ Load into Chat</button>
          </div>
        </div>
        <div class="grid-3" style="gap:8px;">
          <div>
            <label style="margin:0 0 3px 0; font-size:11px;">Ruleset</label>
            <select id="chat-ttrpg-ruleset" onchange="onRulesetChange('chat')" style="font-size:12px;">
              <option value="dnd5e">🐉 D&amp;D 5e (Fantasy)</option>
              <option value="sw5e">🚀 SW5e (Star Wars 5e)</option>
              <option value="dcc">💣 Dungeon Crawler Carl TTRPG</option>
            </select>
          </div>
          <div>
            <label style="margin:0 0 3px 0; font-size:11px;">Art Style</label>
            <select id="chat-ttrpg-style" onchange="applyTtrpgPreset('chat')" style="font-size:12px;">
              <option value="ruleset_auto">✨ Ruleset Signature Style (Auto)</option>
              <option value="oil_painting">🎨 Classic Oil Painting</option>
              <option value="vtt_token">🪙 VTT Token Bust (1024×1024)</option>
              <option value="grimdark_ink">🖌️ Grimdark Ink &amp; Watercolor</option>
              <option value="comic_cover">💥 Pulp / LitRPG Cover Art</option>
            </select>
          </div>
          <div>
            <label style="margin:0 0 3px 0; font-size:11px;">Race / Species</label>
            <select id="chat-ttrpg-race" onchange="applyTtrpgPreset('chat')" style="font-size:12px;"></select>
          </div>
          <div>
            <label style="margin:0 0 3px 0; font-size:11px;">Class</label>
            <select id="chat-ttrpg-class" onchange="applyTtrpgPreset('chat')" style="font-size:12px;"></select>
          </div>
          <div style="grid-column: span 2;">
            <label style="margin:0 0 3px 0; font-size:11px;">Backdrop</label>
            <select id="chat-ttrpg-backdrop" onchange="applyTtrpgPreset('chat')" style="font-size:12px;"></select>
          </div>
        </div>
      </div>

      <div style="background:#0b0f19; border:1px solid var(--border); border-radius:10px; padding:10px 14px; margin-bottom:10px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
          <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <label style="margin:0; color:#c4b5fd; font-size:12px;">📎 Attach Image to Edit, Analyze, or Turn into a Studio Skill:</label>
            <input type="file" id="chat-file" accept="image/*" onchange="uploadChatImage()" style="width:auto; padding:5px 8px; font-size:12px;">
            <button class="btn secondary" id="btn-reset-chat-orig" onclick="resetChatToOriginalImage()" style="display:none; padding:4px 9px; font-size:11px; border-color:var(--green); color:#6ee7b7;">↩️ Reset Canvas to Original Photo</button>
            <button class="btn secondary" id="btn-clear-chat-img" onclick="clearChatImage()" style="display:none; padding:4px 9px; font-size:11px;">✖ Remove Attached Image</button>
          </div>
          <div style="font-size:11px; color:var(--muted);">
            <b>Best SDXL Sizes:</b> <code>1024×1024</code> • <code>832×1216</code> • <code>896×1152</code> • <code>1216×832</code> • <code>1344×768</code> (auto-fitted automatically)
          </div>
        </div>

        <div id="chat-img-controls" style="display:none; margin-top:10px; padding-top:10px; border-top:1px solid var(--border); align-items:flex-start; gap:14px; flex-wrap:wrap;">
          <div style="position:relative; width:140px; border-radius:8px; overflow:hidden; border:2px solid var(--accent); background:#000;">
            <img id="chat-img-preview" src="" style="width:140px; display:block; object-fit:contain;">
            <canvas id="chat-mask-canvas" style="position:absolute; top:0; left:0; width:100%; height:100%; cursor:crosshair; touch-action:none;"></canvas>
          </div>
          <div style="flex:1; min-width:260px;">
            <div style="display:flex; gap:6px; align-items:center; margin-bottom:8px; flex-wrap:wrap;">
              <button type="button" class="btn secondary" id="btn-chat-mask-brush" onclick="setChatMaskMode('brush')" style="padding:3px 7px; font-size:11px; background:var(--accent); color:#fff;">🖌️ Paint Inpaint Zone</button>
              <button type="button" class="btn secondary" id="btn-chat-mask-eraser" onclick="setChatMaskMode('eraser')" style="padding:3px 7px; font-size:11px;">🧽 Eraser</button>
              <button type="button" class="btn secondary" onclick="clearChatMask()" style="padding:3px 7px; font-size:11px; color:#fca5a5;">✖ Clear Mask</button>
              <span style="font-size:10px; color:var(--muted);">Size:</span>
              <input type="range" id="chat-brush-size" min="6" max="60" value="22" style="width:55px; padding:0;" oninput="updateChatBrushSizeLabel(this.value)">
              <span id="chat-brush-size-val" style="font-size:10px; color:#c4b5fd;">22px</span>
            </div>
            <div id="chat-img-meta" style="font-size:12px; color:var(--green); font-weight:600; margin-bottom:6px;"></div>
            <div style="display:flex; gap:12px; flex-wrap:wrap; align-items:center;">
              <label style="display:flex; align-items:center; gap:6px; margin:0; color:#6ee7b7; font-size:12px; font-weight:600;">
                <input type="checkbox" id="chat-preserve-face" checked style="width:auto;"> 🔒 Lock Unpainted Pixels & Face
              </label>
              <div style="display:flex; align-items:center; gap:8px;">
                <label style="margin:0;">Mode:</label>
                <select id="chat-img-mode" style="width:auto;">
                  <option value="edit" selected>🎨 Edit / Inpaint Image (ComfyUI)</option>
                  <option value="reactor">🎭 Brand-New Pose + ReActor Face-Lock</option>
                  <option value="fix">🔧 Fix Flawed Image & Teach AI Rule</option>
                  <option value="skill">⚡ Extract Style & Save as Studio Skill</option>
                  <option value="chat">👁️ Just Ask / Chat (Vision Q&A)</option>
                  <option value="auto">🤖 Auto-Detect</option>
                </select>
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <label style="margin:0;">Inpaint Denoise: <span id="chat-denoise-val" style="color:var(--amber);">0.80</span></label>
                <input type="range" id="chat-denoise" min="0.20" max="0.95" step="0.05" value="0.80" oninput="document.getElementById('chat-denoise-val').textContent=parseFloat(this.value).toFixed(2)" style="width:110px; padding:0;">
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:8px; padding:8px 12px; background:#0b0f19; border:1px solid #10b981; border-radius:8px;">
        <div style="display:flex; gap:14px; flex-wrap:wrap; align-items:center;">
          <label style="display:flex; align-items:center; gap:6px; margin:0; color:#fde68a; font-size:12px; font-weight:700; cursor:pointer;">
            <input type="checkbox" id="chat-dm-mode" style="width:auto;" onchange="onChatModeToggle('dm')">
            🧙 DM Companion Mode
          </label>
          <select id="chat-dm-system" style="width:auto; padding:4px 8px; font-size:12px; border-color:#f59e0b;">
            <option value="dnd5e">🐉 D&amp;D 5e Rules</option>
            <option value="sw5e">🚀 SW5e Rules</option>
            <option value="dcc">💣 DCC TTRPG Rules</option>
          </select>
          <label style="display:flex; align-items:center; gap:6px; margin:0; color:#6ee7b7; font-size:12px; font-weight:600; cursor:pointer;">
            <input type="checkbox" id="chat-dcc-mode" style="width:auto;" onchange="onChatModeToggle('dcc')">
            🎲 DCC Session 0
          </label>
          <label style="display:flex; align-items:center; gap:6px; margin:0; color:#38bdf8; font-size:12px; font-weight:600; cursor:pointer;">
            <input type="checkbox" id="chat-sw5e-mode" style="width:auto;" onchange="onChatModeToggle('sw5e')">
            🚀 SW5e Session 0
          </label>
          <label style="display:flex; align-items:center; gap:6px; margin:0; color:#fca5a5; font-size:12px; font-weight:600; cursor:pointer;">
            <input type="checkbox" id="chat-dnd5e-mode" style="width:auto;" onchange="onChatModeToggle('dnd5e')">
            🐉 5e Session 0
          </label>
        </div>
        <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
          <span id="rules-rag-status" style="font-size:11px; color:var(--muted);">📚 Rules: checking...</span>
          <button type="button" class="btn secondary" style="padding:4px 8px; font-size:11px;" onclick="reindexRulesNow()" title="Scan C:\AI_Workspace\Rules for new or updated PDFs">🔄 Re-Index</button>
          <button type="button" class="btn secondary" style="padding:4px 9px; font-size:11px; border-color:#10b981; color:#a7f3d0;" onclick="prefillDccPrompt()">✨ /dcc</button>
          <button type="button" class="btn secondary" style="padding:4px 9px; font-size:11px; border-color:#38bdf8; color:#bae6fd;" onclick="prefillSw5ePrompt()">✨ /sw5e</button>
          <button type="button" class="btn secondary" style="padding:4px 9px; font-size:11px; border-color:#ef4444; color:#fecaca;" onclick="prefillDnd5ePrompt()">✨ /dnd5e</button>
        </div>
      </div>

      <div class="row">
        <input type="text" id="chat-input" placeholder="Ask DM rules/encounter questions, type '/dm ...', '/dcc ...', '/sw5e ...', '/skill ...', or '/draw ...'..." onkeydown="if(event.key==='Enter') sendChat()">
        <button class="btn" id="btn-chat-send" onclick="sendChat()" style="max-width:140px;">Send</button>
      </div>
    </div>
  </section>

  <!-- TAB: DCC SHEET & JOURNAL -->
  <section id="tab-dcc" class="tab">
    <div class="card" style="margin-bottom:14px; border-color:#10b981;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div>
          <h3 style="margin:0; color:#6ee7b7;">🎲 Dungeon Crawler World — Session 0 Sheet & Journal Builder</h3>
          <div style="font-size:12px; color:var(--muted); margin-top:4px;">
            Chat in <b>💬 Agent Chat</b> with <code>/dcc</code> (or toggle DCC Mode) to auto-fill, tweak stats/attacks/skills here, pick an Image Studio portrait, and export print-ready PDFs.
          </div>
        </div>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
          <select id="dcc-saved-select" onchange="loadSelectedDccCharacter()" style="width:auto; min-width:180px;">
            <option value="">-- New Crawler --</option>
          </select>
          <button class="btn secondary" onclick="newDccCharacter()">🆕 New</button>
          <button class="btn" onclick="saveDccCharacter()">💾 Save</button>
          <button class="btn secondary" style="color:#fca5a5;" onclick="deleteDccCharacter()">🗑️ Delete</button>
        </div>
      </div>
    </div>

    <div class="grid-2">
      <!-- LEFT COLUMN: IDENTITY, STATS, VITALS, PORTRAIT -->
      <div>
        <div class="card" style="margin-bottom:14px;">
          <h3>1. Identity &amp; Meta</h3>
          <div class="grid-2" style="gap:8px;">
            <div><label>Crawler Name</label><input id="dcc-name" placeholder="Carl"></div>
            <div><label>Race</label><input id="dcc-race" value="Human"></div>
            <div><label>Gender / Pronouns</label><input id="dcc-gender" placeholder="He/Him"></div>
            <div><label>Class</label><input id="dcc-class" value="None"></div>
            <div><label>Level</label><input id="dcc-level" value="0"></div>
            <div><label>Crawler Number</label><input id="dcc-number" placeholder="4122"></div>
            <div><label>Floor</label><input id="dcc-floor" value="1"></div>
            <div><label>Size</label><input id="dcc-size" value="Medium"></div>
            <div><label>Move</label><input id="dcc-move" value="30 ft"></div>
            <div><label>Step</label><input id="dcc-step" value="5 ft"></div>
            <div><label>AI Favor</label><input id="dcc-aifavor" value="1"></div>
            <div><label>Popularity (CHA Mod × 2)</label><input id="dcc-popularity" readonly style="background:#0b0f19; color:#fde68a;"></div>
          </div>
        </div>

        <div class="card" style="margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h3 style="margin:0;">2. Core Stats &amp; Vitals</h3>
            <button class="btn secondary" style="padding:4px 10px; font-size:11px;" onclick="recalcDccCharacter()">🧮 Recalculate</button>
          </div>
          <table style="width:100%; border-collapse:collapse; margin-top:10px; font-size:12px;">
            <thead>
              <tr style="color:var(--muted); text-align:left; border-bottom:1px solid var(--border);">
                <th style="padding:4px;">Stat</th><th style="padding:4px;">Unenhanced</th><th style="padding:4px;">Enhanced</th><th style="padding:4px;">Mod</th>
              </tr>
            </thead>
            <tbody>
              <tr><td><b>STR</b></td><td><input type="number" id="dcc-str-un" value="4" onchange="recalcDccCharacter()"></td><td><input type="number" id="dcc-str-en" value="4" onchange="recalcDccCharacter()"></td><td><input id="dcc-str-mod" value="+2" readonly style="width:55px; text-align:center; background:#0b0f19; color:#6ee7b7;"></td></tr>
              <tr><td><b>INT</b></td><td><input type="number" id="dcc-int-un" value="4" onchange="recalcDccCharacter()"></td><td><input type="number" id="dcc-int-en" value="4" onchange="recalcDccCharacter()"></td><td><input id="dcc-int-mod" value="+2" readonly style="width:55px; text-align:center; background:#0b0f19; color:#6ee7b7;"></td></tr>
              <tr><td><b>CON</b></td><td><input type="number" id="dcc-con-un" value="4" onchange="recalcDccCharacter()"></td><td><input type="number" id="dcc-con-en" value="4" onchange="recalcDccCharacter()"></td><td><input id="dcc-con-mod" value="+2" readonly style="width:55px; text-align:center; background:#0b0f19; color:#6ee7b7;"></td></tr>
              <tr><td><b>DEX</b></td><td><input type="number" id="dcc-dex-un" value="4" onchange="recalcDccCharacter()"></td><td><input type="number" id="dcc-dex-en" value="4" onchange="recalcDccCharacter()"></td><td><input id="dcc-dex-mod" value="+2" readonly style="width:55px; text-align:center; background:#0b0f19; color:#6ee7b7;"></td></tr>
              <tr><td><b>CHA</b></td><td><input type="number" id="dcc-cha-un" value="4" onchange="recalcDccCharacter()"></td><td><input type="number" id="dcc-cha-en" value="4" onchange="recalcDccCharacter()"></td><td><input id="dcc-cha-mod" value="+2" readonly style="width:55px; text-align:center; background:#0b0f19; color:#6ee7b7;"></td></tr>
            </tbody>
          </table>

          <div class="grid-3" style="gap:8px; margin-top:10px;">
            <div><label>HP Current</label><input type="number" id="dcc-hp-cur" value="14"></div>
            <div><label>HP Max</label><input type="number" id="dcc-hp-max" value="14"></div>
            <div><label>Evade Total</label><input type="number" id="dcc-evade-tot" value="12" readonly style="background:#0b0f19; color:#6ee7b7;"></div>
            <div><label>Mana Current</label><input type="number" id="dcc-mana-cur" value="9"></div>
            <div><label>Mana Max</label><input type="number" id="dcc-mana-max" value="9"></div>
            <div><label>Evade Buffs</label><input type="number" id="dcc-evade-buff" value="0" onchange="recalcDccCharacter()"></div>
            <div><label>DR Armor</label><input type="number" id="dcc-dr-armor" value="0" onchange="recalcDccCharacter()"></div>
            <div><label>DR Buffs</label><input type="number" id="dcc-dr-buff" value="0" onchange="recalcDccCharacter()"></div>
            <div><label>DR Total</label><input type="number" id="dcc-dr-tot" value="0" readonly style="background:#0b0f19; color:#6ee7b7;"></div>
          </div>

          <div style="margin-top:10px;">
            <label>External Buffs (Max 3)</label>
            <div class="grid-3" style="gap:6px;">
              <input id="dcc-buff-1" placeholder="Buff 1">
              <input id="dcc-buff-2" placeholder="Buff 2">
              <input id="dcc-buff-3" placeholder="Buff 3">
            </div>
          </div>
        </div>

        <div class="card">
          <h3>3. Character Portrait (Journal Page 3 Green Border &amp; Sheet Page 1)</h3>
          <div style="display:flex; gap:12px; align-items:flex-start; flex-wrap:wrap;">
            <div style="width:120px; height:170px; border:2px solid #41ad49; border-radius:6px; background:#0b0f19; display:flex; align-items:center; justify-content:center; overflow:hidden;">
              <img id="dcc-portrait-preview" src="" style="max-width:100%; max-height:100%; object-fit:contain; display:none;">
              <span id="dcc-portrait-empty" style="font-size:11px; color:var(--muted); text-align:center; padding:6px;">No portrait selected</span>
            </div>
            <div style="flex:1; min-width:200px;">
              <label>Portrait Disk Path</label>
              <input id="dcc-portrait-path" placeholder="Select from Image Studio Gallery below...">
              <div style="display:flex; gap:8px; margin-top:8px; flex-wrap:wrap;">
                <button class="btn secondary" onclick="refreshDccPortraitGallery()">🖼️ Pick from Gallery</button>
                <button class="btn secondary" onclick="switchTab('studio', document.querySelector('nav button'))">🎨 Open Image Studio</button>
                <button class="btn secondary" style="color:#fca5a5;" onclick="clearDccPortrait()">✖ Clear</button>
              </div>
              <div id="dcc-portrait-gallery" style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; max-height:140px; overflow-y:auto;"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- RIGHT COLUMN: ATTACKS, SKILLS, GEAR, EXPORT -->
      <div>
        <div class="card" style="margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h3 style="margin:0;">4. Attacks (Sheet Page 1 &amp; Journal Page 5)</h3>
            <button class="btn secondary" style="padding:4px 10px; font-size:11px;" onclick="addDccAttackRow()">+ Add Attack</button>
          </div>
          <div id="dcc-attacks-list" style="margin-top:8px; display:flex; flex-direction:column; gap:6px;"></div>
        </div>

        <div class="card" style="margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h3 style="margin:0;">5. Trained Skills (Rank 1+ Only)</h3>
            <button class="btn secondary" style="padding:4px 10px; font-size:11px;" onclick="addDccSkillRow()">+ Add Skill</button>
          </div>
          <div id="dcc-skills-list" style="margin-top:8px; display:flex; flex-direction:column; gap:6px;"></div>
        </div>

        <div class="card" style="margin-bottom:14px;">
          <h3>6. Gear &amp; Backstory</h3>
          <div class="grid-3" style="gap:6px;">
            <div><label>Head</label><input id="dcc-gear-head"></div>
            <div><label>Torso</label><input id="dcc-gear-torso"></div>
            <div><label>Arms</label><input id="dcc-gear-arms"></div>
            <div><label>Hands</label><input id="dcc-gear-hands"></div>
            <div><label>Legs</label><input id="dcc-gear-legs"></div>
            <div><label>Feet</label><input id="dcc-gear-feet"></div>
          </div>
          <label style="margin-top:6px;">Accessories (Max 10)</label>
          <input id="dcc-gear-acc">
          <div class="grid-3" style="gap:6px; margin-top:6px;">
            <div><label>Past Trauma</label><input id="dcc-trauma"></div>
            <div><label>Loose Ends</label><input id="dcc-loose"></div>
            <div><label>Regrets</label><input id="dcc-regrets"></div>
          </div>
          <label style="margin-top:6px;">Notes</label>
          <textarea id="dcc-notes" rows="2"></textarea>
        </div>

        <div class="card" style="margin-bottom:14px; border-color:#8b5cf6;">
          <h3>7. Export Printable PDFs (Session 0)</h3>
          <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
            <button class="btn" style="background:#10b981; color:#042f2e; font-weight:700;" onclick="exportDccPdfs(true, true)">📄 Export Both (Sheet + Journal PDF)</button>
            <button class="btn secondary" onclick="exportDccPdfs(true, false)">📄 Sheet Only</button>
            <button class="btn secondary" onclick="exportDccPdfs(false, true)">📘 Journal Only</button>
          </div>
          <div id="dcc-export-status" style="margin-top:10px; font-size:12px;"></div>
        </div>

        <details class="card">
          <summary style="cursor:pointer; font-weight:600; color:#c4b5fd;">⚙️ Rulebook Table 2 Mod Brackets &amp; Vital Formulas</summary>
          <div style="font-size:11px; color:var(--muted); margin:8px 0;">
            Verified from rules: <code>4-5 → +2</code>. Adjust remaining brackets/formulas against Rulebook p. 57 if needed:
          </div>
          <textarea id="dcc-rules-json" rows="8" style="font-family:monospace; font-size:11px;"></textarea>
          <button class="btn secondary" style="margin-top:8px;" onclick="saveDccRulesConfig()">💾 Save Rulebook Config</button>
        </details>
      </div>
    </div>
  </section>

  <!-- TAB: SW5E CHARACTER & STARSHIP -->
  <section id="tab-sw5e" class="tab">
    <div class="card" style="margin-bottom:14px; border-color:#38bdf8;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div>
          <h3 style="margin:0; color:#7dd3fc;">🚀 Star Wars 5e (SW5e) — Character &amp; Separate Starship Builder</h3>
          <div style="font-size:12px; color:var(--muted); margin-top:4px;">
            Chat in <b>💬 Agent Chat</b> with <code>/sw5e</code> (or toggle SW5e Mode) to generate a Character &amp; Starship, refine stats below, and export both separate fillable PDFs.
          </div>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn" style="background:#38bdf8; color:#082f49; font-weight:700;" onclick="exportSw5ePdfs(true, true)">📄 Export Both (Character + Ship PDFs)</button>
        </div>
      </div>
      <div id="sw5e-export-status" style="margin-top:8px; font-size:12px;"></div>
    </div>

    <div class="grid-2">
      <!-- LEFT: SW5E CHARACTER SHEET -->
      <div>
        <div class="card" style="margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
            <h3 style="margin:0; color:#7dd3fc;">🧑 SW5e Character Sheet</h3>
            <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
              <select id="sw5e-char-select" onchange="loadSelectedSw5eChar()" style="width:auto; min-width:150px;">
                <option value="">-- New Character --</option>
              </select>
              <button class="btn secondary" style="padding:6px 10px;" onclick="newSw5eChar()">🆕</button>
              <button class="btn" style="padding:6px 10px;" onclick="saveSw5eChar()">💾 Save</button>
              <button class="btn secondary" style="padding:6px 10px; color:#fca5a5;" onclick="deleteSw5eChar()">🗑️</button>
            </div>
          </div>

          <div class="grid-3" style="gap:8px;">
            <div><label>Character Name</label><input id="sw5e-c-name" placeholder="Kaelen Voss"></div>
            <div><label>Species</label><input id="sw5e-c-species" value="Human"></div>
            <div><label>Class</label><input id="sw5e-c-class" value="Operative"></div>
            <div><label>Level</label><input type="number" id="sw5e-c-level" value="1" min="1" max="20" onchange="recalcSw5eChar()"></div>
            <div><label>Background</label><input id="sw5e-c-bg" value="Scoundrel"></div>
            <div><label>Alignment</label><input id="sw5e-c-align" value="Balanced/Gray"></div>
            <div><label>Size</label><input id="sw5e-c-size" value="Medium"></div>
            <div><label>Speed</label><input id="sw5e-c-speed" value="30 ft."></div>
            <div><label>Deployment Role</label><input id="sw5e-c-role" value="Pilot (Rank 0)"></div>
            <div><label>Starting Feat</label><input id="sw5e-c-feat" placeholder="Charmer"></div>
            <div><label>Credits (cr)</label><input id="sw5e-c-credits" value="1000"></div>
            <div><label>Player Name</label><input id="sw5e-c-player"></div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:12px;">
            <b style="font-size:12px; color:#c4b5fd;">Ability Scores (Mod = ⌊(Score−10)/2⌋)</b>
            <button class="btn secondary" style="padding:3px 9px; font-size:11px;" onclick="recalcSw5eChar()">🧮 Recalculate</button>
          </div>
          <div class="grid-3" style="gap:6px; margin-top:6px;">
            <div><label>STR (<span id="sw5e-c-str-m">+0</span>)</label><input type="number" id="sw5e-c-str" value="10" onchange="recalcSw5eChar()"></div>
            <div><label>DEX (<span id="sw5e-c-dex-m">+2</span>)</label><input type="number" id="sw5e-c-dex" value="15" onchange="recalcSw5eChar()"></div>
            <div><label>CON (<span id="sw5e-c-con-m">+2</span>)</label><input type="number" id="sw5e-c-con" value="14" onchange="recalcSw5eChar()"></div>
            <div><label>INT (<span id="sw5e-c-int-m">+1</span>)</label><input type="number" id="sw5e-c-int" value="12" onchange="recalcSw5eChar()"></div>
            <div><label>WIS (<span id="sw5e-c-wis-m">+0</span>)</label><input type="number" id="sw5e-c-wis" value="10" onchange="recalcSw5eChar()"></div>
            <div><label>CHA (<span id="sw5e-c-cha-m">+1</span>)</label><input type="number" id="sw5e-c-cha" value="13" onchange="recalcSw5eChar()"></div>
          </div>

          <div class="grid-3" style="gap:8px; margin-top:8px;">
            <div><label>AC</label><input type="number" id="sw5e-c-ac" value="13"></div>
            <div><label>HP Current / Max</label><div class="row" style="gap:4px;"><input type="number" id="sw5e-c-hpcur" value="10"><input type="number" id="sw5e-c-hpmax" value="10"></div></div>
            <div><label>Hit Dice</label><input id="sw5e-c-hd" value="1d8"></div>
            <div><label>Force Points</label><input type="number" id="sw5e-c-fp" value="0"></div>
            <div><label>Tech Points</label><input type="number" id="sw5e-c-tp" value="0"></div>
            <div><label>Armor Notes</label><input id="sw5e-c-armor" value="Combat Suit"></div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:12px;">
            <b style="font-size:12px; color:#c4b5fd;">Weapons (Blasters / Vibroweapons / Lightweapons)</b>
            <button class="btn secondary" style="padding:3px 9px; font-size:11px;" onclick="addSw5eCharWeapon()">+ Weapon</button>
          </div>
          <div id="sw5e-c-weapons" style="display:flex; flex-direction:column; gap:5px; margin-top:6px;"></div>

          <div class="grid-2" style="gap:8px; margin-top:8px;">
            <div><label>Skill Proficiencies (comma-separated)</label><input id="sw5e-c-skills" value="Piloting, Stealth, Perception, Deception"></div>
            <div><label>Save Proficiencies (comma-separated)</label><input id="sw5e-c-saves" value="DEX, INT"></div>
          </div>
          <label>Languages</label><input id="sw5e-c-langs" value="Galactic Basic">
          <div class="grid-2" style="gap:8px; margin-top:6px;">
            <div><label>Features &amp; Traits (1 per line)</label><textarea id="sw5e-c-features" rows="3"></textarea></div>
            <div><label>Equipment &amp; Powers (1 per line)</label><textarea id="sw5e-c-equip" rows="3"></textarea></div>
          </div>
          <button class="btn secondary" style="width:100%; margin-top:10px; border-color:#38bdf8; color:#bae6fd;" onclick="exportSw5ePdfs(true, false)">📄 Export Character PDF Only</button>
        </div>
      </div>

      <!-- RIGHT: SW5E STARSHIP SHEET -->
      <div>
        <div class="card" style="margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
            <h3 style="margin:0; color:#fde68a;">🛸 SW5e Starship Sheet</h3>
            <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
              <select id="sw5e-ship-select" onchange="loadSelectedSw5eShip()" style="width:auto; min-width:150px;">
                <option value="">-- New Starship --</option>
              </select>
              <button class="btn secondary" style="padding:6px 10px;" onclick="newSw5eShip()">🆕</button>
              <button class="btn" style="padding:6px 10px;" onclick="saveSw5eShip()">💾 Save</button>
              <button class="btn secondary" style="padding:6px 10px; color:#fca5a5;" onclick="deleteSw5eShip()">🗑️</button>
            </div>
          </div>

          <div class="grid-3" style="gap:8px;">
            <div><label>Ship Name</label><input id="sw5e-s-name" placeholder="The Kessel Runner"></div>
            <div>
              <label>Size Category</label>
              <select id="sw5e-s-size" onchange="recalcSw5eShip()">
                <option value="Tiny">Tiny (10 mods)</option>
                <option value="Small">Small (20 mods)</option>
                <option value="Medium" selected>Medium (30 mods)</option>
                <option value="Large">Large (50 mods)</option>
                <option value="Huge">Huge (60 mods)</option>
                <option value="Gargantuan">Gargantuan (70 mods)</option>
              </select>
            </div>
            <div><label>Tier (0–5)</label><input type="number" id="sw5e-s-tier" value="0" min="0" max="5" onchange="recalcSw5eShip()"></div>
            <div><label>Model / Chassis</label><input id="sw5e-s-model" value="YT-1300f Light Freighter"></div>
            <div><label>Manufacturer</label><input id="sw5e-s-mfg" value="Corellian Engineering Corp."></div>
            <div><label>Role Specialization (Tier 2+)</label><input id="sw5e-s-role" value="None (Tier 0)"></div>
            <div><label>Flying Speed</label><input id="sw5e-s-fly" value="300 ft."></div>
            <div><label>Turning Speed</label><input id="sw5e-s-turn" value="200 ft."></div>
            <div><label>Hyperdrive Class</label><input id="sw5e-s-hyper" value="Class 2.0 (Backup 12)"></div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:12px;">
            <b style="font-size:12px; color:#fde68a;">Starship Ability Scores</b>
            <button class="btn secondary" style="padding:3px 9px; font-size:11px;" onclick="recalcSw5eShip()">🧮 Recalculate</button>
          </div>
          <div class="grid-3" style="gap:6px; margin-top:6px;">
            <div><label>STR (<span id="sw5e-s-str-m">+2</span>)</label><input type="number" id="sw5e-s-str" value="14" onchange="recalcSw5eShip()"></div>
            <div><label>DEX (<span id="sw5e-s-dex-m">+1</span>)</label><input type="number" id="sw5e-s-dex" value="12" onchange="recalcSw5eShip()"></div>
            <div><label>CON (<span id="sw5e-s-con-m">+2</span>)</label><input type="number" id="sw5e-s-con" value="14" onchange="recalcSw5eShip()"></div>
            <div><label>INT (<span id="sw5e-s-int-m">+1</span>)</label><input type="number" id="sw5e-s-int" value="12" onchange="recalcSw5eShip()"></div>
            <div><label>WIS (<span id="sw5e-s-wis-m">+0</span>)</label><input type="number" id="sw5e-s-wis" value="10" onchange="recalcSw5eShip()"></div>
            <div><label>CHA (<span id="sw5e-s-cha-m">+0</span>)</label><input type="number" id="sw5e-s-cha" value="10" onchange="recalcSw5eShip()"></div>
          </div>

          <div class="grid-3" style="gap:8px; margin-top:8px;">
            <div><label>AC / DR</label><div class="row" style="gap:4px;"><input type="number" id="sw5e-s-ac" value="14"><input id="sw5e-s-dr" value="4"></div></div>
            <div><label>Hull (HP Cur / Max)</label><div class="row" style="gap:4px;"><input type="number" id="sw5e-s-hpcur" value="36"><input type="number" id="sw5e-s-hpmax" value="36"></div></div>
            <div><label>Shields (SP Cur / Max)</label><div class="row" style="gap:4px;"><input type="number" id="sw5e-s-spcur" value="36"><input type="number" id="sw5e-s-spmax" value="36"></div></div>
            <div><label>Hull Dice</label><input id="sw5e-s-hd" value="3d8"></div>
            <div><label>Shield Dice</label><input id="sw5e-s-sd" value="3d8"></div>
            <div><label>Mod Cap / Max Suites</label><input id="sw5e-s-caps" value="30 / 7" readonly style="background:#0b0f19; color:#fde68a;"></div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:12px;">
            <b style="font-size:12px; color:#fde68a;">Ship Armaments (Up to 4)</b>
            <button class="btn secondary" style="padding:3px 9px; font-size:11px;" onclick="addSw5eShipWeapon()">+ Hardpoint</button>
          </div>
          <div id="sw5e-s-weapons" style="display:flex; flex-direction:column; gap:5px; margin-top:6px;"></div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:12px;">
            <b style="font-size:12px; color:#fde68a;">Crew Assignments (Page 4)</b>
            <button class="btn secondary" style="padding:3px 9px; font-size:11px;" onclick="addSw5eCrewRow()">+ Crew</button>
          </div>
          <div id="sw5e-s-crew" style="display:flex; flex-direction:column; gap:5px; margin-top:6px;"></div>

          <label>Installed Modifications &amp; Suites (1 per line: Name | Type | Price | Notes)</label>
          <textarea id="sw5e-s-mods" rows="3" placeholder="Smuggler's Compartment | Suite | 5,000 cr | Hidden cargo"></textarea>

          <button class="btn secondary" style="width:100%; margin-top:10px; border-color:#f59e0b; color:#fde68a;" onclick="exportSw5ePdfs(false, true)">🛸 Export Starship PDF Only</button>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB: CAMPAIGN ORGANIZER (DCC CRAWLOPS) -->
  <section id="tab-campaign" class="tab">
    <div class="card" style="margin-bottom:14px; border-color:#f59e0b;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div>
          <h3 style="margin:0; color:#fde68a;">🗺️ Multi-System Campaign Organizer (DCC • D&amp;D 5e • SW5e)</h3>
          <div style="font-size:12px; color:var(--muted); margin-top:4px;">
            Two-way synced with <code>C:\AI_Workspace\campaign_vault\</code> &amp; <code>campaign_ops.db</code>. Switch rulesets to manage Hubs, Nodes, Beats, Entities, and Loot.
          </div>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
          <select id="camp-system" onchange="switchCampaignSystem()" style="width:auto; font-weight:700; border-color:#f59e0b; color:#fde68a;">
            <option value="dcc">💣 DCC CrawlOps</option>
            <option value="dnd5e">🐉 D&amp;D 5e CampaignOps</option>
            <option value="sw5e">🚀 SW5e CampaignOps</option>
          </select>
          <input type="file" id="camp-md-file" accept=".md,.txt" onchange="uploadCampaignMarkdown()" style="width:auto; padding:5px 8px; font-size:11px;">
          <button class="btn secondary" onclick="scanVaultSourceDocs()" title="Ingest all .md files in campaign_vault/source_docs">📂 Scan Vault</button>
          <button class="btn amber" onclick="exportSessionRunbookNow()">📘 Export Runbook</button>
        </div>
      </div>
      <div id="camp-status" style="font-size:12px; color:#6ee7b7; margin-top:6px;"></div>
    </div>

    <div class="crawl-ops-layout">
      <!-- LEFT PANE: FLOOR -> NODE TREE -->
      <div class="card" style="padding:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <h3 style="margin:0; font-size:14px;">🏢 Floors &amp; Nodes</h3>
          <button class="btn secondary" style="padding:3px 8px; font-size:11px;" onclick="toggleCampForm('hub')">+ Floor</button>
        </div>
        <div id="camp-add-hub-form" style="display:none; margin-bottom:10px; padding:8px; background:#0b0f19; border:1px solid var(--border); border-radius:8px;">
          <input id="camp-hub-name" placeholder="Floor 3: Over City — Heavensworth" style="margin-bottom:5px;">
          <div class="row" style="gap:5px;">
            <input type="number" id="camp-hub-floor" value="3" placeholder="Floor F">
            <input type="number" id="camp-hub-timer" value="240" placeholder="Timer (hrs)">
          </div>
          <input id="camp-hub-faction" placeholder="Controlling Faction / Boss" style="margin-top:5px;">
          <button class="btn" style="width:100%; margin-top:6px; padding:6px;" onclick="saveCampHub()">Save Floor / Hub</button>
        </div>
        <div id="camp-tree-list" style="display:flex; flex-direction:column; gap:8px; max-height:680px; overflow-y:auto;"></div>
      </div>

      <!-- CENTER PANE: NODE WORKSPACE, BEATS & LOOT -->
      <div>
        <div class="card" style="margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <h3 id="camp-node-title" style="margin:0; color:#c4b5fd;">Select a Floor or Micro Node</h3>
            <div style="display:flex; gap:6px;">
              <button class="btn secondary" style="padding:4px 9px; font-size:11px;" onclick="toggleCampForm('node')">+ Node</button>
              <button class="btn secondary" style="padding:4px 9px; font-size:11px;" onclick="toggleCampForm('beat')">+ Beat</button>
            </div>
          </div>
          <div id="camp-node-meta" style="font-size:12px; color:var(--muted); margin-top:4px;"></div>

          <div id="camp-add-node-form" style="display:none; margin-top:10px; padding:10px; background:#0b0f19; border:1px solid var(--border); border-radius:8px;">
            <div class="grid-3" style="gap:6px;">
              <input id="camp-node-name" placeholder="Node Name (e.g. The One-Eyed Narwhal)">
              <select id="camp-node-type">
                <option>Saferoom</option><option>Desperado Venue</option><option>Club Vanquisher</option>
                <option>Guild Hall</option><option>Shop</option><option>Tavern</option><option>Train Station</option><option>Encounter Zone</option>
              </select>
              <select id="camp-node-marker">
                <option>White Dot</option><option>Red Dot</option><option>Blue Dot</option><option>Purple Dot</option><option>Cross</option><option>Star</option>
              </select>
            </div>
            <textarea id="camp-node-desc" rows="2" placeholder="Node description..." style="margin-top:6px;"></textarea>
            <input id="camp-node-map" placeholder="Projector Battlemap Prompt (optional)" style="margin-top:6px;">
            <button class="btn" style="margin-top:6px;" onclick="saveCampNode()">Save Micro Node</button>
          </div>

          <div id="camp-add-beat-form" style="display:none; margin-top:10px; padding:10px; background:#0b0f19; border:1px solid var(--border); border-radius:8px;">
            <div class="grid-3" style="gap:6px;">
              <input id="camp-beat-title" placeholder="Beat Title">
              <select id="camp-beat-type"><option>Exploration</option><option>Social</option><option>Combat</option><option>Quest</option><option>Boss</option><option>Interview Show</option></select>
              <select id="camp-beat-loot"><option>Bronze</option><option>Silver</option><option>Gold</option><option>Platinum</option><option>Legendary</option><option>Celestial</option></select>
            </div>
            <textarea id="camp-beat-ai" rows="2" placeholder="[SYSTEM AI ANNOUNCEMENT] Read-aloud box..." style="margin-top:6px;"></textarea>
            <textarea id="camp-beat-gm" rows="2" placeholder="GM Notes..." style="margin-top:6px;"></textarea>
            <button class="btn" style="margin-top:6px;" onclick="saveCampBeat()">Save Session Beat</button>
          </div>

          <div id="camp-node-body" style="margin-top:10px; font-size:13px;"></div>
          <div id="camp-node-actions" style="display:none; gap:8px; flex-wrap:wrap; margin-top:10px;">
            <button class="btn secondary" style="padding:5px 10px; font-size:11px;" onclick="copyProjectorPrompt()">📋 Copy Projector Map Prompt</button>
            <button class="btn secondary" style="padding:5px 10px; font-size:11px;" onclick="sendMapPromptToStudio()">🎨 Render Map in Studio</button>
          </div>
        </div>

        <div class="card" style="margin-bottom:14px;">
          <h3 style="margin-bottom:8px;">🎬 Session Beats</h3>
          <div id="camp-beats-list" style="display:flex; flex-direction:column; gap:8px;"></div>
        </div>

        <div class="card">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <h3 style="margin:0;">🎁 Floor-Scaled Loot Box &amp; Achievement Roller</h3>
            <div style="display:flex; gap:6px; align-items:center;">
              <select id="camp-loot-tier" style="width:auto; padding:4px 8px; font-size:12px;">
                <option>Bronze</option><option>Silver</option><option>Gold</option><option>Platinum</option><option>Legendary</option><option>Celestial</option>
              </select>
              <button class="btn amber" style="padding:5px 10px; font-size:12px;" onclick="rollCampLootBox()">🎲 Roll Box</button>
            </div>
          </div>
          <input id="camp-loot-reason" placeholder="Reason / Achievement trigger (e.g. 'Barefoot goblin curb-stomp')" style="margin-top:8px;">
          <pre id="camp-loot-output" style="display:none; margin-top:8px; background:#0b0f19; border:1px solid #f59e0b; padding:10px; border-radius:8px; white-space:pre-wrap; font-size:12px; color:#fde68a;"></pre>
        </div>
      </div>

      <!-- RIGHT PANE: POPULATE NODE & PERSISTENT ENTITIES -->
      <div>
        <div class="card" style="margin-bottom:14px; border-color:#10b981;">
          <h3 style="margin-bottom:8px; color:#6ee7b7;">✨ Populate Active Node</h3>
          <div class="row" style="gap:6px;">
            <input type="number" id="camp-pop-count" value="2" min="1" max="4" style="max-width:65px;" title="Count (1-4)">
            <input id="camp-pop-mix" value="1 Bopca Merchant + 1 Rival GMC" placeholder="Category mix">
          </div>
          <select id="camp-pop-beat" style="margin-top:6px; font-size:12px;">
            <option value="">📍 Persistent in Node (Shopkeeper / Resident)</option>
          </select>
          <input id="camp-pop-hint" placeholder="Optional GM hint (e.g. 'Shady potions dealer')" style="margin-top:6px;">
          <button class="btn" style="width:100%; margin-top:8px; background:#10b981; color:#042f2e; font-weight:700;" onclick="populateActiveNodeNow()">⚡ Generate &amp; Bind Entities to Node</button>
        </div>

        <div class="card">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; gap:6px;">
            <h3 style="margin:0;">👾 Entities (<span id="camp-ent-count">0</span>)</h3>
            <select id="camp-ent-filter" style="width:auto; padding:3px 6px; font-size:11px;" onchange="renderCampaignWorkspace()">
              <option value="beat">🎬 Selected Beat (or Node)</option>
              <option value="node">📍 All in Node</option>
              <option value="all">🗺️ All in Campaign</option>
            </select>
          </div>
          <div id="camp-entities-list" style="display:flex; flex-direction:column; gap:10px; max-height:640px; overflow-y:auto;"></div>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB: D&D 5E CHARACTER SHEET -->
  <section id="tab-dnd5e" class="tab">
    <div class="card" style="margin-bottom:14px; border-color:#ef4444;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div>
          <h3 style="margin:0; color:#fca5a5;">🐉 D&amp;D 5th Edition — Session 0 Character Sheet Builder</h3>
          <div style="font-size:12px; color:var(--muted); margin-top:4px;">
            Chat in <b>💬 Agent Chat</b> with <code>/dnd5e</code> (or toggle 🐉 5e Session 0) to generate a character, tweak stats/spells below, pick a portrait, and export the printable 3-page 5e PDF.
          </div>
        </div>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
          <select id="dnd5e-saved-select" onchange="loadSelectedDnd5eChar()" style="width:auto; min-width:170px;">
            <option value="">-- New 5e Character --</option>
          </select>
          <button class="btn secondary" onclick="newDnd5eChar()">🆕 New</button>
          <button class="btn" onclick="saveDnd5eChar()">💾 Save</button>
          <button class="btn secondary" style="color:#fca5a5;" onclick="deleteDnd5eChar()">🗑️</button>
          <button class="btn" style="background:#ef4444; color:#fff; font-weight:700;" onclick="exportDnd5ePdf()">📄 Export Printable 5e PDF</button>
        </div>
      </div>
      <div id="dnd5e-export-status" style="margin-top:8px; font-size:12px;"></div>
    </div>

    <div class="grid-2">
      <div>
        <div class="card" style="margin-bottom:14px;">
          <h3>1. Identity &amp; Combat Vitals</h3>
          <div class="grid-3" style="gap:8px;">
            <div><label>Character Name</label><input id="dnd5e-name" placeholder="Lyra Nightbreeze"></div>
            <div><label>Race</label><input id="dnd5e-race" value="Human"></div>
            <div><label>Class</label><input id="dnd5e-class" value="Fighter"></div>
            <div><label>Level</label><input type="number" id="dnd5e-level" value="1" min="1" max="20" onchange="recalcDnd5eChar()"></div>
            <div><label>Background</label><input id="dnd5e-bg" value="Soldier"></div>
            <div><label>Alignment</label><input id="dnd5e-align" value="Neutral Good"></div>
            <div><label>Player Name</label><input id="dnd5e-player"></div>
            <div><label>XP</label><input id="dnd5e-xp" value="0"></div>
            <div><label>Speed</label><input id="dnd5e-speed" value="30 ft."></div>
            <div><label>Armor Class</label><input type="number" id="dnd5e-ac" value="16"></div>
            <div><label>HP Cur / Max</label><div class="row" style="gap:4px;"><input type="number" id="dnd5e-hpcur" value="12"><input type="number" id="dnd5e-hpmax" value="12"></div></div>
            <div><label>Hit Dice</label><input id="dnd5e-hd" value="1d10"></div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:12px;">
            <b style="font-size:12px; color:#fca5a5;">Ability Scores (Mod = ⌊(Score−10)/2⌋)</b>
            <button class="btn secondary" style="padding:3px 9px; font-size:11px;" onclick="recalcDnd5eChar()">🧮 Recalculate</button>
          </div>
          <div class="grid-3" style="gap:6px; margin-top:6px;">
            <div><label>STR (<span id="dnd5e-str-m">+2</span>)</label><input type="number" id="dnd5e-str" value="15" onchange="recalcDnd5eChar()"></div>
            <div><label>DEX (<span id="dnd5e-dex-m">+2</span>)</label><input type="number" id="dnd5e-dex" value="14" onchange="recalcDnd5eChar()"></div>
            <div><label>CON (<span id="dnd5e-con-m">+2</span>)</label><input type="number" id="dnd5e-con" value="14" onchange="recalcDnd5eChar()"></div>
            <div><label>INT (<span id="dnd5e-int-m">+0</span>)</label><input type="number" id="dnd5e-int" value="10" onchange="recalcDnd5eChar()"></div>
            <div><label>WIS (<span id="dnd5e-wis-m">+1</span>)</label><input type="number" id="dnd5e-wis" value="12" onchange="recalcDnd5eChar()"></div>
            <div><label>CHA (<span id="dnd5e-cha-m">-1</span>)</label><input type="number" id="dnd5e-cha" value="8" onchange="recalcDnd5eChar()"></div>
          </div>

          <div class="grid-2" style="gap:8px; margin-top:8px;">
            <div><label>Skill Proficiencies (comma-separated)</label><input id="dnd5e-skills" value="Athletics, Intimidation, Perception"></div>
            <div><label>Save Proficiencies (comma-separated)</label><input id="dnd5e-saves" value="STR, CON"></div>
          </div>
        </div>

        <div class="card">
          <h3>2. Character Portrait (Page 2 Appearance Box)</h3>
          <div style="display:flex; gap:12px; align-items:flex-start; flex-wrap:wrap;">
            <div style="width:110px; height:150px; border:2px solid #ef4444; border-radius:6px; background:#0b0f19; display:flex; align-items:center; justify-content:center; overflow:hidden;">
              <img id="dnd5e-portrait-preview" src="" style="max-width:100%; max-height:100%; object-fit:contain; display:none;">
              <span id="dnd5e-portrait-empty" style="font-size:11px; color:var(--muted); text-align:center; padding:6px;">No portrait</span>
            </div>
            <div style="flex:1; min-width:190px;">
              <label>Portrait Disk Path</label>
              <input id="dnd5e-portrait-path" placeholder="Pick from Gallery below...">
              <div style="display:flex; gap:6px; margin-top:6px;">
                <button class="btn secondary" style="padding:4px 9px; font-size:11px;" onclick="refreshDnd5ePortraitGallery()">🖼️ Refresh Gallery</button>
                <button class="btn secondary" style="padding:4px 9px; font-size:11px; color:#fca5a5;" onclick="setDnd5ePortraitPath('')">✖ Clear</button>
              </div>
              <div id="dnd5e-portrait-gallery" style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; max-height:120px; overflow-y:auto;"></div>
            </div>
          </div>
        </div>
      </div>

      <div>
        <div class="card" style="margin-bottom:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h3 style="margin:0;">3. Attacks, Gear &amp; Features</h3>
            <button class="btn secondary" style="padding:3px 9px; font-size:11px;" onclick="addDnd5eWeapon()">+ Weapon (max 3)</button>
          </div>
          <div id="dnd5e-weapons" style="display:flex; flex-direction:column; gap:5px; margin-top:8px;"></div>

          <div class="grid-2" style="gap:8px; margin-top:8px;">
            <div><label>Proficiencies &amp; Languages</label><textarea id="dnd5e-profs" rows="3"></textarea></div>
            <div><label>Equipment &amp; Gold (GP)</label><div style="display:flex; gap:6px; margin-bottom:4px;"><input id="dnd5e-gp" value="10" style="max-width:70px;" title="GP"><span style="font-size:11px; color:var(--muted); align-self:center;">GP</span></div><textarea id="dnd5e-equip" rows="2"></textarea></div>
          </div>
          <label>Features &amp; Traits</label><textarea id="dnd5e-features" rows="3"></textarea>
          <div class="grid-2" style="gap:8px; margin-top:6px;">
            <div><label>Personality Traits</label><input id="dnd5e-traits"></div>
            <div><label>Ideals / Bonds / Flaws</label><input id="dnd5e-ideals" placeholder="Ideals"></div>
          </div>
        </div>

        <div class="card">
          <h3>4. Spellcasting (Page 3)</h3>
          <div class="grid-3" style="gap:8px;">
            <div><label>Spellcasting Class</label><input id="dnd5e-sp-class" placeholder="Wizard"></div>
            <div>
              <label>Casting Ability</label>
              <select id="dnd5e-sp-ab">
                <option value="">None</option><option value="INT">INT</option><option value="WIS">WIS</option><option value="CHA">CHA</option>
              </select>
            </div>
            <div><label>1st / 2nd Slots</label><div class="row" style="gap:4px;"><input id="dnd5e-sp-s1" placeholder="2"><input id="dnd5e-sp-s2" placeholder="0"></div></div>
          </div>
          <label>Cantrips (comma-separated)</label><input id="dnd5e-sp-cantrips" placeholder="Fire Bolt, Mage Hand">
          <label>1st Level Spells (comma-separated)</label><input id="dnd5e-sp-lvl1" placeholder="Magic Missile, Shield">
          <label>2nd Level Spells (comma-separated)</label><input id="dnd5e-sp-lvl2" placeholder="">
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 5: MODELS & SETTINGS -->
  <section id="tab-models" class="tab">
    <div class="card" style="border-color:var(--accent);">
      <h3>⚡ Hybrid Compute Engine — Gemini API (`BLOCK_NONE`) + Local GPU</h3>
      <p style="font-size:13px; color:var(--muted); margin-top:0;">
        Offload Vision AI, DCC character sheet creation, prompt optimization, and chat to your <b>Gemini API Key</b> with all configurable safety thresholds set to <code>BLOCK_NONE</code> (`HARM_CATEGORY_SEXUALLY_EXPLICIT`, `HARM_CATEGORY_DANGEROUS_CONTENT`, `HARM_CATEGORY_HARASSMENT`, `HARM_CATEGORY_HATE_SPEECH`, `HARM_CATEGORY_CIVIC_INTEGRITY`). This frees ~6 GB of VRAM on your RTX 4070 so <b>ComfyUI</b> gets 100% of your GPU!
      </p>
      <div class="grid-equal">
        <div>
          <label>Setup / Compute Mode</label>
          <select id="cfg-setup-mode">
            <option value="hybrid">⚡ Hybrid: Local + Cloud Fallback (Recommended)</option>
            <option value="local">🏠 Fully Local AI (Ollama / LM Studio + ComfyUI Only)</option>
            <option value="cloud">☁️ Fully Cloud AI (ChatGPT / Claude / Gemini + Cloud Images)</option>
          </select>

          <label>Hybrid Priority &amp; Cloud Provider</label>
          <div class="row" style="gap:6px;">
            <select id="cfg-llm-mode">
              <option value="gemini_first">Cloud First → Local Fallback</option>
              <option value="local_only">Local First → Cloud Fallback</option>
            </select>
            <select id="cfg-cloud-provider">
              <option value="gemini">Google Gemini</option>
              <option value="openai">OpenAI (ChatGPT)</option>
              <option value="anthropic">Anthropic (Claude)</option>
            </select>
          </div>

          <label>Gemini / OpenAI / Anthropic Models</label>
          <div class="grid-3" style="gap:6px;">
            <select id="cfg-gemini-model">
              <option value="gemini-2.5-flash">gemini-2.5-flash</option>
              <option value="gemini-2.5-pro">gemini-2.5-pro</option>
              <option value="gemini-2.0-flash">gemini-2.0-flash</option>
            </select>
            <input id="cfg-openai-model" value="gpt-4o-mini" placeholder="gpt-4o-mini">
            <input id="cfg-anthropic-model" value="claude-sonnet-4-5" placeholder="claude-sonnet-4-5">
          </div>
        </div>
        <div>
          <label>Gemini API Key</label>
          <div class="row">
            <input type="password" id="cfg-gemini-key" placeholder="AIzaSy...">
            <button class="btn secondary" style="max-width:75px;" onclick="const el=document.getElementById('cfg-gemini-key'); el.type = el.type==='password'?'text':'password';">👁️</button>
          </div>
          <label>OpenAI API Key (ChatGPT + Cloud Images)</label>
          <input type="password" id="cfg-openai-key" placeholder="sk-...">
          <label>Anthropic API Key (Claude)</label>
          <input type="password" id="cfg-anthropic-key" placeholder="sk-ant-...">
          <div style="display:flex; gap:10px; margin-top:14px;">
            <button class="btn" onclick="saveSettings()" style="flex:1;">💾 Save Compute &amp; API Settings</button>
            <button class="btn amber" onclick="testGeminiConnection()" style="flex:1;">🧪 Test Gemini</button>
          </div>
          <div id="gemini-test-status" style="margin-top:8px; font-size:12px; color:var(--green);"></div>
        </div>
      </div>
    </div>

    <div class="grid-equal">
      <div class="card">
        <h3>Download Additional Checkpoints or LoRAs (Civitai / HuggingFace)</h3>
        <p style="font-size:13px; color:var(--muted);">
          Paste any direct model download URL (e.g. from Civitai or HuggingFace) to download directly into your ComfyUI folders.
        </p>
        <label>Model Type</label>
        <select id="dl-type">
          <option value="checkpoint">Checkpoint (`ComfyUI\models\checkpoints`)</option>
          <option value="lora">LoRA (`ComfyUI\models\loras`)</option>
        </select>
        <label>Filename (e.g., `my_lora.safetensors`)</label>
        <input type="text" id="dl-filename" placeholder="example_model.safetensors">
        <label>Direct Download URL</label>
        <input type="text" id="dl-url" placeholder="https://civitai.com/api/download/models/...">
        <button class="btn secondary" onclick="downloadModel()" style="margin-top:14px; width:100%;">⬇️ Download to ComfyUI</button>
      </div>
    </div>
  </section>
</main>

<script>
let currentUploadedPaths = [];
let studioInputImagePath = '';
let chatAttachedImagePath = '';
let chatAttachedImageUrl = '';
let chatOriginalImagePath = '';
let chatOriginalImageUrl = '';
let chatHistory = [];
let studioSkillsCache = [];

function switchTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}

async function api(path, method='GET', body=null) {
  const opts = { method, headers: {'Content-Type': 'application/json'} };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  return await res.json();
}

async function refreshStatus() {
  try {
    const st = await api('/api/status');
    const cDot = document.getElementById('comfy-dot');
    const cTxt = document.getElementById('comfy-text');
    if (st.comfy.online) {
      cDot.className = 'dot on';
      cTxt.textContent = 'Online (Port 8188)';
    } else {
      cDot.className = 'dot';
      cTxt.textContent = 'Offline';
    }

    const lDot = document.getElementById('llm-dot');
    const lTxt = document.getElementById('llm-text');
    if (st.llm.online) {
      lDot.className = 'dot on';
      lTxt.textContent = st.llm.provider + ' (' + (st.llm.models[0] || 'Ready') + ')';
    } else {
      lDot.className = 'dot';
      lTxt.textContent = 'Offline';
    }
  } catch (e) {}
}

async function startService(which) {
  const res = await api('/api/service/start', 'POST', { service: which });
  alert(res.message || res.error);
  setTimeout(refreshStatus, 2000);
}

async function initDashboard() {
  await refreshStatus();
  setInterval(refreshStatus, 3000);

  const models = await api('/api/models');
  const ckptSel = document.getElementById('gen-ckpt');
  ckptSel.innerHTML = '';
  (models.checkpoints || []).forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    if (c.toLowerCase().includes('nsfw') || c.toLowerCase().includes('juggernaut')) opt.selected = true;
    ckptSel.appendChild(opt);
  });

  const loraSel = document.getElementById('gen-lora');
  loraSel.innerHTML = '<option value="">None</option>';
  (models.loras || []).forEach(l => {
    const opt = document.createElement('option');
    opt.value = l;
    opt.textContent = l;
    loraSel.appendChild(opt);
  });

  const cfg = await api('/api/config');
  document.getElementById('cfg-setup-mode').value = cfg.setup_mode || 'hybrid';
  document.getElementById('cfg-llm-mode').value = cfg.llm_provider_mode || 'gemini_first';
  document.getElementById('cfg-cloud-provider').value = cfg.cloud_provider || 'gemini';
  document.getElementById('cfg-gemini-model').value = cfg.gemini_model || 'gemini-2.5-flash';
  document.getElementById('cfg-openai-model').value = cfg.openai_model || 'gpt-4o-mini';
  document.getElementById('cfg-anthropic-model').value = cfg.anthropic_model || 'claude-sonnet-4-5';
  document.getElementById('cfg-gemini-key').value = cfg.gemini_api_key || '';
  document.getElementById('cfg-openai-key').value = cfg.openai_api_key || '';
  document.getElementById('cfg-anthropic-key').value = cfg.anthropic_api_key || '';
  if (cfg.setup_completed === false) {
    openSetupWizard();
  }

  loadStudioSkills();
  loadLearnedMemory();
  loadGallery();
  initDccTab();
  initSw5eTab();
  initDnd5eTab();
  initCampaignTab();
  initTtrpgPresets();
  refreshRulesIndexStatus();
}

async function loadLearnedMemory() {
  const mem = await api('/api/learned-memory');
  renderLearnedMemory(mem);
}

function renderLearnedMemory(mem) {
  if (!mem) return;
  document.getElementById('chk-use-learned-memory').checked = mem.enabled !== false;
  const pos = mem.positive_boosts || [];
  const neg = mem.negative_blocks || [];
  const les = mem.style_lessons || [];
  document.getElementById('mem-pos-boosts').value = pos.join('\n');
  document.getElementById('mem-neg-blocks').value = neg.join('\n');
  document.getElementById('mem-lessons').value = les.join('\n');

  const sumEl = document.getElementById('learned-memory-summary');
  if (mem.enabled === false) {
    sumEl.innerHTML = `<span style="color:var(--amber);">Paused</span> (${pos.length} positive boosts, ${neg.length} negative blocks, ${les.length} style rules stored)`;
  } else {
    sumEl.innerHTML = `
      <span style="color:var(--green); font-weight:600;">Active:</span>
      <b>${pos.length}</b> Positive Boosts • <b>${neg.length}</b> Negative Blocks • <b>${les.length}</b> Style Lessons<br>
      <span style="color:#c4b5fd;">Latest Boosts:</span> <code>${pos.slice(-3).join(', ') || '(none)'}</code>
    `;
  }
}

function toggleMemoryEditor() {
  const el = document.getElementById('learned-memory-editor');
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

async function toggleLearnedMemoryEnabled() {
  const enabled = document.getElementById('chk-use-learned-memory').checked;
  const res = await api('/api/learned-memory', 'POST', { enabled });
  if (res.ok) renderLearnedMemory(res.memory);
}

async function saveLearnedMemoryFromUI() {
  const pos = document.getElementById('mem-pos-boosts').value.split('\n').map(s => s.trim()).filter(Boolean);
  const neg = document.getElementById('mem-neg-blocks').value.split('\n').map(s => s.trim()).filter(Boolean);
  const les = document.getElementById('mem-lessons').value.split('\n').map(s => s.trim()).filter(Boolean);
  const enabled = document.getElementById('chk-use-learned-memory').checked;
  const res = await api('/api/learned-memory', 'POST', {
    enabled,
    positive_boosts: pos,
    negative_blocks: neg,
    style_lessons: les
  });
  if (res.ok) {
    renderLearnedMemory(res.memory);
    alert('Saved learned memory rules!');
  }
}

async function fixAndTeachFromStudio() {
  if (!studioInputImagePath) return alert('Select or upload an image first (or click "🔧 Fix" on any image in the Gallery).');
  const feedback = document.getElementById('studio-edit-instruction').value.trim();
  if (!feedback) {
    document.getElementById('studio-edit-instruction').focus();
    return alert('Describe what went wrong or needs fixing in the box above (e.g., "her hands have 6 fingers and skin looks too plastic, make hair darker").');
  }
  const btn = document.getElementById('btn-fix-teach');
  const statusEl = document.getElementById('gen-status');
  const diagEl = document.getElementById('studio-fix-diagnosis');
  btn.disabled = true;
  statusEl.textContent = '🔧 AI is diagnosing the image flaw, learning your rule, and generating the corrected image...';
  diagEl.style.display = 'none';

  try {
    const res = await api('/api/fix-and-learn', 'POST', {
      image_path: studioInputImagePath,
      feedback: feedback,
      current_prompt: document.getElementById('gen-prompt').value,
      current_negative: document.getElementById('gen-neg').value,
      skill_id: document.getElementById('gen-skill').value,
      remember_globally: document.getElementById('chk-learn-global').checked,
      update_skill: document.getElementById('chk-learn-skill').checked,
      auto_regenerate: true
    });
    if (res.ok) {
      const pl = res.plan || {};
      if (pl.corrected_prompt) document.getElementById('gen-prompt').value = pl.corrected_prompt;
      if (pl.corrected_negative) document.getElementById('gen-neg').value = pl.corrected_negative;
      if (pl.recommended_denoise) {
        document.getElementById('gen-denoise').value = pl.recommended_denoise;
        document.getElementById('studio-denoise-val').textContent = parseFloat(pl.recommended_denoise).toFixed(2);
      }
      if (res.memory) renderLearnedMemory(res.memory);
      if (document.getElementById('chk-learn-skill').checked && document.getElementById('gen-skill').value) {
        await loadStudioSkills(document.getElementById('gen-skill').value);
      }
      const learnedHtml = (res.learned_summary && res.learned_summary.length)
        ? `<br><span style="color:#c4b5fd;">🧠 Learned for Future Images:</span> ${res.learned_summary.join(' | ')}`
        : `<br><span style="color:var(--muted);">Applied as a scene-specific fix for this image.</span>`;
      diagEl.innerHTML = `<b style="color:var(--green);">🔧 Diagnosis:</b> ${pl.diagnosis || 'Repaired prompt & negative weights.'}${learnedHtml}`;
      diagEl.style.display = 'block';
      statusEl.textContent = '✅ Fixed image generated and rule saved to memory!';
      loadGallery();
    } else {
      statusEl.textContent = '❌ Fix error: ' + (res.error || 'Failed');
    }
  } catch (e) {
    statusEl.textContent = '❌ Fix error: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

async function loadStudioSkills(selectId='') {
  const res = await api('/api/studio-skills');
  studioSkillsCache = res.skills || [];
  const sel = document.getElementById('gen-skill');
  const currentVal = selectId || sel.value;
  sel.innerHTML = '<option value="">None (Standard Manual Settings)</option>';
  studioSkillsCache.forEach(sk => {
    const opt = document.createElement('option');
    opt.value = sk.id;
    opt.textContent = `⚡ ${sk.name} — ${sk.description || ''}`;
    sel.appendChild(opt);
  });
  if (currentVal) {
    sel.value = currentVal;
    onSelectStudioSkill();
  }
}

function onSelectStudioSkill() {
  const skillId = document.getElementById('gen-skill').value;
  const descEl = document.getElementById('gen-skill-desc');
  const delBtn = document.getElementById('btn-del-skill');
  if (!skillId) {
    descEl.innerHTML = 'Select a skill to auto-apply its lighting, framing, negative prompt, SDXL resolution, steps, CFG, and prompt enhancer rules — or create your own in <b>Agent Chat</b>!';
    delBtn.style.display = 'none';
    return;
  }
  const sk = studioSkillsCache.find(s => s.id === skillId);
  if (!sk) return;
  delBtn.style.display = 'inline-flex';
  const st = sk.settings || {};
  if (st.resolution) {
    const resSel = document.getElementById('gen-res');
    for (const opt of resSel.options) {
      if (opt.value === st.resolution) { resSel.value = st.resolution; break; }
    }
  }
  if (st.steps) document.getElementById('gen-steps').value = st.steps;
  if (st.cfg) document.getElementById('gen-cfg').value = st.cfg;
  if (st.sampler) document.getElementById('gen-sampler').value = st.sampler;
  if (st.scheduler) document.getElementById('gen-scheduler').value = st.scheduler;
  if (st.denoise) {
    document.getElementById('gen-denoise').value = st.denoise;
    document.getElementById('studio-denoise-val').textContent = parseFloat(st.denoise).toFixed(2);
  }
  if (sk.negative_prompt) {
    document.getElementById('gen-neg').value = sk.negative_prompt;
  }
  descEl.innerHTML = `
    <span style="color:var(--green); font-weight:600;">Active Skill: ${sk.name}</span> — ${sk.description || ''}<br>
    <span style="color:#c4b5fd;">Auto-Tags:</span> <code>${[sk.prompt_prefix, sk.prompt_suffix].filter(Boolean).join(' ... ')}</code>
  `;
}

async function deleteSelectedStudioSkill() {
  const skillId = document.getElementById('gen-skill').value;
  if (!skillId) return;
  const sk = studioSkillsCache.find(s => s.id === skillId);
  if (!confirm(`Delete Studio Skill "${sk ? sk.name : skillId}"?`)) return;
  const res = await api('/api/studio-skills/delete', 'POST', { skill_id: skillId });
  if (res.ok) {
    document.getElementById('gen-skill').value = '';
    await loadStudioSkills();
    onSelectStudioSkill();
  }
}

function useSkillInStudio(skillId) {
  loadStudioSkills(skillId).then(() => {
    document.querySelectorAll('nav button')[0].click();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}

function startSkillPromptInChat() {
  document.querySelectorAll('nav button')[3].click();
  insertSkillTemplate();
}

function insertSkillTemplate() {
  const inp = document.getElementById('chat-input');
  if (chatAttachedImagePath) {
    document.getElementById('chat-img-mode').value = 'skill';
    inp.value = '/skill Create a reusable Image Studio skill based on this attached image style called ';
  } else {
    inp.value = '/skill Create an Image Studio skill called ';
  }
  inp.focus();
}

let lastPromptBeforeEnhance = '';

function undoEnhancePrompt() {
  if (lastPromptBeforeEnhance) {
    document.getElementById('gen-prompt').value = lastPromptBeforeEnhance;
    document.getElementById('btn-undo-enhance').style.display = 'none';
    document.getElementById('gen-status').textContent = '↩️ Restored your original prompt.';
  }
}

async function enhancePrompt() {
  const p = document.getElementById('gen-prompt').value.trim();
  if (!p) return alert('Type your prompt idea first, then click Enhance!');
  lastPromptBeforeEnhance = p;
  const statusEl = document.getElementById('gen-status');
  const activeSkillId = document.getElementById('gen-skill').value;
  statusEl.textContent = activeSkillId
    ? '✨ Optimizing your prompt with AI + active Studio Skill rules...'
    : '✨ Optimizing your prompt with AI...';
  try {
    const res = await api('/api/enhance-prompt', 'POST', {
      prompt: p,
      image_path: studioInputImagePath,
      skill_id: activeSkillId
    });
    if (res.ok && res.prompt) {
      document.getElementById('gen-prompt').value = res.prompt.trim();
      document.getElementById('btn-undo-enhance').style.display = 'inline-flex';
      statusEl.textContent = '✅ Prompt optimized! (Click "↩️ Undo Enhance" if you prefer your original wording.)';
    } else {
      statusEl.textContent = '❌ Enhance error: ' + (res.error || 'Failed');
    }
  } catch (e) {
    statusEl.textContent = '❌ Enhance error: ' + e.message;
  }
}

async function uploadStudioInputImage() {
  const input = document.getElementById('studio-input-file');
  if (!input.files || !input.files.length) return;
  const file = input.files[0];
  const b64 = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.readAsDataURL(file);
  });
  const res = await api('/api/upload', 'POST', { filename: file.name, data_b64: b64 });
  if (res.ok) {
    setStudioInputImage(res.disk_path, res.url, res.width, res.height, res.recommended_res);
  }
}

// ============================================================================
// INTERACTIVE BRUSH INPAINTING CANVAS CONTROLLER
// ============================================================================
let studioMaskMode = 'brush'; // 'brush' or 'eraser'
let studioBrushSize = 28;
let isStudioPainting = false;
let studioMaskHasStrokes = false;

function initMaskCanvas(canvasId, imgId) {
  const canvas = document.getElementById(canvasId);
  const img = document.getElementById(imgId);
  if (!canvas || !img) return;

  function syncSize() {
    if (img.naturalWidth && img.naturalHeight) {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
    } else {
      canvas.width = img.clientWidth || 220;
      canvas.height = img.clientHeight || 220;
    }
  }

  if (img.complete && img.naturalWidth) {
    syncSize();
  } else {
    img.onload = syncSize;
  }
}

function setStudioMaskMode(mode) {
  studioMaskMode = mode;
  const brushBtn = document.getElementById('btn-mask-mode-brush');
  const eraserBtn = document.getElementById('btn-mask-mode-eraser');
  if (brushBtn && eraserBtn) {
    if (mode === 'brush') {
      brushBtn.style.background = 'var(--accent)';
      brushBtn.style.color = '#fff';
      eraserBtn.style.background = 'var(--panel-alt)';
      eraserBtn.style.color = 'var(--text)';
    } else {
      eraserBtn.style.background = 'var(--amber)';
      eraserBtn.style.color = '#000';
      brushBtn.style.background = 'var(--panel-alt)';
      brushBtn.style.color = 'var(--text)';
    }
  }
}

function updateStudioBrushSizeLabel(val) {
  studioBrushSize = parseInt(val);
  const el = document.getElementById('studio-brush-size-val');
  if (el) el.textContent = val + 'px';
}

function clearStudioMask() {
  const canvas = document.getElementById('studio-mask-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  studioMaskHasStrokes = false;
  const badge = document.getElementById('studio-mask-status-badge');
  if (badge) {
    badge.innerHTML = `🎨 <b>Brush Mask Inpaint Ready:</b> Paint where you want the new elements. Unpainted areas stay 100% original photo!`;
  }
}

function getMaskCanvasAsBase64(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || canvas.width === 0 || canvas.height === 0) return '';

  // Render to a black/white mask canvas where painted pixels are pure white #FFFFFF
  // and unpainted pixels are pure black #000000 (standard ComfyUI/SDXL mask input)
  const exportCanvas = document.createElement('canvas');
  exportCanvas.width = canvas.width;
  exportCanvas.height = canvas.height;
  const expCtx = exportCanvas.getContext('2d');

  // Fill black
  expCtx.fillStyle = '#000000';
  expCtx.fillRect(0, 0, exportCanvas.width, exportCanvas.height);

  // Inspect source canvas alpha to draw pure white wherever user painted
  const srcCtx = canvas.getContext('2d');
  const srcData = srcCtx.getImageData(0, 0, canvas.width, canvas.height);
  const expData = expCtx.getImageData(0, 0, exportCanvas.width, exportCanvas.height);
  let hasWhite = false;

  for (let i = 0; i < srcData.data.length; i += 4) {
    const alpha = srcData.data[i + 3];
    if (alpha > 15) {
      expData.data[i] = 255;
      expData.data[i + 1] = 255;
      expData.data[i + 2] = 255;
      expData.data[i + 3] = 255;
      hasWhite = true;
    }
  }

  if (!hasWhite) return '';
  expCtx.putImageData(expData, 0, 0);
  return exportCanvas.toDataURL('image/png');
}

function setupCanvasDrawing(canvasId, imgId, isChat=false) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  function getPos(e) {
    const rect = canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY
    };
  }

  function startDraw(e) {
    e.preventDefault();
    if (isChat) isChatPainting = true;
    else isStudioPainting = true;
    draw(e);
  }

  function draw(e) {
    const active = isChat ? isChatPainting : isStudioPainting;
    if (!active) return;
    e.preventDefault();
    const pos = getPos(e);
    const mode = isChat ? chatMaskMode : studioMaskMode;
    const size = isChat ? chatBrushSize : studioBrushSize;
    const scaleFactor = canvas.width / (canvas.clientWidth || canvas.width);
    const radius = (size / 2) * scaleFactor;

    ctx.save();
    if (mode === 'eraser') {
      ctx.globalCompositeOperation = 'destination-out';
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.globalCompositeOperation = 'source-over';
      ctx.fillStyle = 'rgba(239, 68, 68, 0.72)'; // Vivid red semi-transparent overlay
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
      ctx.fill();
      if (isChat) chatMaskHasStrokes = true;
      else {
        studioMaskHasStrokes = true;
        const badge = document.getElementById('studio-mask-status-badge');
        if (badge) {
          badge.innerHTML = `✨ <b style="color:#6ee7b7;">Active Brush Mask:</b> Targeted Inpaint active! Unpainted areas are 100% locked.`;
        }
      }
    }
    ctx.restore();
  }

  function stopDraw(e) {
    if (isChat) isChatPainting = false;
    else isStudioPainting = false;
  }

  canvas.addEventListener('mousedown', startDraw);
  canvas.addEventListener('mousemove', draw);
  window.addEventListener('mouseup', stopDraw);

  canvas.addEventListener('touchstart', startDraw, { passive: false });
  canvas.addEventListener('touchmove', draw, { passive: false });
  window.addEventListener('touchend', stopDraw);
}

// Chat Mask Inpaint Variables
let chatMaskMode = 'brush';
let chatBrushSize = 22;
let isChatPainting = false;
let chatMaskHasStrokes = false;

function setChatMaskMode(mode) {
  chatMaskMode = mode;
  const b = document.getElementById('btn-chat-mask-brush');
  const e = document.getElementById('btn-chat-mask-eraser');
  if (b && e) {
    if (mode === 'brush') {
      b.style.background = 'var(--accent)';
      b.style.color = '#fff';
      e.style.background = 'var(--panel-alt)';
      e.style.color = 'var(--text)';
    } else {
      e.style.background = 'var(--amber)';
      e.style.color = '#000';
      b.style.background = 'var(--panel-alt)';
      b.style.color = 'var(--text)';
    }
  }
}

function updateChatBrushSizeLabel(val) {
  chatBrushSize = parseInt(val);
  const el = document.getElementById('chat-brush-size-val');
  if (el) el.textContent = val + 'px';
}

// ============================================================================
// TTRPG RULESET CHARACTER PORTRAIT PRESETS (D&D 5e, SW5e, DCC)
// ============================================================================
const TTRPG_RULESETS = {
  dnd5e: {
    name: "D&D 5e",
    signatureStyle: "(official D&D 5e handbook fantasy illustration style:1.25), rich painterly brushwork, dramatic chiaroscuro rim lighting, detailed leather and metal textures, 8k uhd",
    races: [
      ["human", "Human", "human"],
      ["elf_high", "High Elf", "graceful high elf, pointed ears, refined elven features"],
      ["elf_wood", "Wood Elf", "wood elf, pointed ears, weathered forest-toned skin, keen wild eyes"],
      ["drow", "Drow (Dark Elf)", "drow dark elf, obsidian charcoal skin, silver-white hair, crimson or violet eyes, pointed ears"],
      ["dwarf", "Dwarf", "stocky dwarf, thick braided beard, weathered noble features, sturdy build"],
      ["halfling", "Halfling", "halfling, youthful expressive face, curly hair, nimble stature"],
      ["dragonborn", "Dragonborn", "dragonborn reptilian humanoid, sculpted draconic scales, horned crest, glowing draconic eyes"],
      ["gnome", "Gnome", "gnome, bright curious eyes, whimsical features, clever expression"],
      ["half_elf", "Half-Elf", "half-elf, subtly pointed ears, charismatic human-elven features"],
      ["half_orc", "Half-Orc", "half-orc, olive-grey skin, prominent lower tusks, fierce battle-hardened jaw"],
      ["tiefling", "Tiefling", "tiefling, curved swept-back horns, solid glowing amber or gold eyes, infernal heritage"],
      ["aasimar", "Aasimar", "aasimar, luminous celestial eyes, subtle golden halo-like rim light, noble ethereal features"],
      ["goliath", "Goliath", "towering goliath, pale stone-grey skin with dark geometric lithoderm markings, bald muscular build"],
      ["tabaxi", "Tabaxi", "tabaxi feline humanoid, spotted leopard-like fur, slit cat eyes, alert whiskers"],
      ["tortle", "Tortle", "tortle turtle humanoid, weathered reptilian face, heavy armored carapace shell"],
      ["kenku", "Kenku", "kenku raven humanoid, sleek black feathers, sharp obsidian beak, expressive dark eyes"],
      ["genasi", "Genasi (Elemental)", "elemental genasi, glowing elemental veins and hair (fire, water, earth, or air motif)"],
      ["firbolg", "Firbolg", "firbolg giant-kin, soft mossy-grey skin, broad nose, gentle wise forest eyes"],
      ["warforged", "Warforged", "warforged living construct, articulatedmithril and darkwood plating, glowing optical sensors"],
      ["changeling", "Changeling", "changeling shapeshifter, pale alabaster skin, featureless silver-white eyes, silver hair"],
      ["harengon", "Harengon", "harengon rabbit-folk humanoid, tall expressive ears, alert twitching nose, furred face"],
      ["owlin", "Owlin", "owlin owl-folk humanoid, feathered brow tufts, large luminous amber owl eyes, sleek plumage"]
    ],
    classes: [
      ["artificer", "Artificer", "arcane artificer wearing brass-goggled leather apron, glowing alchemical vials and runic gadgets"],
      ["barbarian", "Barbarian", "fierce barbarian warrior in fur-trimmed iron pauldrons, battle scars, heavy greatsword or war axe"],
      ["bard", "Bard", "charismatic bard in embroidered velvet doublet, ornate lute slung over shoulder, jaunty feather cap"],
      ["cleric", "Cleric", "devout cleric in engraved scale mail and tabard, glowing holy symbol amulet, radiant divine aura"],
      ["druid", "Druid", "wild druid in moss-draped hide vestments, antlered wooden circlet, gnarled oak staff with glowing leaves"],
      ["fighter", "Fighter", "veteran fighter in battered steel plate armor, scarred shield, crisp martial bearing"],
      ["monk", "Monk", "disciplined martial monk in wrapped linen gi, prayer beads, focused serene stance"],
      ["paladin", "Paladin", "heroic paladin in gleaming engraved plate armor, flowing cape, radiant oath-sworn presence"],
      ["ranger", "Ranger", "wilderness ranger in hooded forest-green cloak, studded leather, carved longbow and quiver"],
      ["rogue", "Rogue", "shadow rogue in dark hooded leather armor, twin daggers, sharp calculating gaze"],
      ["sorcerer", "Sorcerer", "innate arcane sorcerer in flowing silk robes, crackling raw elemental magic around hands"],
      ["warlock", "Warlock", "eldritch warlock in dark velvet and gold vestments, swirling violet pact magic, tome of shadows"],
      ["wizard", "Wizard", "arcane wizard in ornate runic robes, glowing crystal-topped staff, floating arcane sigils"]
    ],
    backdrops: [
      ["tavern", "🔥 Tavern Torchlight", "(warm flickering hearth and torchlight:1.25), cozy medieval tavern background, wooden beams, amber bokeh"],
      ["dungeon", "🏰 Stone Dungeon Cavern", "(cold blue torchlight:1.25), ancient carved stone dungeon cavern, drifting mist, dramatic shadows"],
      ["forest", "🌲 Mystic Ancient Forest", "(ancient mossy woodland background:1.25), volumetric sunbeams filtering through canopy, floating dust motes"],
      ["battlefield", "⚡ Stormy Battlefield", "(stormy overcast sky with distant lightning:1.25), swirling embers and smoke, epic fantasy battlefield"],
      ["tower", "🔮 Arcane Wizard Tower", "(high-ceilinged arcane library tower:1.25), floating candles, ancient spell tomes, stained glass starlight"],
      ["underdark", "🍄 Underdark Cavern", "(bioluminescent fungi cavern:1.25), eerie violet and teal cave glow, subterranean stalactites"],
      ["citadel", "👑 Royal Citadel Hall", "(grand marble throne hall:1.25), tattered heraldic banners, shafts of golden cathedral light"]
    ]
  },
  sw5e: {
    name: "SW5e (Star Wars 5e)",
    signatureStyle: "(cinematic Star Wars sci-fi concept art style:1.25), ILM matte-painting atmosphere, crisp rim lighting, weathered lived-in galactic gear, 8k uhd",
    races: [
      ["human", "Human", "human galactic spacer"],
      ["twilek", "Twi'lek", "twi'lek alien humanoid, twin articulated head-tails (lekku), vibrant colored skin, expressive eyes"],
      ["togruta", "Togruta", "togruta alien humanoid, patterned orange-red skin with white facial markings, striped montrals and head-tails"],
      ["zabrak", "Zabrak", "zabrak alien humanoid, crown of cranial horns, intricate geometric facial tattoos, intense eyes"],
      ["chiss", "Chiss", "chiss alien humanoid, crisp cobalt-blue skin, glowing solid crimson eyes, jet-black hair"],
      ["wookiee", "Wookiee", "towering wookiee warrior, thick shaggy brown-and-grey fur, bandolier strap, fierce noble eyes"],
      ["rodian", "Rodian", "rodian alien, emerald-green textured skin, large faceted dark eyes, flexible snout and twin antennae"],
      ["mirialan", "Mirialan", "mirialan alien humanoid, olive-green skin, traditional black geometric diamond facial tattoos"],
      ["nautolan", "Nautolan", "nautolan amphibious humanoid, teal-green skin, large glossy black eyes, trailing head-tentacles"],
      ["kel_dor", "Kel Dor", "kel dor alien, leathery orange skin, dark protective goggles and metallic antiox breath mask"],
      ["mon_calamari", "Mon Calamari", "mon calamari amphibious alien, mottled salmon-orange skin, domed cranium, large swivel eyes"],
      ["duros", "Duros", "duros spacer alien, smooth blue-grey skin, large red slit-pupil eyes, high cheekbones"],
      ["trandoshan", "Trandoshan", "trandoshan reptilian hunter, heavy green-yellow scales, sharp claws, slit amber predator eyes"],
      ["bothan", "Bothan", "bothan spy humanoid, tawny furred canine-feline face, pointed ears, shrewd calculating eyes"],
      ["jawa", "Jawa", "hooded jawa scavenger, brown coarse robes, deep shadowed cowl with twin glowing yellow eyes"],
      ["ewok", "Ewok", "ewok woodland creature, furry bear-like face, stitched leather hood with feather, bright dark eyes"],
      ["droid", "Droid (Combat/Protocol)", "weathered sci-fi droid chassis, scratched brushed durasteel plating, glowing photoreceptors, Exposed wiring"],
      ["miraluka", "Miraluka", "miraluka near-human, ornate woven cloth blindfold over eyes, serene Force-sensitive aura"],
      ["rattataki", "Rattataki", "rattataki warrior, chalk-white bald head, dark scarred facial tattoos, piercing cold eyes"],
      ["sith_pureblood", "Sith Pureblood", "sith pureblood humanoid, crimson-red skin, bone ridges and facial tendrils, glowing golden-yellow eyes"],
      ["mandalorian", "Mandalorian (Armored)", "mandalorian warrior wearing scarred beskar T-visor helmet and weathered plated armor"]
    ],
    classes: [
      ["berserker", "Berserker", "fierce galactic berserker in heavy scavenged armor, vibro-axe slung across back, battle-worn grip"],
      ["consular", "Consular (Force Sage)", "Force consular in flowing layered tunic and hooded cloak, serene concentration, glowing lightsaber hilt"],
      ["engineer", "Engineer", "tech-savvy starship engineer in oil-stained flight vest, holographic wrist datapad, plasma welder"],
      ["fighter", "Fighter (Trooper/Merc)", "battle-hardened mercenary trooper in scarred composite armor, heavy blaster rifle, tactical pauldron"],
      ["guardian", "Guardian (Jedi/Knight)", "armored Force guardian in battle-ready robes with shoulder plates, ignited plasma blade glow"],
      ["monk", "Monk (Teras Kasi)", "martial Teras Kasi mystic in wrapped spacer tunic, reinforced bracers, poised combat stance"],
      ["operative", "Operative (Smuggler/Spy)", "slick galactic operative in battered leather flight jacket, low-slung blaster pistol, rakish smirk"],
      ["scholar", "Scholar (Tactician/Medic)", "galactic scholar in crisp collared officer coat, glowing holo-projector, analytical gaze"],
      ["scout", "Scout (Bounty Hunter)", "rugged galactic scout and tracker in poncho and macrobinoculars, sniper blaster carbine"],
      ["sentinel", "Sentinel (Shadow)", "covert Force sentinel in dark stealth-weave cowl, dual-bladed hilt, moody shadow aura"]
    ],
    backdrops: [
      ["coruscant", "🌃 Coruscant Neon Underworld", "(rain-slicked Coruscant lower-level neon alley:1.25), glowing Aurebesh holo-signs, distant flying speeder trails"],
      ["cantina", "🥃 Galactic Cantina Booth", "(smoky dim-lit spaceport cantina:1.25), glowing blue holographic table, alien ambiance, warm amber booth lights"],
      ["destroyer", "🛸 Star Destroyer Bridge", "(polished dark imperial starship bridge:1.25), triangular viewport looking out at stars, cold tactical rim lighting"],
      ["tatooine", "☀️ Twin Suns Desert", "(arid desert spaceport canyon:1.25), twin suns glowing on dusty horizon, moisture vaporators, heat haze"],
      ["dagobah", "🌿 Misty Force Swamp", "(foggy ancient swamp jungle:1.25), twisted gnarled roots, eerie emerald mist, mystical Force ambiance"],
      ["jedi_temple", "🏛️ Ancient Temple Ruins", "(moss-covered ancient Force temple ruins:1.25), carved monoliths, shafts of golden sunbeams"],
      ["hyperspace", "✨ Hyperspace Cockpit", "(starship cockpit interior:1.25), streaking blue-white hyperspace starlines outside canopy, instrument panel glow"]
    ]
  },
  dcc: {
    name: "Dungeon Crawler Carl TTRPG",
    signatureStyle: "(gritty modern LitRPG dungeon-crawl cover illustration style:1.25), dramatic broadcast spotlighting, absurdly lethal dungeon gear over street clothes, crisp detail, 8k uhd",
    races: [
      ["human", "Human", "human earth survivor"],
      ["cat_person", "Cat-Person (Feline)", "bipedal feline cat-person humanoid, plush patterned fur, tufted ears, sharp whiskers, expressive cat eyes"],
      ["changeling", "Changeling", "dungeon changeling, shifting iridescent skin tones, uncanny expressive eyes, adaptable build"],
      ["were_creature", "Were-Creature / Lycan", "ferocious lycanthrope humanoid, bristling fur, jagged fangs, glowing amber predator eyes"],
      ["goblin", "Goblin", "wiry green-skinned goblin, tall notched ears, sharp teeth, mischievous manic grin"],
      ["kobold", "Kobold", "scaled reptilian kobold, slender snout, small horns, wide alert yellow eyes"],
      ["rock_person", "Rock-Person / Golem", "hulking stone-skinned rock-person, cracked granite plates with glowing mineral seams"],
      ["mantis", "Mantis / Insectoid", "chitinous mantis insectoid humanoid, faceted compound eyes, sleek armored exoskeleton"],
      ["elf", "Elf", "sharp-featured dungeon elf, long pointed ears, battle-dusted noble expression"],
      ["dwarf", "Dwarf", "burly dungeon dwarf, heavy braided beard, soot-smudged brow, stout frame"],
      ["orc", "Orc", "towering muscular orc, scarred green-grey skin, heavy tusks, fierce survivor glare"],
      ["undead", "Undead / Skeleton", "reanimated dungeon undead crawler, weathered bone and tattered wraps, eerie soul-fire eyes"],
      ["slime_kin", "Slime-Kin", "translucent bioluminescent slime-kin humanoid, shimmering gelatinous contours"],
      ["naga", "Naga / Serpentine", "serpentine naga humanoid, iridescent scales, slit-pupil eyes, hooded cobra-like crest"]
    ],
    classes: [
      ["crawler0", "Level 0 Survivor", "new earth crawler wearing mismatched street clothes (leather jacket, hoodie, or boxers) clutching improvised loot"],
      ["anarchist", "Anarchist / Demolitionist", "chaotic demolitionist covered in soot, bandolier of enchanted dynamite and goblin grenades, manic smirk"],
      ["pugilist", "Pugilist / Brawler", "bare-knuckle dungeon brawler with glowing enchanted gauntlets, taped knuckles, bruised determined face"],
      ["berserker", "Berserker", "blood-spattered dungeon berserker in spiked trophy pauldrons, massive jagged cleaver"],
      ["pyromancer", "Pyromancer / Mage", "scorched dungeon mage in enchanted hoodie, hands wreathed in roaring fireballs and mana sparks"],
      ["rogue", "Rogue / Trap-Disarmer", "nimble dungeon rogue with lockpicks, loot satchel, hooded cloak, wary street-smart eyes"],
      ["healer", "Healer / Field Medic", "frantic dungeon medic with glowing green restoration aura, bandolier of red healing potions"],
      ["necromancer", "Necromancer", "eerie dungeon necromancer in tattered dark coat, swirling sickly-green soul wisps and bone charms"],
      ["summoner", "Summoner / Pet Tamer", "dungeon tamer accompanied by glowing summon sigils and loyal monster-pet collar charms"],
      ["bard", "Showrunner Bard", "flamboyant dungeon performer with enchanted megaphone or instrument, dazzling sponsor-spotlight aura"],
      ["juggernaut", "Tank / Juggernaut", "heavy dungeon tank behind a battered riot shield and mismatched enchanted plate armor"],
      ["sniper", "Sniper / Marksman", "sharp-eyed marksman with enchanted crossbow or makeshift launcher, tactical goggles"]
    ],
    backdrops: [
      ["saferoom", "🛋️ Safe Room Neon Lounge", "(dungeon safe room lounge:1.25), warm neon sign glow, vending machines, plush mismatched sofa, brief respite"],
      ["corridor", "⚠️ AI Trap Corridor", "(gritty dungeon stone-and-steel corridor:1.25), glowing red laser tripwires, floating broadcast drone camera"],
      ["arena", "💥 Goblin Murder-Dozer Arena", "(chaotic subterranean boss arena:1.25), sparks, burning wreckage, roaring crowd shadows in stadium tiers"],
      ["desperado", "🍸 Desperado Club Neon Bar", "(seedy underworld neon club interior:1.25), magenta and cyan bar lights, smoky haze, shady patrons"],
      ["spotlight", "🎥 Boss Chamber Spotlight", "(dramatic overhead broadcast spotlight beams:1.25), floating camera drones, cracked dungeon floor, smoke"],
      ["irontangle", "🚇 Iron Tangle Subway", "(twisted subterranean subway station:1.25), rusted train cars, flickering fluorescent tubes, graffiti"],
      ["overcity", "🏙️ Enchanted Overcity", "(surreal neon-lit dungeon city street:1.25), towering surreal facades, floating glowing achievement banners"]
    ]
  }
};

const TTRPG_ART_STYLES = {
  ruleset_auto: {
    label: "Ruleset Signature Style",
    prompt: "",
    denoise: 0.78,
    mode: "edit"
  },
  oil_painting: {
    label: "Classic Oil Painting",
    prompt: "(classic fantasy oil painting style:1.3), rich painterly brushwork, dramatic chiaroscuro lighting, fine canvas texture, masterwork illustration",
    denoise: 0.65,
    mode: "edit"
  },
  vtt_token: {
    label: "VTT Token Bust (1024x1024)",
    prompt: "(centered head and shoulders VTT token portrait:1.3), bold readable silhouette, clean uncluttered backdrop, crisp high-contrast rim lighting, tabletop RPG token art",
    denoise: 1.0,
    mode: "reactor",
    resolution: "1024x1024"
  },
  grimdark_ink: {
    label: "Grimdark Ink & Watercolor",
    prompt: "(grimdark ink and watercolor concept art:1.3), expressive crosshatching, gritty atmospheric shading, muted desaturated palette, weathered textures",
    denoise: 0.68,
    mode: "edit"
  },
  comic_cover: {
    label: "Pulp / LitRPG Cover Art",
    prompt: "(dynamic pulp fantasy and LitRPG cover art:1.3), bold inked linework, vibrant cinematic lighting, heroic dramatic framing",
    denoise: 0.72,
    mode: "edit"
  }
};

function _ttrpgIds(prefix) {
  const p = prefix === 'chat' ? 'chat-ttrpg-' : 'ttrpg-';
  return {
    ruleset: p + 'ruleset',
    style: p + 'style',
    race: p + 'race',
    cls: p + 'class',
    backdrop: p + 'backdrop'
  };
}

function initTtrpgPresets() {
  onRulesetChange('studio', false);
  onRulesetChange('chat', false);
}

function onRulesetChange(prefix='studio', shouldApply=true) {
  if (typeof prefix === 'boolean') { shouldApply = prefix; prefix = 'studio'; }
  const ids = _ttrpgIds(prefix);
  const rsKey = (document.getElementById(ids.ruleset)?.value) || 'dnd5e';
  const rs = TTRPG_RULESETS[rsKey];
  if (!rs) return;

  const fillSel = (id, items) => {
    const sel = document.getElementById(id);
    if (!sel) return;
    sel.innerHTML = '';
    items.forEach(([val, label]) => {
      const opt = document.createElement('option');
      opt.value = val;
      opt.textContent = label;
      sel.appendChild(opt);
    });
  };
  fillSel(ids.race, rs.races);
  fillSel(ids.cls, rs.classes);
  fillSel(ids.backdrop, rs.backdrops);
  if (shouldApply) applyTtrpgPreset(prefix);
}

function applyTtrpgPreset(prefix='studio') {
  const ids = _ttrpgIds(prefix);
  const rsKey = document.getElementById(ids.ruleset)?.value || 'dnd5e';
  const rs = TTRPG_RULESETS[rsKey];
  if (!rs) return;

  const raceVal = document.getElementById(ids.race)?.value;
  const classVal = document.getElementById(ids.cls)?.value;
  const bgVal = document.getElementById(ids.backdrop)?.value;
  const styleVal = document.getElementById(ids.style)?.value || 'ruleset_auto';

  const raceItem = rs.races.find(r => r[0] === raceVal) || rs.races[0];
  const classItem = rs.classes.find(c => c[0] === classVal) || rs.classes[0];
  const bgItem = rs.backdrops.find(b => b[0] === bgVal) || rs.backdrops[0];
  const styleObj = TTRPG_ART_STYLES[styleVal] || TTRPG_ART_STYLES.ruleset_auto;

  const stylePrompt = styleVal === 'ruleset_auto' ? rs.signatureStyle : styleObj.prompt;
  const fullPrompt = `(${raceItem[2]} ${classItem[2]} character portrait:1.3), ${bgItem[2]}, ${stylePrompt}, sharp focus on eyes`;

  if (prefix === 'chat') {
    const chatInp = document.getElementById('chat-input');
    const modeSel = document.getElementById('chat-img-mode');
    const denoiseEl = document.getElementById('chat-denoise');
    const denoiseValEl = document.getElementById('chat-denoise-val');
    if (chatInp) {
      chatInp.value = chatAttachedImagePath
        ? `${raceItem[1]} ${classItem[1]} (${rs.name}), ${bgItem[1].replace(/^[^\w]+/, '')}, ${styleObj.label}`
        : `/draw ${fullPrompt}`;
      chatInp.focus();
    }
    if (modeSel) modeSel.value = styleObj.mode === 'reactor' ? 'reactor' : 'edit';
    if (denoiseEl) {
      denoiseEl.value = styleObj.denoise;
      if (denoiseValEl) denoiseValEl.textContent = parseFloat(styleObj.denoise).toFixed(2);
    }
    return;
  }

  const promptEl = document.getElementById('gen-prompt');
  const denoiseEl = document.getElementById('gen-denoise');
  const denoiseValEl = document.getElementById('studio-denoise-val');
  const reactorEl = document.getElementById('gen-enable-reactor');
  const editInstEl = document.getElementById('studio-edit-instruction');
  const resEl = document.getElementById('gen-res');

  if (promptEl) promptEl.value = fullPrompt;
  if (styleObj.resolution && resEl) resEl.value = styleObj.resolution;
  if (editInstEl) editInstEl.value = `${raceItem[1]} ${classItem[1]} (${rs.name})`;
  if (denoiseEl) {
    denoiseEl.value = styleObj.denoise;
    if (denoiseValEl) denoiseValEl.textContent = parseFloat(styleObj.denoise).toFixed(2);
  }
  if (reactorEl) {
    reactorEl.checked = (styleObj.mode === 'reactor' && Boolean(studioInputImagePath));
  }
  const statusEl = document.getElementById('gen-status');
  if (statusEl) {
    statusEl.textContent = `⚔️ Loaded ${rs.name}: ${raceItem[1]} ${classItem[1]}! Click 'Generate Image Now' to render.`;
  }
}

function randomizeTtrpgPreset(prefix='studio') {
  const ids = _ttrpgIds(prefix);
  const rsKey = document.getElementById(ids.ruleset)?.value || 'dnd5e';
  const rs = TTRPG_RULESETS[rsKey];
  if (!rs) return;
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)][0];
  document.getElementById(ids.race).value = pick(rs.races);
  document.getElementById(ids.cls).value = pick(rs.classes);
  document.getElementById(ids.backdrop).value = pick(rs.backdrops);
  applyTtrpgPreset(prefix);
}

function clearChatMask() {
  const canvas = document.getElementById('chat-mask-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  chatMaskHasStrokes = false;
}

function setStudioInputImage(diskPath, url, w=null, h=null, recRes=null) {
  studioInputImagePath = diskPath;
  const img = document.getElementById('studio-img-preview');
  img.src = url;
  document.getElementById('studio-img-preview-box').style.display = 'block';
  document.getElementById('btn-clear-studio-img').style.display = 'inline-flex';
  if (w && h) {
    document.getElementById('studio-img-info').textContent = `Uploaded: ${w}×${h} px → Nearest SDXL Preset: ${recRes}`;
  } else {
    document.getElementById('studio-img-info').textContent = `Loaded for Img2Img Editing`;
  }
  if (recRes) {
    const sel = document.getElementById('gen-res');
    for (const opt of sel.options) {
      if (opt.value === recRes) {
        sel.value = recRes;
        break;
      }
    }
  }
  clearStudioMask();
  setTimeout(() => {
    initMaskCanvas('studio-mask-canvas', 'studio-img-preview');
    setupCanvasDrawing('studio-mask-canvas', 'studio-img-preview', false);
  }, 100);
}

function clearStudioInputImage() {
  studioInputImagePath = '';
  document.getElementById('studio-input-file').value = '';
  document.getElementById('studio-img-preview-box').style.display = 'none';
  document.getElementById('btn-clear-studio-img').style.display = 'none';
  clearStudioMask();
}

async function describeOrEditInputImage() {
  if (!studioInputImagePath) return alert('Upload an input image first.');
  const inst = document.getElementById('studio-edit-instruction').value.trim();
  const statusEl = document.getElementById('gen-status');
  statusEl.textContent = '🔍 Vision AI is analyzing your image and writing the SDXL prompt...';
  const res = await api('/api/describe-image', 'POST', {
    image_path: studioInputImagePath,
    edit_instruction: inst
  });
  if (res.ok && res.prompt) {
    document.getElementById('gen-prompt').value = res.prompt;
    statusEl.textContent = '✅ Vision AI wrote the updated prompt! Click Generate Image Now to apply.';
  } else {
    statusEl.textContent = '❌ Could not analyze image: ' + (res.error || '');
  }
}

async function generateImage() {
  let prompt = document.getElementById('gen-prompt').value.trim();
  const editInst = document.getElementById('studio-edit-instruction').value.trim();
  const [w, h] = document.getElementById('gen-res').value.split('x').map(Number);
  const btn = document.getElementById('btn-generate');
  const statusEl = document.getElementById('gen-status');
  btn.disabled = true;

  try {
    if (studioInputImagePath && !prompt && editInst) {
      statusEl.textContent = '🔍 Vision AI is building the edit prompt from your image...';
      const descRes = await api('/api/describe-image', 'POST', {
        image_path: studioInputImagePath,
        edit_instruction: editInst
      });
      if (descRes.ok && descRes.prompt) {
        prompt = descRes.prompt;
        document.getElementById('gen-prompt').value = prompt;
      }
    }
    if (!prompt) {
      btn.disabled = false;
      return alert('Please enter a prompt (or upload an image and describe what to change).');
    }

    const activeSkillId = document.getElementById('gen-skill').value;
    if (activeSkillId) {
      const sk = studioSkillsCache.find(s => s.id === activeSkillId);
      if (sk) {
        const pLower = prompt.toLowerCase();
        if (sk.prompt_prefix && !pLower.includes(sk.prompt_prefix.toLowerCase())) {
          prompt = `${sk.prompt_prefix}, ${prompt}`;
        }
        if (sk.prompt_suffix && !pLower.includes(sk.prompt_suffix.toLowerCase())) {
          prompt = `${prompt}, ${sk.prompt_suffix}`;
        }
      }
    }

    const maskB64 = studioInputImagePath ? getMaskCanvasAsBase64('studio-mask-canvas') : '';
    const isMaskInpaint = Boolean(maskB64);

    statusEl.textContent = isMaskInpaint
      ? '⏳ Inpainting painted brush zone via ComfyUI (100% of unpainted face/photo locked)...'
      : (studioInputImagePath
        ? '⏳ Editing image via ComfyUI Img2Img on RTX 4070...'
        : '⏳ Generating on RTX 4070 via ComfyUI...');

    const res = await api('/api/generate', 'POST', {
      prompt,
      negative_prompt: document.getElementById('gen-neg').value,
      checkpoint: document.getElementById('gen-ckpt').value,
      lora_name: document.getElementById('gen-lora').value,
      lora_strength: parseFloat(document.getElementById('gen-lora-str').value || '0.8'),
      width: w,
      height: h,
      batch_size: parseInt(document.getElementById('gen-batch').value || '1'),
      steps: parseInt(document.getElementById('gen-steps').value || '28'),
      cfg: parseFloat(document.getElementById('gen-cfg').value || '5.5'),
      seed: parseInt(document.getElementById('gen-seed').value || '-1'),
      sampler: document.getElementById('gen-sampler').value,
      scheduler: document.getElementById('gen-scheduler').value,
      input_image: studioInputImagePath,
      mask_image_b64: maskB64,
      original_face_image: studioInputImagePath,
      preserve_face: document.getElementById('gen-preserve-face').checked,
      enable_reactor: document.getElementById('gen-enable-reactor').checked,
      denoise: parseFloat(document.getElementById('gen-denoise').value || (isMaskInpaint ? '0.80' : '0.60')),
      scale_to_resolution: document.getElementById('gen-scale-res').checked,
      apply_learned_memory: document.getElementById('chk-use-learned-memory').checked
    });
    if (res.ok) {
      statusEl.textContent = `✅ Done! Seed: ${res.seed}`;
      loadGallery();
    } else {
      statusEl.textContent = '❌ Error: ' + (res.error || 'Unknown error');
    }
  } catch (e) {
    statusEl.textContent = '❌ Error: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

async function loadGallery() {
  const res = await api('/api/gallery');
  const gal = document.getElementById('image-gallery');
  gal.innerHTML = '';
  (res.images || []).forEach(img => {
    const escapedPath = img.disk_path.replace(/\\/g, '\\\\');
    const escapedName = img.filename.replace(/'/g, "\\'");
    const div = document.createElement('div');
    div.className = 'img-card';
    div.innerHTML = `
      <img src="${img.url}" onclick="window.open('${img.url}', '_blank')" title="Click to view full size">
      <div class="actions">
        <button class="btn amber" style="flex:1; padding:6px; font-size:11px;" onclick="openFixAndTeachInStudio('${escapedPath}', '${img.url}')" title="Fix flaws in this image & teach AI rule">🔧 Fix</button>
        <button class="btn secondary" style="flex:1; padding:6px; font-size:11px;" onclick="editImageInStudio('${escapedPath}', '${img.url}')">✏️ Edit</button>
        <button class="btn secondary" style="flex:1; padding:6px; font-size:11px; border-color:#10b981; color:#a7f3d0;" onclick="setDccPortraitPath('${escapedPath}', '${img.url}'); switchTab('dcc', document.getElementById('nav-btn-dcc'));" title="Use as DCC Character Portrait">🎲 Portrait</button>
        <button class="btn secondary" style="padding:6px 8px; font-size:11px; border-color:var(--red); color:#fca5a5;" onclick="deleteGalleryImage('${escapedName}')" title="Delete this image">🗑️</button>
      </div>
    `;
    gal.appendChild(div);
  });
}

async function deleteGalleryImage(filename) {
  const res = await api('/api/gallery/delete', 'POST', { filename });
  if (res.ok) {
    if (studioInputImagePath && studioInputImagePath.endsWith(filename)) {
      clearStudioInputImage();
    }
    loadGallery();
  } else {
    alert('Failed to delete image: ' + (res.error || 'Unknown error'));
  }
}

async function deleteAllGalleryImages() {
  if (!confirm('Are you sure you want to delete ALL images in the gallery?')) return;
  const res = await api('/api/gallery/delete', 'POST', { delete_all: true });
  if (res.ok) {
    clearStudioInputImage();
    loadGallery();
  }
}

function editImageInStudio(diskPath, url) {
  setStudioInputImage(diskPath, url);
  document.querySelectorAll('nav button')[0].click();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function openFixAndTeachInStudio(diskPath, url) {
  setStudioInputImage(diskPath, url);
  document.querySelectorAll('nav button')[0].click();
  window.scrollTo({ top: 0, behavior: 'smooth' });
  const inp = document.getElementById('studio-edit-instruction');
  inp.focus();
  inp.placeholder = "Describe what went wrong (e.g. 'fix hands, skin looks too plastic, make hair darker') & click 🔧 Fix & Teach AI Now";
}

function editImageInChat(diskPath, url) {
  if (!chatOriginalImagePath) {
    chatOriginalImagePath = diskPath;
    chatOriginalImageUrl = url;
  }
  chatAttachedImagePath = diskPath;
  chatAttachedImageUrl = url;
  document.getElementById('chat-img-preview').src = url;
  if (chatOriginalImagePath && chatOriginalImagePath !== chatAttachedImagePath) {
    document.getElementById('chat-img-meta').textContent = 'Editing current canvas (🔒 Original Face Context Locked)';
    document.getElementById('btn-reset-chat-orig').style.display = 'inline-flex';
  } else {
    document.getElementById('chat-img-meta').textContent = 'Original Reference Image (🔒 Face Identity Locked)';
    document.getElementById('btn-reset-chat-orig').style.display = 'none';
  }
  document.getElementById('chat-img-controls').style.display = 'flex';
  document.getElementById('btn-clear-chat-img').style.display = 'inline-flex';
  document.getElementById('chat-img-mode').value = 'edit';
  document.getElementById('chat-input').focus();
}

async function uploadChatImage() {
  const input = document.getElementById('chat-file');
  if (!input.files || !input.files.length) return;
  const file = input.files[0];
  const b64 = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.readAsDataURL(file);
  });
  const res = await api('/api/upload', 'POST', { filename: file.name, data_b64: b64 });
  if (res.ok) {
    chatOriginalImagePath = res.disk_path;
    chatOriginalImageUrl = res.url;
    chatAttachedImagePath = res.disk_path;
    chatAttachedImageUrl = res.url;
    const img = document.getElementById('chat-img-preview');
    img.src = res.url;
    document.getElementById('chat-img-meta').textContent = `Original: ${res.width}×${res.height} px (SDXL Target: ${res.recommended_res} • 🔒 Face Locked)`;
    document.getElementById('chat-img-controls').style.display = 'flex';
    document.getElementById('btn-clear-chat-img').style.display = 'inline-flex';
    document.getElementById('btn-reset-chat-orig').style.display = 'none';
    clearChatMask();
    setTimeout(() => {
      initMaskCanvas('chat-mask-canvas', 'chat-img-preview');
      setupCanvasDrawing('chat-mask-canvas', 'chat-img-preview', true);
    }, 100);
  }
}

function resetChatToOriginalImage() {
  if (!chatOriginalImagePath) return;
  chatAttachedImagePath = chatOriginalImagePath;
  chatAttachedImageUrl = chatOriginalImageUrl;
  const img = document.getElementById('chat-img-preview');
  img.src = chatOriginalImageUrl;
  document.getElementById('chat-img-meta').textContent = 'Reverted to Original Reference Photo (🔒 Face Locked)';
  document.getElementById('btn-reset-chat-orig').style.display = 'none';
  clearChatMask();
  setTimeout(() => {
    initMaskCanvas('chat-mask-canvas', 'chat-img-preview');
  }, 100);
}

function clearChatImage() {
  chatAttachedImagePath = '';
  chatAttachedImageUrl = '';
  chatOriginalImagePath = '';
  chatOriginalImageUrl = '';
  document.getElementById('chat-file').value = '';
  document.getElementById('chat-img-controls').style.display = 'none';
  document.getElementById('btn-clear-chat-img').style.display = 'none';
  document.getElementById('btn-reset-chat-orig').style.display = 'none';
  clearChatMask();
}

async function sendChat() {
  const inp = document.getElementById('chat-input');
  const text = inp.value.trim();
  if (!text && !chatAttachedImagePath) return;
  inp.value = '';
  const box = document.getElementById('chat-box');
  const btn = document.getElementById('btn-chat-send');
  btn.disabled = true;

  let userThumb = '';
  if (chatAttachedImageUrl) {
    userThumb = `<div style="margin-top:6px;"><img src="${chatAttachedImageUrl}" style="max-width:140px; border-radius:6px; border:1px solid #c4b5fd;"></div>`;
  }
  box.innerHTML += `<div class="msg user">You: ${text || '(Attached Image)'}${userThumb}</div>`;
  const waitingId = 'wait-' + Date.now();
  box.innerHTML += `<div class="msg assistant" id="${waitingId}">⏳ Working on your request...</div>`;
  box.scrollTop = box.scrollHeight;

  try {
    const chatMaskB64 = chatAttachedImagePath ? getMaskCanvasAsBase64('chat-mask-canvas') : '';
    const res = await api('/api/chat', 'POST', {
      message: text,
      history: chatHistory,
      image_path: chatAttachedImagePath,
      mask_image_b64: chatMaskB64,
      original_image_path: chatOriginalImagePath || chatAttachedImagePath,
      preserve_face: document.getElementById('chat-preserve-face').checked,
      denoise: parseFloat(document.getElementById('chat-denoise').value || (chatMaskB64 ? '0.80' : '0.60')),
      action_mode: document.getElementById('chat-img-mode').value,
      dcc_mode: document.getElementById('chat-dcc-mode').checked,
      dcc_character: document.getElementById('chat-dcc-mode').checked ? getDccFormState() : null,
      sw5e_mode: document.getElementById('chat-sw5e-mode').checked,
      sw5e_character: document.getElementById('chat-sw5e-mode').checked ? getSw5eCharState() : null,
      sw5e_ship: document.getElementById('chat-sw5e-mode').checked ? getSw5eShipState() : null,
      dm_mode: document.getElementById('chat-dm-mode').checked,
      dm_system: document.getElementById('chat-dm-system').value,
      dnd5e_mode: document.getElementById('chat-dnd5e-mode').checked,
      dnd5e_character: document.getElementById('chat-dnd5e-mode').checked ? getDnd5eCharState() : null
    });
    chatHistory.push({ role: 'user', content: text });
    chatHistory.push({ role: 'assistant', content: res.reply || '' });

    let imgHtml = '';
    (res.images || []).forEach(u => {
      const fname = u.split('/').pop();
      const diskP = `C:\\\\AI_Workspace\\\\outputs\\\\images\\\\${fname}`;
      imgHtml += `
        <div style="margin-top:10px;">
          <img src="${u}" onclick="window.open('${u}', '_blank')" style="max-width:340px; border-radius:8px; border:1px solid #8b5cf6; cursor:pointer; display:block;">
          <div style="display:flex; gap:8px; margin-top:6px;">
            <button class="btn secondary" style="padding:5px 10px; font-size:11px;" onclick="editImageInChat('${diskP}', '${u}')">✏️ Keep Editing This Image in Chat</button>
            <button class="btn secondary" style="padding:5px 10px; font-size:11px;" onclick="editImageInStudio('${diskP}', '${u}')">🎨 Open in Image Studio</button>
          </div>
        </div>`;
    });

    if (res.images && res.images.length && chatAttachedImagePath) {
      const latestUrl = res.images[0];
      const latestFname = latestUrl.split('/').pop();
      const latestDiskPath = `C:\\AI_Workspace\\outputs\\images\\${latestFname}`;
      if (!chatOriginalImagePath) {
        chatOriginalImagePath = chatAttachedImagePath;
        chatOriginalImageUrl = chatAttachedImageUrl;
      }
      chatAttachedImagePath = latestDiskPath;
      chatAttachedImageUrl = latestUrl;
      document.getElementById('chat-img-preview').src = latestUrl;
      document.getElementById('chat-img-meta').textContent = 'Canvas updated to latest edit (🔒 Original Face Locked from first upload)';
      document.getElementById('btn-reset-chat-orig').style.display = 'inline-flex';
      clearChatMask();
      setTimeout(() => {
        initMaskCanvas('chat-mask-canvas', 'chat-img-preview');
      }, 100);
    }
    let skillBtnHtml = '';
    if (res.created_skill && res.created_skill.id) {
      await loadStudioSkills(res.created_skill.id);
      skillBtnHtml = `
        <div style="margin-top:10px;">
          <button class="btn amber" style="padding:7px 14px; font-size:12px;" onclick="useSkillInStudio('${res.created_skill.id}')">⚡ Activate & Open "${res.created_skill.name}" in Image Studio</button>
        </div>`;
    }
    if (res.learned_memory) {
      renderLearnedMemory(res.learned_memory);
    }
    if (res.dcc_character) {
      applyDccCharacterToForm(res.dcc_character);
      await refreshDccList(res.dcc_character.id);
      skillBtnHtml += `
        <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn" style="padding:7px 14px; font-size:12px; background:#10b981; color:#042f2e; font-weight:700;" onclick="switchTab('dcc', document.getElementById('nav-btn-dcc'))">🎲 Open "${res.dcc_character.name || 'Crawler'}" in DCC Sheet &amp; Journal</button>
        </div>`;
    }
    if (res.sw5e_character || res.sw5e_ship) {
      if (res.sw5e_character) applySw5eCharToForm(res.sw5e_character);
      if (res.sw5e_ship) applySw5eShipToForm(res.sw5e_ship);
      await refreshSw5eLists(res.sw5e_character?.id || '', res.sw5e_ship?.id || '');
      skillBtnHtml += `
        <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn" style="padding:7px 14px; font-size:12px; background:#38bdf8; color:#082f49; font-weight:700;" onclick="switchTab('sw5e', document.getElementById('nav-btn-sw5e'))">🚀 Open in SW5e Character &amp; Ship Builder</button>
        </div>`;
    }
    if (res.dm_citations && res.dm_citations.length) {
      const cites = res.dm_citations.map(c => `<span class="badge" style="font-size:10px; padding:2px 7px;">📖 ${c.book} (p. ${c.page})</span>`).join(' ');
      skillBtnHtml += `<div style="margin-top:10px; display:flex; gap:6px; flex-wrap:wrap; align-items:center;">${cites}</div>`;
    }
    if (res.dnd5e_character) {
      applyDnd5eCharToForm(res.dnd5e_character);
      await refreshDnd5eList(res.dnd5e_character.id);
      skillBtnHtml += `
        <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn" style="padding:7px 14px; font-size:12px; background:#ef4444; color:#fff; font-weight:700;" onclick="switchTab('dnd5e', document.getElementById('nav-btn-dnd5e'))">🐉 Open "${res.dnd5e_character.name || 'Character'}" in D&amp;D 5e Sheet</button>
        </div>`;
    }
    const waitEl = document.getElementById(waitingId);
    if (waitEl) {
      waitEl.innerHTML = `${(res.reply || res.error || '').replace(/\n/g, '<br>')}${skillBtnHtml}${imgHtml}`;
    }
    box.scrollTop = box.scrollHeight;
    if (res.images && res.images.length) loadGallery();
  } catch (e) {
    const waitEl = document.getElementById(waitingId);
    if (waitEl) waitEl.textContent = '❌ Error: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

async function saveSettings() {
  await api('/api/config', 'POST', {
    setup_mode: document.getElementById('cfg-setup-mode').value,
    llm_provider_mode: document.getElementById('cfg-llm-mode').value,
    cloud_provider: document.getElementById('cfg-cloud-provider').value,
    gemini_model: document.getElementById('cfg-gemini-model').value,
    openai_model: document.getElementById('cfg-openai-model').value.trim(),
    anthropic_model: document.getElementById('cfg-anthropic-model').value.trim(),
    gemini_api_key: document.getElementById('cfg-gemini-key').value.trim(),
    openai_api_key: document.getElementById('cfg-openai-key').value.trim(),
    anthropic_api_key: document.getElementById('cfg-anthropic-key').value.trim()
  });
  await refreshStatus();
  alert('Settings saved!');
}

async function openSetupWizard() {
  document.getElementById('setup-wizard-modal').style.display = 'block';
  await refreshSetupWizardStatus();
}

function closeSetupWizard() {
  document.getElementById('setup-wizard-modal').style.display = 'none';
}

function selectWizardMode(mode) {
  document.querySelectorAll('input[name="wiz-mode"]').forEach(r => { r.checked = (r.value === mode); });
  document.getElementById('wiz-local-box').style.display = (mode === 'cloud') ? 'none' : 'block';
  document.getElementById('wiz-cloud-box').style.display = (mode === 'local') ? 'none' : 'block';
}

async function refreshSetupWizardStatus() {
  try {
    const st = await api('/api/setup/status');
    document.getElementById('wiz-data-dir').textContent = st.data_dir || '';
    const cfg = st.config || {};
    selectWizardMode(cfg.setup_mode || 'hybrid');
    document.getElementById('wiz-cloud-provider').value = cfg.cloud_provider || 'gemini';
    document.getElementById('wiz-gemini-key').value = cfg.gemini_api_key || '';
    document.getElementById('wiz-openai-key').value = cfg.openai_api_key || '';
    document.getElementById('wiz-anthropic-key').value = cfg.anthropic_api_key || '';
    document.getElementById('wiz-ollama-model').value = cfg.ollama_model || 'qwen2.5:7b';

    const ol = st.ollama || {};
    const olEl = document.getElementById('wiz-ollama-status');
    olEl.innerHTML = ol.online
      ? `<span style="color:#6ee7b7;">Online</span> (${(ol.models || []).join(', ') || 'no models pulled yet'})`
      : `<span style="color:#fca5a5;">Not detected on 11434</span> (<a href="https://ollama.com/download" target="_blank" style="color:#7dd3fc;">Install Ollama</a>)`;

    const pEl = document.getElementById('wiz-ollama-pull');
    if (ol.pull && ol.pull.pulling) {
      pEl.textContent = `⏳ Pulling ${ol.pull.model}: ${ol.pull.status} (${ol.pull.percent}%)`;
      setTimeout(refreshSetupWizardStatus, 2000);
    } else if (ol.pull && ol.pull.status) {
      pEl.textContent = ol.pull.status;
    }

    const pages = (st.rules_status && st.rules_status.indexed_pages) || {};
    ['dcc', 'dnd5e', 'sw5e'].forEach(k => {
      const el = document.getElementById(`wiz-rb-${k}`);
      if (el) {
        const cnt = pages[k] || 0;
        el.innerHTML = cnt > 0
          ? `<span style="color:#6ee7b7;">✅ Unlocked (${cnt} pages)</span>`
          : `<span style="color:#fde68a;">🔒 Locked (drop PDF below)</span>`;
      }
    });
  } catch (e) {}
}

async function pullOllamaFromWizard() {
  const model = document.getElementById('wiz-ollama-model').value.trim() || 'qwen2.5:7b';
  await api('/api/ollama/pull', 'POST', { model });
  setTimeout(refreshSetupWizardStatus, 600);
}

async function uploadRulebookPdf(sysKey, inp) {
  if (!inp.files || !inp.files.length) return;
  const f = inp.files[0];
  const b64 = await new Promise(res => {
    const r = new FileReader();
    r.onload = () => res(r.result.split(',')[1]);
    r.readAsDataURL(f);
  });
  await api('/api/rules/upload', 'POST', { system: sysKey, filename: f.name, data_b64: b64 });
  setTimeout(() => { refreshSetupWizardStatus(); refreshRulesIndexStatus(); }, 1500);
}

async function saveAndFinishWizard() {
  let mode = 'hybrid';
  document.querySelectorAll('input[name="wiz-mode"]').forEach(r => { if (r.checked) mode = r.value; });
  await api('/api/config', 'POST', {
    setup_completed: true,
    setup_mode: mode,
    cloud_provider: document.getElementById('wiz-cloud-provider').value,
    gemini_api_key: document.getElementById('wiz-gemini-key').value.trim(),
    openai_api_key: document.getElementById('wiz-openai-key').value.trim(),
    anthropic_api_key: document.getElementById('wiz-anthropic-key').value.trim(),
    ollama_model: document.getElementById('wiz-ollama-model').value.trim() || 'qwen2.5:7b'
  });
  closeSetupWizard();
  location.reload();
}

// ============================================================================
// DCC CHARACTER SHEET & JOURNAL BUILDER
// ============================================================================
let currentDccId = '';

function prefillDccPrompt() {
  document.getElementById('chat-dcc-mode').checked = true;
  const inp = document.getElementById('chat-input');
  inp.value = '/dcc Create a Level 1 Human Crawler named Carl (He/Him), Crawler #4122, STR 5 INT 4 CON 5 DEX 4 CHA 3. Background: Childhood (Biking, Scrap Collecting), Adolescence (Boxing, Lockpicking), Career (Coast Guard Tech, Marine Mechanics), Hobbies (Cat Care, Demolition). Equipment: Leather Jacket, Boxers.';
  inp.focus();
}

async function initDccTab() {
  await refreshDccList();
  await refreshDccPortraitGallery();
}

async function refreshDccList(selectId='') {
  try {
    const data = await api('/api/dcc/characters');
    const sel = document.getElementById('dcc-saved-select');
    if (!sel) return;
    sel.innerHTML = '<option value="">-- New Crawler --</option>';
    (data.characters || []).forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.name || c.id} (Lv.${c.level || 0} ${c.race || ''})`;
      sel.appendChild(opt);
    });
    if (selectId) {
      sel.value = selectId;
      currentDccId = selectId;
    } else if (!currentDccId && data.default_character) {
      applyDccCharacterToForm(data.default_character);
    }
    if (data.rules) {
      document.getElementById('dcc-rules-json').value = JSON.stringify(data.rules, null, 2);
    }
  } catch (e) { console.error('initDccTab error:', e); }
}

async function loadSelectedDccCharacter() {
  const id = document.getElementById('dcc-saved-select').value;
  if (!id) { newDccCharacter(); return; }
  const res = await api('/api/dcc/character?id=' + encodeURIComponent(id));
  if (res.ok && res.character) {
    currentDccId = res.character.id;
    applyDccCharacterToForm(res.character);
  }
}

async function newDccCharacter() {
  currentDccId = '';
  document.getElementById('dcc-saved-select').value = '';
  const data = await api('/api/dcc/characters');
  if (data.default_character) applyDccCharacterToForm(data.default_character);
}

function getDccFormState() {
  const attacks = [];
  document.querySelectorAll('#dcc-attacks-list .dcc-atk-row').forEach(row => {
    attacks.push({
      name: row.querySelector('.atk-name').value.trim(),
      rank: parseInt(row.querySelector('.atk-rank').value || '3', 10),
      stat: row.querySelector('.atk-stat').value,
      damage_dice: row.querySelector('.atk-dmg').value.trim() || '1d4',
      effects: row.querySelector('.atk-fx').value.trim()
    });
  });
  const skills = [];
  document.querySelectorAll('#dcc-skills-list .dcc-sk-row').forEach(row => {
    skills.push({
      name: row.querySelector('.sk-name').value.trim(),
      origin: row.querySelector('.sk-orig').value.trim(),
      rank: parseInt(row.querySelector('.sk-rank').value || '1', 10),
      stat: row.querySelector('.sk-stat').value,
      check_type: row.querySelector('.sk-type').value,
      notes: row.querySelector('.sk-notes').value.trim()
    });
  });
  return {
    id: currentDccId,
    name: document.getElementById('dcc-name').value.trim(),
    race: document.getElementById('dcc-race').value.trim(),
    gender: document.getElementById('dcc-gender').value.trim(),
    level: document.getElementById('dcc-level').value.trim(),
    crawler_number: document.getElementById('dcc-number').value.trim(),
    class_name: document.getElementById('dcc-class').value.trim(),
    floor: document.getElementById('dcc-floor').value.trim(),
    size: document.getElementById('dcc-size').value.trim(),
    move: document.getElementById('dcc-move').value.trim(),
    step: document.getElementById('dcc-step').value.trim(),
    ai_favor: document.getElementById('dcc-aifavor').value.trim(),
    portrait_path: document.getElementById('dcc-portrait-path').value.trim(),
    stats: {
      STR: { unenhanced: parseInt(document.getElementById('dcc-str-un').value || '4', 10), enhanced: parseInt(document.getElementById('dcc-str-en').value || '4', 10) },
      INT: { unenhanced: parseInt(document.getElementById('dcc-int-un').value || '4', 10), enhanced: parseInt(document.getElementById('dcc-int-en').value || '4', 10) },
      CON: { unenhanced: parseInt(document.getElementById('dcc-con-un').value || '4', 10), enhanced: parseInt(document.getElementById('dcc-con-en').value || '4', 10) },
      DEX: { unenhanced: parseInt(document.getElementById('dcc-dex-un').value || '4', 10), enhanced: parseInt(document.getElementById('dcc-dex-en').value || '4', 10) },
      CHA: { unenhanced: parseInt(document.getElementById('dcc-cha-un').value || '4', 10), enhanced: parseInt(document.getElementById('dcc-cha-en').value || '4', 10) }
    },
    vitals: {
      hp_current: parseInt(document.getElementById('dcc-hp-cur').value || '0', 10),
      hp_max: parseInt(document.getElementById('dcc-hp-max').value || '0', 10),
      mana_current: parseInt(document.getElementById('dcc-mana-cur').value || '0', 10),
      mana_max: parseInt(document.getElementById('dcc-mana-max').value || '0', 10),
      evade_buffs: parseInt(document.getElementById('dcc-evade-buff').value || '0', 10),
      armor: parseInt(document.getElementById('dcc-dr-armor').value || '0', 10),
      dr_buffs: parseInt(document.getElementById('dcc-dr-buff').value || '0', 10)
    },
    external_buffs: [
      document.getElementById('dcc-buff-1').value.trim(),
      document.getElementById('dcc-buff-2').value.trim(),
      document.getElementById('dcc-buff-3').value.trim()
    ],
    attacks,
    skills,
    gear: {
      head: document.getElementById('dcc-gear-head').value.trim(),
      torso: document.getElementById('dcc-gear-torso').value.trim(),
      arms: document.getElementById('dcc-gear-arms').value.trim(),
      hands: document.getElementById('dcc-gear-hands').value.trim(),
      legs: document.getElementById('dcc-gear-legs').value.trim(),
      feet: document.getElementById('dcc-gear-feet').value.trim(),
      accessories: document.getElementById('dcc-gear-acc').value.trim()
    },
    past_trauma: document.getElementById('dcc-trauma').value.trim(),
    loose_ends: document.getElementById('dcc-loose').value.trim(),
    regrets: document.getElementById('dcc-regrets').value.trim(),
    notes: document.getElementById('dcc-notes').value.trim()
  };
}

function fmtDccMod(n) { return (n >= 0 ? '+' : '') + n; }

function applyDccCharacterToForm(c) {
  if (!c) return;
  currentDccId = c.id || '';
  document.getElementById('dcc-name').value = c.name || '';
  document.getElementById('dcc-race').value = c.race || 'Human';
  document.getElementById('dcc-gender').value = c.gender || '';
  document.getElementById('dcc-level').value = c.level ?? '0';
  document.getElementById('dcc-number').value = c.crawler_number || '';
  document.getElementById('dcc-class').value = c.class_name || 'None';
  document.getElementById('dcc-floor').value = c.floor || '1';
  document.getElementById('dcc-size').value = c.size || 'Medium';
  document.getElementById('dcc-move').value = c.move || '30 ft';
  document.getElementById('dcc-step').value = c.step || '5 ft';
  document.getElementById('dcc-aifavor').value = c.ai_favor ?? '1';

  const st = c.stats || {};
  ['str','int','con','dex','cha'].forEach(k => {
    const s = st[k.toUpperCase()] || { unenhanced: 4, enhanced: 4, mod: 2 };
    document.getElementById(`dcc-${k}-un`).value = s.unenhanced ?? 4;
    document.getElementById(`dcc-${k}-en`).value = s.enhanced ?? 4;
    document.getElementById(`dcc-${k}-mod`).value = fmtDccMod(s.mod ?? 0);
  });

  const vt = c.vitals || {};
  document.getElementById('dcc-hp-cur').value = vt.hp_current ?? 14;
  document.getElementById('dcc-hp-max').value = vt.hp_max ?? 14;
  document.getElementById('dcc-mana-cur').value = vt.mana_current ?? 9;
  document.getElementById('dcc-mana-max').value = vt.mana_max ?? 9;
  document.getElementById('dcc-evade-buff').value = vt.evade_buffs ?? 0;
  document.getElementById('dcc-evade-tot').value = vt.evade_total ?? 12;
  document.getElementById('dcc-dr-armor').value = vt.armor ?? 0;
  document.getElementById('dcc-dr-buff').value = vt.dr_buffs ?? 0;
  document.getElementById('dcc-dr-tot').value = vt.dr_total ?? 0;
  document.getElementById('dcc-popularity').value = vt.popularity ?? 4;

  const ext = c.external_buffs || ['', '', ''];
  document.getElementById('dcc-buff-1').value = ext[0] || '';
  document.getElementById('dcc-buff-2').value = ext[1] || '';
  document.getElementById('dcc-buff-3').value = ext[2] || '';

  setDccPortraitPath(c.portrait_path || '');

  const atkList = document.getElementById('dcc-attacks-list');
  atkList.innerHTML = '';
  (c.attacks || []).forEach(a => addDccAttackRow(a));

  const skList = document.getElementById('dcc-skills-list');
  skList.innerHTML = '';
  (c.skills || []).forEach(s => addDccSkillRow(s));

  const gr = c.gear || {};
  document.getElementById('dcc-gear-head').value = gr.head || '';
  document.getElementById('dcc-gear-torso').value = gr.torso || '';
  document.getElementById('dcc-gear-arms').value = gr.arms || '';
  document.getElementById('dcc-gear-hands').value = gr.hands || '';
  document.getElementById('dcc-gear-legs').value = gr.legs || '';
  document.getElementById('dcc-gear-feet').value = gr.feet || '';
  document.getElementById('dcc-gear-acc').value = gr.accessories || '';

  document.getElementById('dcc-trauma').value = c.past_trauma || '';
  document.getElementById('dcc-loose').value = c.loose_ends || '';
  document.getElementById('dcc-regrets').value = c.regrets || '';
  document.getElementById('dcc-notes').value = c.notes || '';
}

function addDccAttackRow(a={}) {
  const list = document.getElementById('dcc-attacks-list');
  const div = document.createElement('div');
  div.className = 'dcc-atk-row';
  div.style.cssText = 'display:grid; grid-template-columns:2fr 60px 70px 80px 2fr 30px; gap:4px; align-items:center;';
  div.innerHTML = `
    <input class="atk-name" placeholder="Attack Name" value="${(a.name || '').replace(/"/g, '&quot;')}">
    <input class="atk-rank" type="number" title="Rank" value="${a.rank ?? 3}">
    <select class="atk-stat">
      <option value="STR" ${a.stat==='STR'?'selected':''}>STR</option>
      <option value="DEX" ${a.stat==='DEX'?'selected':''}>DEX</option>
      <option value="INT" ${a.stat==='INT'?'selected':''}>INT</option>
      <option value="CON" ${a.stat==='CON'?'selected':''}>CON</option>
      <option value="CHA" ${a.stat==='CHA'?'selected':''}>CHA</option>
    </select>
    <input class="atk-dmg" placeholder="1d4" value="${(a.damage_dice || '1d4').replace(/"/g, '&quot;')}">
    <input class="atk-fx" placeholder="Effects / Check / AI Favor" value="${(a.effects || '').replace(/"/g, '&quot;')}">
    <button type="button" class="btn secondary" style="padding:4px 6px; color:#fca5a5;" onclick="this.parentElement.remove()">✖</button>
  `;
  list.appendChild(div);
}

function addDccSkillRow(s={}) {
  const list = document.getElementById('dcc-skills-list');
  const div = document.createElement('div');
  div.className = 'dcc-sk-row';
  div.style.cssText = 'display:grid; grid-template-columns:2fr 1.2fr 55px 75px 1.2fr 1.5fr 30px; gap:4px; align-items:center;';
  div.innerHTML = `
    <input class="sk-name" placeholder="Skill Name" value="${(s.name || '').replace(/"/g, '&quot;')}">
    <input class="sk-orig" placeholder="Origin" value="${(s.origin || '').replace(/"/g, '&quot;')}">
    <input class="sk-rank" type="number" min="1" value="${s.rank ?? 1}">
    <select class="sk-stat">
      <option value="STR" ${s.stat==='STR'?'selected':''}>STR</option>
      <option value="INT" ${s.stat==='INT'?'selected':''}>INT</option>
      <option value="CON" ${s.stat==='CON'?'selected':''}>CON</option>
      <option value="DEX" ${s.stat==='DEX'?'selected':''}>DEX</option>
      <option value="CHA" ${s.stat==='CHA'?'selected':''}>CHA</option>
      <option value="None" ${(!s.stat || s.stat==='None')?'selected':''}>None</option>
    </select>
    <select class="sk-type">
      <option value="Unopposed" ${s.check_type==='Unopposed'?'selected':''}>Unopposed</option>
      <option value="Opposed" ${s.check_type==='Opposed'?'selected':''}>Opposed</option>
      <option value="Passive" ${s.check_type==='Passive'?'selected':''}>Passive</option>
      <option value="Evade" ${s.check_type==='Evade'?'selected':''}>Evade</option>
    </select>
    <input class="sk-notes" placeholder="Notes" value="${(s.notes || '').replace(/"/g, '&quot;')}">
    <button type="button" class="btn secondary" style="padding:4px 6px; color:#fca5a5;" onclick="this.parentElement.remove()">✖</button>
  `;
  list.appendChild(div);
}

async function recalcDccCharacter() {
  const st = getDccFormState();
  // Clear hp_max/mana_max if user wants formula recalc? Only recalc mods/evade/dr/pop; keep explicit HP/Mana unless 0
  const res = await api('/api/dcc/calculate', 'POST', st);
  if (res.ok && res.character) applyDccCharacterToForm(res.character);
}

async function saveDccCharacter() {
  const res = await api('/api/dcc/save', 'POST', getDccFormState());
  if (res.ok && res.character) {
    applyDccCharacterToForm(res.character);
    await refreshDccList(res.character.id);
  }
}

async function deleteDccCharacter() {
  if (!currentDccId) return;
  if (!confirm('Delete this saved Crawler?')) return;
  await api('/api/dcc/delete', 'POST', { id: currentDccId });
  await newDccCharacter();
  await refreshDccList();
}

function setDccPortraitPath(diskPath, previewUrl='') {
  document.getElementById('dcc-portrait-path').value = diskPath || '';
  const img = document.getElementById('dcc-portrait-preview');
  const empty = document.getElementById('dcc-portrait-empty');
  if (diskPath) {
    const fname = diskPath.split(/[\\/]/).pop();
    img.src = previewUrl || ('/outputs/images/' + encodeURIComponent(fname));
    img.style.display = 'block';
    empty.style.display = 'none';
  } else {
    img.src = '';
    img.style.display = 'none';
    empty.style.display = 'block';
  }
}

function clearDccPortrait() { setDccPortraitPath(''); }

async function refreshDccPortraitGallery() {
  try {
    const g = await api('/api/gallery');
    const box = document.getElementById('dcc-portrait-gallery');
    if (!box) return;
    box.innerHTML = '';
    (g.images || []).slice(0, 18).forEach(im => {
      const thumb = document.createElement('img');
      thumb.src = im.url;
      thumb.title = im.filename;
      thumb.style.cssText = 'width:52px; height:72px; object-fit:cover; border-radius:4px; border:1px solid var(--border); cursor:pointer;';
      thumb.onclick = () => setDccPortraitPath(im.disk_path, im.url);
      box.appendChild(thumb);
    });
  } catch (e) {}
}

async function exportDccPdfs(exportSheet, exportJournal) {
  const statusEl = document.getElementById('dcc-export-status');
  statusEl.innerHTML = '⏳ Generating printable PDFs...';
  const res = await api('/api/dcc/export-pdf', 'POST', {
    character: getDccFormState(),
    export_sheet: exportSheet,
    export_journal: exportJournal
  });
  if (!res.ok) {
    statusEl.innerHTML = `<span style="color:#fca5a5;">❌ Export failed: ${res.error || 'Unknown error'}</span>`;
    return;
  }
  applyDccCharacterToForm(res.character);
  await refreshDccList(res.character.id);
  let links = [];
  if (res.files && res.files.sheet) {
    links.push(`<a href="${res.files.sheet.url}" target="_blank" class="btn secondary" style="display:inline-flex; padding:6px 12px; text-decoration:none; border-color:#8b5cf6; color:#ddd6fe;">📄 Open / Print Character Sheet (${res.files.sheet.filename})</a>`);
  }
  if (res.files && res.files.journal) {
    links.push(`<a href="${res.files.journal.url}" target="_blank" class="btn secondary" style="display:inline-flex; padding:6px 12px; text-decoration:none; border-color:#10b981; color:#a7f3d0;">📘 Open / Print Character Journal (${res.files.journal.filename})</a>`);
  }
  statusEl.innerHTML = `<div style="color:#6ee7b7; margin-bottom:6px;">✅ Exported Session 0 PDFs to <code>C:\\AI_Workspace\\outputs\\dcc\\</code>!</div><div style="display:flex; gap:8px; flex-wrap:wrap;">${links.join('')}</div>`;
}

async function saveDccRulesConfig() {
  try {
    const parsed = JSON.parse(document.getElementById('dcc-rules-json').value);
    const res = await api('/api/dcc/rules', 'POST', parsed);
    if (res.ok) {
      await recalcDccCharacter();
      alert('DCC Rulebook Table 2 & formulas saved!');
    }
  } catch (e) {
    alert('Invalid JSON: ' + e.message);
  }
}

// ============================================================================
// SW5E CHARACTER & STARSHIP BUILDER
// ============================================================================
let currentSw5eCharId = '';
let currentSw5eShipId = '';

function prefillSw5ePrompt() {
  document.getElementById('chat-dcc-mode').checked = false;
  document.getElementById('chat-sw5e-mode').checked = true;
  const inp = document.getElementById('chat-input');
  inp.value = '/sw5e Create a Level 1 Twi\'lek Operative (Pilot, Scoundrel background, Charmer feat) named Kaelen Voss, plus a Tier 0 Medium YT-1300f Light Freighter named The Kessel Runner.';
  inp.focus();
}

async function initSw5eTab() {
  await refreshSw5eLists();
}

async function refreshSw5eLists(selCharId='', selShipId='') {
  try {
    const data = await api('/api/sw5e/state');
    const cSel = document.getElementById('sw5e-char-select');
    if (cSel) {
      cSel.innerHTML = '<option value="">-- New Character --</option>';
      (data.characters || []).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.name || c.id} (Lv.${c.level || 1} ${c.species || ''} ${c.class_name || ''})`;
        cSel.appendChild(opt);
      });
      if (selCharId) { cSel.value = selCharId; currentSw5eCharId = selCharId; }
      else if (!currentSw5eCharId && data.default_character) applySw5eCharToForm(data.default_character);
    }
    const sSel = document.getElementById('sw5e-ship-select');
    if (sSel) {
      sSel.innerHTML = '<option value="">-- New Starship --</option>';
      (data.ships || []).forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = `${s.name || s.id} (${s.size || ''} Tier ${s.tier ?? 0})`;
        sSel.appendChild(opt);
      });
      if (selShipId) { sSel.value = selShipId; currentSw5eShipId = selShipId; }
      else if (!currentSw5eShipId && data.default_ship) applySw5eShipToForm(data.default_ship);
    }
  } catch (e) { console.error('initSw5eTab error:', e); }
}

async function loadSelectedSw5eChar() {
  const id = document.getElementById('sw5e-char-select').value;
  if (!id) { newSw5eChar(); return; }
  const res = await api('/api/sw5e/character?id=' + encodeURIComponent(id));
  if (res.ok && res.character) applySw5eCharToForm(res.character);
}

async function loadSelectedSw5eShip() {
  const id = document.getElementById('sw5e-ship-select').value;
  if (!id) { newSw5eShip(); return; }
  const res = await api('/api/sw5e/ship?id=' + encodeURIComponent(id));
  if (res.ok && res.ship) applySw5eShipToForm(res.ship);
}

async function newSw5eChar() {
  currentSw5eCharId = '';
  document.getElementById('sw5e-char-select').value = '';
  const data = await api('/api/sw5e/state');
  if (data.default_character) applySw5eCharToForm(data.default_character);
}

async function newSw5eShip() {
  currentSw5eShipId = '';
  document.getElementById('sw5e-ship-select').value = '';
  const data = await api('/api/sw5e/state');
  if (data.default_ship) applySw5eShipToForm(data.default_ship);
}

function addSw5eCharWeapon(w={}) {
  const box = document.getElementById('sw5e-c-weapons');
  const row = document.createElement('div');
  row.className = 'sw5e-cw-row';
  row.style.cssText = 'display:grid; grid-template-columns:2fr 60px 1.4fr 80px 1.4fr 28px; gap:4px; align-items:center;';
  row.innerHTML = `
    <input class="cw-name" placeholder="Blaster Pistol" value="${(w.name||'').replace(/"/g,'&quot;')}">
    <input class="cw-atk" placeholder="+4" value="${(w.attack||'').replace(/"/g,'&quot;')}">
    <input class="cw-dmg" placeholder="1d6+2 Energy" value="${(w.damage||'').replace(/"/g,'&quot;')}">
    <input class="cw-rng" placeholder="40/160" value="${(w.range||'').replace(/"/g,'&quot;')}">
    <input class="cw-misc" placeholder="Blaster, Reload" value="${(w.misc||'').replace(/"/g,'&quot;')}">
    <button type="button" class="btn secondary" style="padding:4px 6px; color:#fca5a5;" onclick="this.parentElement.remove()">✖</button>
  `;
  box.appendChild(row);
}

function addSw5eShipWeapon(w={}) {
  const box = document.getElementById('sw5e-s-weapons');
  const row = document.createElement('div');
  row.className = 'sw5e-sw-row';
  row.style.cssText = 'display:grid; grid-template-columns:2fr 55px 1.4fr 80px 90px 28px; gap:4px; align-items:center;';
  row.innerHTML = `
    <input class="sw-name" placeholder="Dual Laser Cannon" value="${(w.name||'').replace(/"/g,'&quot;')}">
    <input class="sw-atk" placeholder="+3" value="${(w.attack||'').replace(/"/g,'&quot;')}">
    <input class="sw-dmg" placeholder="2d8 Energy" value="${(w.damage||'').replace(/"/g,'&quot;')}">
    <input class="sw-rng" placeholder="300/1200" value="${(w.range||'').replace(/"/g,'&quot;')}">
    <input class="sw-arc" placeholder="Turret 360" value="${(w.arc||'').replace(/"/g,'&quot;')}">
    <button type="button" class="btn secondary" style="padding:4px 6px; color:#fca5a5;" onclick="this.parentElement.remove()">✖</button>
  `;
  box.appendChild(row);
}

function addSw5eCrewRow(c={}) {
  const box = document.getElementById('sw5e-s-crew');
  const row = document.createElement('div');
  row.className = 'sw5e-cr-row';
  row.style.cssText = 'display:grid; grid-template-columns:1.5fr 1fr 28px; gap:4px; align-items:center;';
  row.innerHTML = `
    <input class="cr-name" placeholder="Character Name" value="${(c.name||'').replace(/"/g,'&quot;')}">
    <input class="cr-role" placeholder="Pilot / Gunner / Mechanic" value="${(c.role||'').replace(/"/g,'&quot;')}">
    <button type="button" class="btn secondary" style="padding:4px 6px; color:#fca5a5;" onclick="this.parentElement.remove()">✖</button>
  `;
  box.appendChild(row);
}

function getSw5eCharState() {
  const weapons = [];
  document.querySelectorAll('#sw5e-c-weapons .sw5e-cw-row').forEach(r => {
    weapons.push({
      name: r.querySelector('.cw-name').value.trim(),
      attack: r.querySelector('.cw-atk').value.trim(),
      damage: r.querySelector('.cw-dmg').value.trim(),
      range: r.querySelector('.cw-rng').value.trim(),
      misc: r.querySelector('.cw-misc').value.trim(),
      weight: ''
    });
  });
  const skill_ranks = {};
  document.getElementById('sw5e-c-skills').value.split(',').map(s => s.trim()).filter(Boolean).forEach(s => { skill_ranks[s] = 1; });
  const save_profs = document.getElementById('sw5e-c-saves').value.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
  return {
    id: currentSw5eCharId,
    name: document.getElementById('sw5e-c-name').value.trim(),
    species: document.getElementById('sw5e-c-species').value.trim(),
    class_name: document.getElementById('sw5e-c-class').value.trim(),
    level: parseInt(document.getElementById('sw5e-c-level').value || '1', 10),
    background: document.getElementById('sw5e-c-bg').value.trim(),
    alignment: document.getElementById('sw5e-c-align').value.trim(),
    size: document.getElementById('sw5e-c-size').value.trim(),
    speed: document.getElementById('sw5e-c-speed').value.trim(),
    deployment_role: document.getElementById('sw5e-c-role').value.trim(),
    starting_feat: document.getElementById('sw5e-c-feat').value.trim(),
    credits: document.getElementById('sw5e-c-credits').value.trim(),
    player_name: document.getElementById('sw5e-c-player').value.trim(),
    stats: {
      STR: parseInt(document.getElementById('sw5e-c-str').value || '10', 10),
      DEX: parseInt(document.getElementById('sw5e-c-dex').value || '10', 10),
      CON: parseInt(document.getElementById('sw5e-c-con').value || '10', 10),
      INT: parseInt(document.getElementById('sw5e-c-int').value || '10', 10),
      WIS: parseInt(document.getElementById('sw5e-c-wis').value || '10', 10),
      CHA: parseInt(document.getElementById('sw5e-c-cha').value || '10', 10)
    },
    ac: parseInt(document.getElementById('sw5e-c-ac').value || '10', 10),
    hp_current: parseInt(document.getElementById('sw5e-c-hpcur').value || '10', 10),
    hp_max: parseInt(document.getElementById('sw5e-c-hpmax').value || '10', 10),
    hit_dice: document.getElementById('sw5e-c-hd').value.trim(),
    force_points: parseInt(document.getElementById('sw5e-c-fp').value || '0', 10),
    tech_points: parseInt(document.getElementById('sw5e-c-tp').value || '0', 10),
    armor_notes: document.getElementById('sw5e-c-armor').value.trim(),
    weapons,
    skill_ranks,
    save_profs,
    languages: document.getElementById('sw5e-c-langs').value.trim(),
    features: document.getElementById('sw5e-c-features').value.trim(),
    equipment: document.getElementById('sw5e-c-equip').value.trim()
  };
}

function applySw5eCharToForm(c) {
  if (!c) return;
  currentSw5eCharId = c.id || '';
  document.getElementById('sw5e-c-name').value = c.name || '';
  document.getElementById('sw5e-c-species').value = c.species || 'Human';
  document.getElementById('sw5e-c-class').value = c.class_name || 'Operative';
  document.getElementById('sw5e-c-level').value = c.level ?? 1;
  document.getElementById('sw5e-c-bg').value = c.background || '';
  document.getElementById('sw5e-c-align').value = c.alignment || '';
  document.getElementById('sw5e-c-size').value = c.size || 'Medium';
  document.getElementById('sw5e-c-speed').value = c.speed || '30 ft.';
  document.getElementById('sw5e-c-role').value = c.deployment_role || '';
  document.getElementById('sw5e-c-feat').value = c.starting_feat || '';
  document.getElementById('sw5e-c-credits').value = c.credits || '1000';
  document.getElementById('sw5e-c-player').value = c.player_name || '';

  const st = c.stats || {};
  const md = c.mods || {};
  ['str','dex','con','int','wis','cha'].forEach(k => {
    const K = k.toUpperCase();
    document.getElementById(`sw5e-c-${k}`).value = st[K] ?? 10;
    const m = md[K] ?? Math.floor(((st[K] ?? 10) - 10) / 2);
    document.getElementById(`sw5e-c-${k}-m`).textContent = (m >= 0 ? '+' : '') + m;
  });
  document.getElementById('sw5e-c-ac').value = c.ac ?? 10;
  document.getElementById('sw5e-c-hpcur').value = c.hp_current ?? 10;
  document.getElementById('sw5e-c-hpmax').value = c.hp_max ?? 10;
  document.getElementById('sw5e-c-hd').value = c.hit_dice || '1d8';
  document.getElementById('sw5e-c-fp').value = c.force_points ?? 0;
  document.getElementById('sw5e-c-tp').value = c.tech_points ?? 0;
  document.getElementById('sw5e-c-armor').value = c.armor_notes || '';

  const wBox = document.getElementById('sw5e-c-weapons');
  wBox.innerHTML = '';
  (c.weapons || []).forEach(w => addSw5eCharWeapon(w));

  const sks = Object.entries(c.skill_ranks || {}).filter(([,r]) => r > 0).map(([n]) => n);
  document.getElementById('sw5e-c-skills').value = sks.join(', ');
  document.getElementById('sw5e-c-saves').value = (c.save_profs || []).join(', ');
  document.getElementById('sw5e-c-langs').value = c.languages || 'Galactic Basic';
  document.getElementById('sw5e-c-features').value = c.features || '';
  document.getElementById('sw5e-c-equip').value = c.equipment || '';
}

function getSw5eShipState() {
  const weapons = [];
  document.querySelectorAll('#sw5e-s-weapons .sw5e-sw-row').forEach(r => {
    weapons.push({
      name: r.querySelector('.sw-name').value.trim(),
      attack: r.querySelector('.sw-atk').value.trim(),
      damage: r.querySelector('.sw-dmg').value.trim(),
      range: r.querySelector('.sw-rng').value.trim(),
      arc: r.querySelector('.sw-arc').value.trim(),
      notes: ''
    });
  });
  const crew = [];
  document.querySelectorAll('#sw5e-s-crew .sw5e-cr-row').forEach(r => {
    crew.push({
      name: r.querySelector('.cr-name').value.trim(),
      role: r.querySelector('.cr-role').value.trim()
    });
  });
  const modifications = document.getElementById('sw5e-s-mods').value.split('\n').map(ln => ln.trim()).filter(Boolean).map(ln => {
    const parts = ln.split('|').map(p => p.trim());
    return { name: parts[0] || '', type: parts[1] || 'Suite', price: parts[2] || '', description: parts[3] || '' };
  });
  return {
    id: currentSw5eShipId,
    name: document.getElementById('sw5e-s-name').value.trim(),
    size: document.getElementById('sw5e-s-size').value,
    tier: parseInt(document.getElementById('sw5e-s-tier').value || '0', 10),
    model: document.getElementById('sw5e-s-model').value.trim(),
    manufacturer: document.getElementById('sw5e-s-mfg').value.trim(),
    role_spec: document.getElementById('sw5e-s-role').value.trim(),
    flying_speed: document.getElementById('sw5e-s-fly').value.trim(),
    turning_speed: document.getElementById('sw5e-s-turn').value.trim(),
    hyperdrive: document.getElementById('sw5e-s-hyper').value.trim(),
    stats: {
      STR: parseInt(document.getElementById('sw5e-s-str').value || '10', 10),
      DEX: parseInt(document.getElementById('sw5e-s-dex').value || '10', 10),
      CON: parseInt(document.getElementById('sw5e-s-con').value || '10', 10),
      INT: parseInt(document.getElementById('sw5e-s-int').value || '10', 10),
      WIS: parseInt(document.getElementById('sw5e-s-wis').value || '10', 10),
      CHA: parseInt(document.getElementById('sw5e-s-cha').value || '10', 10)
    },
    ac: parseInt(document.getElementById('sw5e-s-ac').value || '12', 10),
    dr: document.getElementById('sw5e-s-dr').value.trim(),
    hp_current: parseInt(document.getElementById('sw5e-s-hpcur').value || '24', 10),
    hp_max: parseInt(document.getElementById('sw5e-s-hpmax').value || '24', 10),
    sp_current: parseInt(document.getElementById('sw5e-s-spcur').value || '24', 10),
    sp_max: parseInt(document.getElementById('sw5e-s-spmax').value || '24', 10),
    hull_dice: document.getElementById('sw5e-s-hd').value.trim(),
    shield_dice: document.getElementById('sw5e-s-sd').value.trim(),
    weapons,
    crew,
    modifications
  };
}

function applySw5eShipToForm(s) {
  if (!s) return;
  currentSw5eShipId = s.id || '';
  document.getElementById('sw5e-s-name').value = s.name || '';
  document.getElementById('sw5e-s-size').value = s.size || 'Medium';
  document.getElementById('sw5e-s-tier').value = s.tier ?? 0;
  document.getElementById('sw5e-s-model').value = s.model || '';
  document.getElementById('sw5e-s-mfg').value = s.manufacturer || '';
  document.getElementById('sw5e-s-role').value = s.role_spec || '';
  document.getElementById('sw5e-s-fly').value = s.flying_speed || '300 ft.';
  document.getElementById('sw5e-s-turn').value = s.turning_speed || '200 ft.';
  document.getElementById('sw5e-s-hyper').value = s.hyperdrive || '';

  const st = s.stats || {};
  const md = s.mods || {};
  ['str','dex','con','int','wis','cha'].forEach(k => {
    const K = k.toUpperCase();
    document.getElementById(`sw5e-s-${k}`).value = st[K] ?? 10;
    const m = md[K] ?? Math.floor(((st[K] ?? 10) - 10) / 2);
    document.getElementById(`sw5e-s-${k}-m`).textContent = (m >= 0 ? '+' : '') + m;
  });
  document.getElementById('sw5e-s-ac').value = s.ac ?? 12;
  document.getElementById('sw5e-s-dr').value = s.dr ?? '4';
  document.getElementById('sw5e-s-hpcur').value = s.hp_current ?? 36;
  document.getElementById('sw5e-s-hpmax').value = s.hp_max ?? 36;
  document.getElementById('sw5e-s-spcur').value = s.sp_current ?? 36;
  document.getElementById('sw5e-s-spmax').value = s.sp_max ?? 36;
  document.getElementById('sw5e-s-hd').value = s.hull_dice || '3d8';
  document.getElementById('sw5e-s-sd').value = s.shield_dice || '3d8';
  document.getElementById('sw5e-s-caps').value = `${s.mod_cap ?? 30} / ${s.max_suites ?? 7}`;

  const wBox = document.getElementById('sw5e-s-weapons');
  wBox.innerHTML = '';
  (s.weapons || []).forEach(w => addSw5eShipWeapon(w));

  const cBox = document.getElementById('sw5e-s-crew');
  cBox.innerHTML = '';
  (s.crew || []).forEach(c => addSw5eCrewRow(c));

  document.getElementById('sw5e-s-mods').value = (s.modifications || []).map(m => `${m.name} | ${m.type} | ${m.price} | ${m.description}`).join('\n');
}

async function recalcSw5eChar() {
  const res = await api('/api/sw5e/calculate-char', 'POST', getSw5eCharState());
  if (res.ok && res.character) applySw5eCharToForm(res.character);
}

async function recalcSw5eShip() {
  const res = await api('/api/sw5e/calculate-ship', 'POST', getSw5eShipState());
  if (res.ok && res.ship) applySw5eShipToForm(res.ship);
}

async function saveSw5eChar() {
  const res = await api('/api/sw5e/save-char', 'POST', getSw5eCharState());
  if (res.ok && res.character) {
    applySw5eCharToForm(res.character);
    await refreshSw5eLists(res.character.id, currentSw5eShipId);
  }
}

async function saveSw5eShip() {
  const res = await api('/api/sw5e/save-ship', 'POST', getSw5eShipState());
  if (res.ok && res.ship) {
    applySw5eShipToForm(res.ship);
    await refreshSw5eLists(currentSw5eCharId, res.ship.id);
  }
}

async function deleteSw5eChar() {
  if (!currentSw5eCharId || !confirm('Delete this SW5e Character?')) return;
  await api('/api/sw5e/delete-char', 'POST', { id: currentSw5eCharId });
  await newSw5eChar();
  await refreshSw5eLists('', currentSw5eShipId);
}

async function deleteSw5eShip() {
  if (!currentSw5eShipId || !confirm('Delete this SW5e Starship?')) return;
  await api('/api/sw5e/delete-ship', 'POST', { id: currentSw5eShipId });
  await newSw5eShip();
  await refreshSw5eLists(currentSw5eCharId, '');
}

async function exportSw5ePdfs(exportChar, exportShip) {
  const statusEl = document.getElementById('sw5e-export-status');
  statusEl.innerHTML = '⏳ Exporting SW5e PDF(s)...';
  const payload = {};
  if (exportChar) payload.character = getSw5eCharState();
  if (exportShip) payload.ship = getSw5eShipState();
  const res = await api('/api/sw5e/export-pdf', 'POST', payload);
  if (!res.ok) {
    statusEl.innerHTML = `<span style="color:#fca5a5;">❌ Export failed: ${res.error || 'Unknown error'}</span>`;
    return;
  }
  if (res.character) applySw5eCharToForm(res.character);
  if (res.ship) applySw5eShipToForm(res.ship);
  await refreshSw5eLists(res.character?.id || currentSw5eCharId, res.ship?.id || currentSw5eShipId);
  const links = [];
  if (res.files?.character) {
    links.push(`<a href="${res.files.character.url}" target="_blank" class="btn secondary" style="display:inline-flex; padding:6px 12px; text-decoration:none; border-color:#38bdf8; color:#bae6fd;">🧑 Open / Print Character PDF (${res.files.character.filename})</a>`);
  }
  if (res.files?.ship) {
    links.push(`<a href="${res.files.ship.url}" target="_blank" class="btn secondary" style="display:inline-flex; padding:6px 12px; text-decoration:none; border-color:#f59e0b; color:#fde68a;">🛸 Open / Print Starship PDF (${res.files.ship.filename})</a>`);
  }
  statusEl.innerHTML = `<div style="color:#6ee7b7; margin-bottom:6px;">✅ Exported SW5e PDFs to <code>C:\\AI_Workspace\\outputs\\sw5e\\</code>!</div><div style="display:flex; gap:8px; flex-wrap:wrap;">${links.join('')}</div>`;
}

function onChatModeToggle(mode) {
  const dm = document.getElementById('chat-dm-mode');
  const dcc = document.getElementById('chat-dcc-mode');
  const sw = document.getElementById('chat-sw5e-mode');
  const d5 = document.getElementById('chat-dnd5e-mode');
  if (mode === 'dm' && dm.checked) { dcc.checked = false; sw.checked = false; d5.checked = false; }
  if (mode === 'dcc' && dcc.checked) { dm.checked = false; sw.checked = false; d5.checked = false; }
  if (mode === 'sw5e' && sw.checked) { dm.checked = false; dcc.checked = false; d5.checked = false; }
  if (mode === 'dnd5e' && d5.checked) { dm.checked = false; dcc.checked = false; sw.checked = false; }
}

// ============================================================================
// D&D 5E CHARACTER SHEET BUILDER
// ============================================================================
let currentDnd5eId = '';

function prefillDnd5ePrompt() {
  onChatModeToggle('dnd5e');
  document.getElementById('chat-dnd5e-mode').checked = true;
  onChatModeToggle('dnd5e');
  const inp = document.getElementById('chat-input');
  inp.value = '/dnd5e Create a Level 1 High Elf Wizard (Sage background) named Lyra Nightbreeze with Fire Bolt, Mage Hand, Magic Missile, and Shield.';
  inp.focus();
}

async function initDnd5eTab() {
  await refreshDnd5eList();
  await refreshDnd5ePortraitGallery();
}

async function refreshDnd5eList(selectId='') {
  try {
    const data = await api('/api/dnd5e/characters');
    const sel = document.getElementById('dnd5e-saved-select');
    if (!sel) return;
    sel.innerHTML = '<option value="">-- New 5e Character --</option>';
    (data.characters || []).forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.name || c.id} (Lv.${c.level || 1} ${c.race || ''} ${c.class_name || ''})`;
      sel.appendChild(opt);
    });
    if (selectId) { sel.value = selectId; currentDnd5eId = selectId; }
    else if (!currentDnd5eId && data.default_character) applyDnd5eCharToForm(data.default_character);
  } catch (e) {}
}

async function loadSelectedDnd5eChar() {
  const id = document.getElementById('dnd5e-saved-select').value;
  if (!id) { newDnd5eChar(); return; }
  const res = await api('/api/dnd5e/character?id=' + encodeURIComponent(id));
  if (res.ok && res.character) applyDnd5eCharToForm(res.character);
}

async function newDnd5eChar() {
  currentDnd5eId = '';
  document.getElementById('dnd5e-saved-select').value = '';
  const data = await api('/api/dnd5e/characters');
  if (data.default_character) applyDnd5eCharToForm(data.default_character);
}

function addDnd5eWeapon(w={}) {
  const box = document.getElementById('dnd5e-weapons');
  const row = document.createElement('div');
  row.className = 'd5-wp-row';
  row.style.cssText = 'display:grid; grid-template-columns:2fr 65px 2fr 28px; gap:4px; align-items:center;';
  row.innerHTML = `
    <input class="d5w-name" placeholder="Longsword" value="${(w.name||'').replace(/"/g,'&quot;')}">
    <input class="d5w-atk" placeholder="+4" value="${(w.atk||'').replace(/"/g,'&quot;')}">
    <input class="d5w-dmg" placeholder="1d8+2 Slashing" value="${(w.damage||'').replace(/"/g,'&quot;')}">
    <button type="button" class="btn secondary" style="padding:4px 6px; color:#fca5a5;" onclick="this.parentElement.remove()">✖</button>
  `;
  box.appendChild(row);
}

function getDnd5eCharState() {
  const weapons = [];
  document.querySelectorAll('#dnd5e-weapons .d5-wp-row').forEach(r => {
    weapons.push({
      name: r.querySelector('.d5w-name').value.trim(),
      atk: r.querySelector('.d5w-atk').value.trim(),
      damage: r.querySelector('.d5w-dmg').value.trim()
    });
  });
  const skill_ranks = {};
  document.getElementById('dnd5e-skills').value.split(',').map(s => s.trim()).filter(Boolean).forEach(s => { skill_ranks[s] = 1; });
  const save_profs = document.getElementById('dnd5e-saves').value.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
  return {
    id: currentDnd5eId,
    name: document.getElementById('dnd5e-name').value.trim(),
    race: document.getElementById('dnd5e-race').value.trim(),
    class_name: document.getElementById('dnd5e-class').value.trim(),
    level: parseInt(document.getElementById('dnd5e-level').value || '1', 10),
    background: document.getElementById('dnd5e-bg').value.trim(),
    alignment: document.getElementById('dnd5e-align').value.trim(),
    player_name: document.getElementById('dnd5e-player').value.trim(),
    xp: document.getElementById('dnd5e-xp').value.trim(),
    speed: document.getElementById('dnd5e-speed').value.trim(),
    ac: parseInt(document.getElementById('dnd5e-ac').value || '10', 10),
    hp_current: parseInt(document.getElementById('dnd5e-hpcur').value || '10', 10),
    hp_max: parseInt(document.getElementById('dnd5e-hpmax').value || '10', 10),
    hit_dice: document.getElementById('dnd5e-hd').value.trim(),
    portrait_path: document.getElementById('dnd5e-portrait-path').value.trim(),
    stats: {
      STR: parseInt(document.getElementById('dnd5e-str').value || '10', 10),
      DEX: parseInt(document.getElementById('dnd5e-dex').value || '10', 10),
      CON: parseInt(document.getElementById('dnd5e-con').value || '10', 10),
      INT: parseInt(document.getElementById('dnd5e-int').value || '10', 10),
      WIS: parseInt(document.getElementById('dnd5e-wis').value || '10', 10),
      CHA: parseInt(document.getElementById('dnd5e-cha').value || '10', 10)
    },
    skill_ranks,
    save_profs,
    weapons,
    currency: { gp: document.getElementById('dnd5e-gp').value.trim() },
    proficiencies_lang: document.getElementById('dnd5e-profs').value.trim(),
    equipment: document.getElementById('dnd5e-equip').value.trim(),
    features_traits: document.getElementById('dnd5e-features').value.trim(),
    personality_traits: document.getElementById('dnd5e-traits').value.trim(),
    ideals: document.getElementById('dnd5e-ideals').value.trim(),
    spellcasting: {
      class_name: document.getElementById('dnd5e-sp-class').value.trim(),
      ability: document.getElementById('dnd5e-sp-ab').value,
      slots_1: document.getElementById('dnd5e-sp-s1').value.trim(),
      slots_2: document.getElementById('dnd5e-sp-s2').value.trim(),
      cantrips: document.getElementById('dnd5e-sp-cantrips').value.split(',').map(s => s.trim()).filter(Boolean),
      level_1: document.getElementById('dnd5e-sp-lvl1').value.split(',').map(s => s.trim()).filter(Boolean),
      level_2: document.getElementById('dnd5e-sp-lvl2').value.split(',').map(s => s.trim()).filter(Boolean)
    }
  };
}

function applyDnd5eCharToForm(c) {
  if (!c) return;
  currentDnd5eId = c.id || '';
  document.getElementById('dnd5e-name').value = c.name || '';
  document.getElementById('dnd5e-race').value = c.race || 'Human';
  document.getElementById('dnd5e-class').value = c.class_name || 'Fighter';
  document.getElementById('dnd5e-level').value = c.level ?? 1;
  document.getElementById('dnd5e-bg').value = c.background || '';
  document.getElementById('dnd5e-align').value = c.alignment || '';
  document.getElementById('dnd5e-player').value = c.player_name || '';
  document.getElementById('dnd5e-xp').value = c.xp ?? '0';
  document.getElementById('dnd5e-speed').value = c.speed || '30 ft.';
  document.getElementById('dnd5e-ac').value = c.ac ?? 10;
  document.getElementById('dnd5e-hpcur').value = c.hp_current ?? 10;
  document.getElementById('dnd5e-hpmax').value = c.hp_max ?? 10;
  document.getElementById('dnd5e-hd').value = c.hit_dice || '1d10';
  setDnd5ePortraitPath(c.portrait_path || '');

  const st = c.stats || {};
  const md = c.mods || {};
  ['str','dex','con','int','wis','cha'].forEach(k => {
    const K = k.toUpperCase();
    document.getElementById(`dnd5e-${k}`).value = st[K] ?? 10;
    const m = md[K] ?? Math.floor(((st[K] ?? 10) - 10) / 2);
    document.getElementById(`dnd5e-${k}-m`).textContent = (m >= 0 ? '+' : '') + m;
  });

  const wBox = document.getElementById('dnd5e-weapons');
  wBox.innerHTML = '';
  (c.weapons || []).forEach(w => addDnd5eWeapon(w));

  const sks = Object.entries(c.skill_ranks || {}).filter(([,r]) => r > 0).map(([n]) => n);
  document.getElementById('dnd5e-skills').value = sks.join(', ');
  document.getElementById('dnd5e-saves').value = (c.save_profs || []).join(', ');
  document.getElementById('dnd5e-gp').value = (c.currency && c.currency.gp) || '10';
  document.getElementById('dnd5e-profs').value = c.proficiencies_lang || '';
  document.getElementById('dnd5e-equip').value = c.equipment || '';
  document.getElementById('dnd5e-features').value = c.features_traits || '';
  document.getElementById('dnd5e-traits').value = c.personality_traits || '';
  document.getElementById('dnd5e-ideals').value = c.ideals || '';

  const sp = c.spellcasting || {};
  document.getElementById('dnd5e-sp-class').value = sp.class_name || '';
  document.getElementById('dnd5e-sp-ab').value = sp.ability || '';
  document.getElementById('dnd5e-sp-s1').value = sp.slots_1 || '';
  document.getElementById('dnd5e-sp-s2').value = sp.slots_2 || '';
  document.getElementById('dnd5e-sp-cantrips').value = (sp.cantrips || []).join(', ');
  document.getElementById('dnd5e-sp-lvl1').value = (sp.level_1 || []).join(', ');
  document.getElementById('dnd5e-sp-lvl2').value = (sp.level_2 || []).join(', ');
}

function setDnd5ePortraitPath(diskPath, previewUrl='') {
  document.getElementById('dnd5e-portrait-path').value = diskPath || '';
  const img = document.getElementById('dnd5e-portrait-preview');
  const empty = document.getElementById('dnd5e-portrait-empty');
  if (diskPath) {
    const fname = diskPath.split(/[\\/]/).pop();
    img.src = previewUrl || ('/outputs/images/' + encodeURIComponent(fname));
    img.style.display = 'block';
    empty.style.display = 'none';
  } else {
    img.src = '';
    img.style.display = 'none';
    empty.style.display = 'block';
  }
}

async function refreshDnd5ePortraitGallery() {
  try {
    const g = await api('/api/gallery');
    const box = document.getElementById('dnd5e-portrait-gallery');
    if (!box) return;
    box.innerHTML = '';
    (g.images || []).slice(0, 14).forEach(im => {
      const thumb = document.createElement('img');
      thumb.src = im.url;
      thumb.title = im.filename;
      thumb.style.cssText = 'width:48px; height:64px; object-fit:cover; border-radius:4px; border:1px solid var(--border); cursor:pointer;';
      thumb.onclick = () => setDnd5ePortraitPath(im.disk_path, im.url);
      box.appendChild(thumb);
    });
  } catch (e) {}
}

async function recalcDnd5eChar() {
  const res = await api('/api/dnd5e/calculate', 'POST', getDnd5eCharState());
  if (res.ok && res.character) applyDnd5eCharToForm(res.character);
}

async function saveDnd5eChar() {
  const res = await api('/api/dnd5e/save', 'POST', getDnd5eCharState());
  if (res.ok && res.character) {
    applyDnd5eCharToForm(res.character);
    await refreshDnd5eList(res.character.id);
  }
}

async function deleteDnd5eChar() {
  if (!currentDnd5eId || !confirm('Delete this 5e Character?')) return;
  await api('/api/dnd5e/delete', 'POST', { id: currentDnd5eId });
  await newDnd5eChar();
  await refreshDnd5eList();
}

async function exportDnd5ePdf() {
  const stEl = document.getElementById('dnd5e-export-status');
  stEl.innerHTML = '⏳ Exporting printable 3-page D&D 5e PDF...';
  const res = await api('/api/dnd5e/export-pdf', 'POST', { character: getDnd5eCharState() });
  if (!res.ok) {
    stEl.innerHTML = `<span style="color:#fca5a5;">❌ Export failed: ${res.error || 'Unknown error'}</span>`;
    return;
  }
  applyDnd5eCharToForm(res.character);
  await refreshDnd5eList(res.character.id);
  stEl.innerHTML = `<div style="color:#6ee7b7; margin-bottom:6px;">✅ Exported to <code>C:\\AI_Workspace\\outputs\\dnd5e\\</code>!</div>` +
    `<a href="${res.file.url}" target="_blank" class="btn secondary" style="display:inline-flex; padding:6px 12px; text-decoration:none; border-color:#ef4444; color:#fecaca;">📄 Open / Print 5e Character Sheet (${res.file.filename})</a>`;
}

async function refreshRulesIndexStatus() {
  try {
    const st = await api('/api/rules/status');
    const el = document.getElementById('rules-rag-status');
    if (!el) return;
    const p = st.indexed_pages || {};
    if (st.indexing) {
      el.innerHTML = `<span style="color:#fde68a;">⏳ Indexing ${st.progress || '...'}</span>`;
      setTimeout(refreshRulesIndexStatus, 2500);
    } else {
      el.innerHTML = `📚 Indexed: <b>5e</b> ${p.dnd5e || 0}p • <b>SW5e</b> ${p.sw5e || 0}p • <b>DCC</b> ${p.dcc || 0}p`;
    }
  } catch (e) {}
}

async function reindexRulesNow() {
  await api('/api/rules/reindex', 'POST', { force: false });
  refreshRulesIndexStatus();
}

// ============================================================================
// CAMPAIGN ORGANIZER (DCC CRAWLOPS)
// ============================================================================
let campTree = { hubs: [], nodes: [], beats: [], entities: [], source_files: [] };
let activeCampSystem = 'dcc';
let activeHubId = '';
let activeNodeId = '';
let activeBeatId = '';

const CAMP_SYSTEM_META = {
  dcc: {
    hubLabel: 'F',
    nodeTypes: ['Saferoom','Desperado Venue','Club Vanquisher','Guild Hall','Shop','Tavern','Train Station','Encounter Zone'],
    lootTiers: ['Bronze','Silver','Gold','Platinum','Legendary','Celestial'],
    defaultMix: '1 Bopca Merchant + 1 Rival GMC'
  },
  dnd5e: {
    hubLabel: 'Tier ',
    nodeTypes: ['Tavern','Dungeon Room','Town / Ward','Temple','Guildhall','Wilderness','Boss Lair'],
    lootTiers: ['Tier 1 (CR 0-4)','Tier 2 (CR 5-10)','Tier 3 (CR 11-16)','Tier 4 (CR 17+)'],
    defaultMix: '1 Merchant + 2 Guard / Bandit Enemies'
  },
  sw5e: {
    hubLabel: 'Tier ',
    nodeTypes: ['Cantina','Spaceport','Imperial Base','Asteroid Outpost','Smuggler Den','Bridge / Hangar','Encounter Zone'],
    lootTiers: ['Standard','Premium','Prototype','Advanced','Artifact','Legendary'],
    defaultMix: '1 Underworld Broker + 2 Mercenaries'
  }
};

function applyCampSystemLabels() {
  const meta = CAMP_SYSTEM_META[activeCampSystem] || CAMP_SYSTEM_META.dcc;
  const ntSel = document.getElementById('camp-node-type');
  if (ntSel) ntSel.innerHTML = meta.nodeTypes.map(t => `<option>${t}</option>`).join('');
  const ltSel = document.getElementById('camp-loot-tier');
  if (ltSel) ltSel.innerHTML = meta.lootTiers.map(t => `<option>${t}</option>`).join('');
  const mixEl = document.getElementById('camp-pop-mix');
  if (mixEl) mixEl.value = meta.defaultMix;
}

async function switchCampaignSystem() {
  activeCampSystem = document.getElementById('camp-system')?.value || 'dcc';
  activeHubId = '';
  activeNodeId = '';
  activeBeatId = '';
  applyCampSystemLabels();
  await initCampaignTab();
}

async function initCampaignTab() {
  try {
    activeCampSystem = document.getElementById('camp-system')?.value || activeCampSystem || 'dcc';
    applyCampSystemLabels();
    const res = await api('/api/campaign/tree?system=' + encodeURIComponent(activeCampSystem));
    if (res.ok) {
      campTree = res;
      if (!activeHubId && campTree.hubs.length) activeHubId = campTree.hubs[0].id;
      if (!activeNodeId && campTree.nodes.length) {
        const n = campTree.nodes.find(x => x.hub_id === activeHubId) || campTree.nodes[0];
        if (n) activeNodeId = n.id;
      }
      renderCampaignWorkspace();
    }
  } catch (e) { console.error('initCampaignTab:', e); }
}

function toggleCampForm(which) {
  const el = document.getElementById(`camp-add-${which}-form`);
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function renderCampaignWorkspace() {
  const treeEl = document.getElementById('camp-tree-list');
  if (!treeEl) return;
  treeEl.innerHTML = '';

  if (!campTree.hubs.length) {
    treeEl.innerHTML = '<div style="font-size:12px; color:var(--muted);">No floors yet. Upload a Markdown file above or click <b>+ Floor</b>.</div>';
  }

  campTree.hubs.forEach(h => {
    const hBox = document.createElement('div');
    hBox.style.cssText = `padding:8px; border-radius:8px; border:1px solid ${h.id === activeHubId ? '#f59e0b' : 'var(--border)'}; background:#0b0f19;`;
    hBox.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; cursor:pointer;" onclick="activeHubId='${h.id}'; renderCampaignWorkspace();">
        <b style="font-size:12px; color:#fde68a;">F${h.floor_number}: ${h.name}</b>
        <span style="font-size:10px; color:var(--muted);">⏱️ ${h.collapse_timer_hours}h</span>
      </div>`;
    const nodes = campTree.nodes.filter(n => n.hub_id === h.id);
    nodes.forEach(n => {
      const nBtn = document.createElement('div');
      nBtn.style.cssText = `margin-top:5px; padding:5px 8px; border-radius:6px; font-size:11px; cursor:pointer; background:${n.id === activeNodeId ? '#312e81' : '#111827'}; border:1px solid ${n.id === activeNodeId ? '#8b5cf6' : 'transparent'};`;
      nBtn.textContent = `• ${n.name} [${n.minimap_marker}]`;
      nBtn.onclick = (ev) => { ev.stopPropagation(); activeHubId = h.id; activeNodeId = n.id; activeBeatId = ''; renderCampaignWorkspace(); };
      hBox.appendChild(nBtn);
    });
    treeEl.appendChild(hBox);
  });

  const node = campTree.nodes.find(n => n.id === activeNodeId);
  const hub = campTree.hubs.find(h => h.id === (node ? node.hub_id : activeHubId));
  const titleEl = document.getElementById('camp-node-title');
  const metaEl = document.getElementById('camp-node-meta');
  const bodyEl = document.getElementById('camp-node-body');
  const actEl = document.getElementById('camp-node-actions');

  if (node) {
    const f = hub ? hub.floor_number : 1;
    titleEl.textContent = `${node.name} (${node.node_type})`;
    metaEl.innerHTML = `Floor <b>F=${f}</b> • Marker: <b>${node.minimap_marker}</b> • Stat DC: <code>${10+f}</code> • Unopposed DC: <code>${10+2*f}</code>`;
    bodyEl.innerHTML = `<div>${(node.description_md || 'No description yet.').replace(/\n/g, '<br>')}</div>` +
      (node.environmental_hazards ? `<div style="margin-top:6px; color:#fca5a5;"><b>Hazards:</b> ${node.environmental_hazards}</div>` : '');
    actEl.style.display = 'flex';
  } else {
    titleEl.textContent = hub ? `${hub.name} (Floor ${hub.floor_number})` : 'Select or Create a Floor / Node';
    metaEl.textContent = hub ? `Collapse Timer: ${hub.collapse_timer_hours}h | Faction: ${hub.controlling_faction || 'None'}` : '';
    bodyEl.textContent = hub?.summary_md || '';
    actEl.style.display = 'none';
  }

  // Beats & Populate Beat Dropdown
  const beatsEl = document.getElementById('camp-beats-list');
  beatsEl.innerHTML = '';
  const beats = campTree.beats.filter(b => !activeNodeId || b.node_id === activeNodeId);
  const popBeatSel = document.getElementById('camp-pop-beat');
  if (popBeatSel) {
    const prevVal = popBeatSel.value;
    popBeatSel.innerHTML = '<option value="">📍 Persistent in Node (Shopkeeper / Resident)</option>' +
      beats.map(b => `<option value="${b.id}">🎬 Beat: ${b.title}</option>`).join('');
    if (beats.some(b => b.id === (activeBeatId || prevVal))) popBeatSel.value = activeBeatId || prevVal;
  }
  if (!beats.length) beatsEl.innerHTML = '<div style="font-size:12px; color:var(--muted);">No beats for this node yet.</div>';
  beats.forEach(b => {
    const isSel = b.id === activeBeatId;
    const div = document.createElement('div');
    div.style.cssText = `padding:10px; background:#0b0f19; border:1px solid ${isSel ? '#f59e0b' : 'var(--border)'}; border-radius:8px; cursor:pointer;`;
    div.onclick = (ev) => { if (ev.target.tagName !== 'SELECT') { activeBeatId = isSel ? '' : b.id; renderCampaignWorkspace(); } };
    div.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
        <b style="font-size:12px; color:${isSel ? '#fde68a' : '#e5e7eb'};">${isSel ? '▶ ' : ''}[${b.beat_type}] ${b.title} <span style="color:#fde68a;">(${b.loot_reward_tier})</span></b>
        <select style="width:auto; padding:2px 6px; font-size:11px;" onchange="updateCampBeatStatus('${b.id}', this.value)">
          ${['Unplayed','Active','Completed','Skipped'].map(s => `<option ${b.status===s?'selected':''}>${s}</option>`).join('')}
        </select>
      </div>
      ${b.ai_announcement_md ? `<div style="margin-top:6px; padding:6px 8px; background:#1e1b4b; border-left:3px solid #f59e0b; font-size:11px; color:#fde68a;">${b.ai_announcement_md}</div>` : ''}
      ${b.gm_notes_md ? `<div style="margin-top:5px; font-size:11px; color:var(--muted);">${b.gm_notes_md}</div>` : ''}
    `;
    beatsEl.appendChild(div);
  });

  // Entities
  const filterMode = document.getElementById('camp-ent-filter')?.value || 'beat';
  const ents = campTree.entities.filter(e => {
    if (filterMode === 'all' || !activeNodeId) return true;
    if (e.current_node_id !== activeNodeId) return false;
    if (filterMode === 'beat' && activeBeatId) return e.beat_id === activeBeatId;
    return true;
  });
  document.getElementById('camp-ent-count').textContent = ents.length;
  const entEl = document.getElementById('camp-entities-list');
  entEl.innerHTML = '';

  ents.forEach(e => {
    const sb = e.stat_block || {};
    const st = sb.stats || {};
    const md = sb.mods || {};
    let statsHtml = '';
    if (sb.system === 'dnd5e' || sb.system === 'sw5e') {
      const hpCur = sb.hp_current ?? 10;
      const hpMax = sb.hp_max ?? 10;
      statsHtml = `
        <div style="font-size:11px; color:var(--muted); margin-top:2px;">
          AC: <b style="color:#fff;">${sb.ac ?? 12}</b> • HP: <b style="color:#6ee7b7;">${hpCur}/${hpMax}</b> • ${sb.cr || ''}
        </div>
        <div style="display:flex; gap:4px; margin:5px 0;">
          <button type="button" class="btn secondary" style="padding:2px 7px; font-size:10px; color:#fca5a5;" onclick="updateEntityLive('${e.id}', {hp_delta: -5})">-5</button>
          <button type="button" class="btn secondary" style="padding:2px 7px; font-size:10px; color:#fca5a5;" onclick="updateEntityLive('${e.id}', {hp_delta: -1})">-1</button>
          <button type="button" class="btn secondary" style="padding:2px 7px; font-size:10px; color:#6ee7b7;" onclick="updateEntityLive('${e.id}', {hp_delta: 1})">+1</button>
          <button type="button" class="btn secondary" style="padding:2px 7px; font-size:10px; color:#6ee7b7;" onclick="updateEntityLive('${e.id}', {hp_delta: 5})">+5</button>
        </div>
        <div style="font-size:10px; color:var(--muted);">
          STR ${st.STR||10}(${md.STR>=0?'+':''}${md.STR||0}) DEX ${st.DEX||10}(${md.DEX>=0?'+':''}${md.DEX||0}) CON ${st.CON||10}(${md.CON>=0?'+':''}${md.CON||0}) INT ${st.INT||10}(${md.INT>=0?'+':''}${md.INT||0}) WIS ${st.WIS||10}(${md.WIS>=0?'+':''}${md.WIS||0}) CHA ${st.CHA||10}(${md.CHA>=0?'+':''}${md.CHA||0})
        </div>`;
    } else {
      const slots = sb.hb_slots || 10;
      const dmg = sb.hb_damaged_slots || 0;
      let hbHtml = '';
      for (let i = 0; i < slots; i++) {
        const isDmg = i >= (slots - dmg);
        const newDmg = slots - i;
        const toggleVal = isDmg ? (newDmg - 1) : newDmg;
        hbHtml += `<div class="hb-slot ${isDmg ? 'damaged' : ''}" title="Click to set damaged slots: ${toggleVal}" onclick="setEntityHb('${e.id}', ${toggleVal})"></div>`;
      }
      statsHtml = `
        <div style="font-size:11px; color:var(--muted); margin-top:2px;">
          Evade DC: <b style="color:#fff;">${sb.evade_dc ?? 13}</b> • DR: <b style="color:#fff;">${sb.dr ?? 1}</b> • HB: <b>${slots - dmg}/${slots}</b> (${sb.hb_slot_value ?? 2}/slot)
        </div>
        <div class="hb-bar">${hbHtml}</div>
        <div style="font-size:10px; color:var(--muted);">
          STR ${st.STR||3}(+${md.STR||2}) INT ${st.INT||3}(+${md.INT||2}) CON ${st.CON||3}(+${md.CON||2}) DEX ${st.DEX||3}(+${md.DEX||2}) CHA ${st.CHA||3}(+${md.CHA||2})
        </div>`;
    }
    const card = document.createElement('div');
    card.style.cssText = 'padding:10px; background:#0b0f19; border:1px solid var(--border); border-radius:8px; font-size:12px;';
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
        <b style="color:#c4b5fd;">${e.name}</b>
        <span style="font-size:10px; color:#6ee7b7;">${e.entity_category} • Lv.${e.level}</span>
      </div>
      ${statsHtml}
      <div class="row" style="gap:4px; margin-top:6px;">
        <select style="font-size:11px; padding:3px;" onchange="updateEntityLive('${e.id}', {current_node_id: this.value})">
          ${campTree.nodes.map(n => `<option value="${n.id}" ${n.id===e.current_node_id?'selected':''}>📍 ${n.name}</option>`).join('')}
        </select>
        <select style="font-size:11px; padding:3px; max-width:115px;" onchange="updateEntityLive('${e.id}', {beat_id: this.value})" title="Bind to Beat or keep Persistent in Node">
          <option value="">📍 Persistent</option>
          ${campTree.beats.filter(b => b.node_id === e.current_node_id).map(b => `<option value="${b.id}" ${b.id===e.beat_id?'selected':''}>🎬 ${b.title}</option>`).join('')}
        </select>
        <select style="font-size:11px; padding:3px; max-width:85px;" onchange="updateEntityLive('${e.id}', {status: this.value})">
          ${['Alive','Hostile','Relocated','Dying','Dead'].map(s => `<option ${e.status===s?'selected':''}>${s}</option>`).join('')}
        </select>
      </div>
    `;
    entEl.appendChild(card);
  });
}

async function saveCampHub() {
  const res = await api('/api/campaign/hub', 'POST', {
    campaign_system: activeCampSystem,
    name: document.getElementById('camp-hub-name').value.trim(),
    floor_number: parseInt(document.getElementById('camp-hub-floor').value || '1', 10),
    collapse_timer_hours: parseInt(document.getElementById('camp-hub-timer').value || '240', 10),
    controlling_faction: document.getElementById('camp-hub-faction').value.trim()
  });
  if (res.ok) {
    campTree = res.tree;
    activeHubId = res.hub.id;
    toggleCampForm('hub');
    renderCampaignWorkspace();
  }
}

async function saveCampNode() {
  if (!activeHubId) return alert('Create or select a Hub / Floor first.');
  const res = await api('/api/campaign/node', 'POST', {
    campaign_system: activeCampSystem,
    hub_id: activeHubId,
    name: document.getElementById('camp-node-name').value.trim(),
    node_type: document.getElementById('camp-node-type').value,
    minimap_marker: document.getElementById('camp-node-marker').value,
    description_md: document.getElementById('camp-node-desc').value.trim(),
    projector_map_prompt: document.getElementById('camp-node-map').value.trim()
  });
  if (res.ok) {
    campTree = res.tree;
    activeNodeId = res.node.id;
    toggleCampForm('node');
    renderCampaignWorkspace();
  }
}

async function saveCampBeat() {
  if (!activeNodeId) return alert('Select a Micro Node first.');
  const res = await api('/api/campaign/beat', 'POST', {
    campaign_system: activeCampSystem,
    node_id: activeNodeId,
    title: document.getElementById('camp-beat-title').value.trim(),
    beat_type: document.getElementById('camp-beat-type').value,
    loot_reward_tier: document.getElementById('camp-beat-loot').value,
    ai_announcement_md: document.getElementById('camp-beat-ai').value.trim(),
    gm_notes_md: document.getElementById('camp-beat-gm').value.trim()
  });
  if (res.ok) {
    campTree = res.tree;
    toggleCampForm('beat');
    renderCampaignWorkspace();
  }
}

async function updateCampBeatStatus(beatId, status) {
  const b = campTree.beats.find(x => x.id === beatId);
  if (!b) return;
  const res = await api('/api/campaign/beat', 'POST', { ...b, campaign_system: activeCampSystem, status });
  if (res.ok) { campTree = res.tree; renderCampaignWorkspace(); }
}

async function setEntityHb(entId, damagedSlots) {
  await updateEntityLive(entId, { hb_damaged_slots: damagedSlots });
}

async function updateEntityLive(entId, payload) {
  const res = await api('/api/campaign/entity/live', 'POST', { id: entId, campaign_system: activeCampSystem, ...payload });
  if (res.ok) { campTree = res.tree; renderCampaignWorkspace(); }
}

async function populateActiveNodeNow() {
  if (!activeNodeId) return alert('Select a Micro Node first.');
  const stEl = document.getElementById('camp-status');
  stEl.textContent = `⏳ Generating ${activeCampSystem.toUpperCase()} entities for node...`;
  const res = await api('/api/campaign/populate', 'POST', {
    campaign_system: activeCampSystem,
    node_id: activeNodeId,
    beat_id: document.getElementById('camp-pop-beat')?.value || '',
    count: parseInt(document.getElementById('camp-pop-count').value || '2', 10),
    category_mix: document.getElementById('camp-pop-mix').value.trim(),
    hint: document.getElementById('camp-pop-hint').value.trim()
  });
  if (res.ok) {
    campTree = res.tree;
    renderCampaignWorkspace();
    stEl.textContent = `✅ Populated ${(res.created || []).length} persistent entities and synced to campaign_vault/npcs/.`;
  } else {
    stEl.textContent = `❌ ${res.error || 'Failed to populate node.'}`;
  }
}

async function uploadCampaignMarkdown() {
  const inp = document.getElementById('camp-md-file');
  if (!inp.files || !inp.files.length) return;
  const file = inp.files[0];
  const content = await file.text();
  const stEl = document.getElementById('camp-status');
  stEl.textContent = `⏳ Ingesting ${file.name} (${activeCampSystem.toUpperCase()})...`;
  const res = await api('/api/campaign/ingest', 'POST', { filename: file.name, content, campaign_system: activeCampSystem });
  if (res.ok) {
    campTree = res.tree;
    if (campTree.hubs.length && !activeHubId) activeHubId = campTree.hubs[0].id;
    if (campTree.nodes.length && !activeNodeId) activeNodeId = campTree.nodes[0].id;
    renderCampaignWorkspace();
    stEl.textContent = `✅ Ingested ${file.name}: ${res.counts.hubs} hubs, ${res.counts.nodes} nodes, ${res.counts.beats} beats, ${res.counts.entities} entities.`;
  }
}

async function scanVaultSourceDocs() {
  const stEl = document.getElementById('camp-status');
  stEl.textContent = `⏳ Scanning campaign_vault/source_docs (${activeCampSystem.toUpperCase()})...`;
  const res = await api('/api/campaign/scan-vault', 'POST', { campaign_system: activeCampSystem });
  if (res.ok) {
    campTree = res.tree;
    renderCampaignWorkspace();
    stEl.textContent = `✅ Scanned ${res.processed} source file(s) from campaign_vault/source_docs/.`;
  }
}

async function rollCampLootBox() {
  const node = campTree.nodes.find(n => n.id === activeNodeId);
  const hub = campTree.hubs.find(h => h.id === (node ? node.hub_id : activeHubId));
  const res = await api('/api/campaign/loot', 'POST', {
    campaign_system: activeCampSystem,
    floor_number: hub ? hub.floor_number : 1,
    tier: document.getElementById('camp-loot-tier').value,
    reason: document.getElementById('camp-loot-reason').value.trim()
  });
  const out = document.getElementById('camp-loot-output');
  out.style.display = 'block';
  out.textContent = res.announcement || '';
}

async function exportSessionRunbookNow() {
  const title = prompt('Session Runbook Title:', 'Session 01 Runbook');
  if (!title) return;
  const res = await api('/api/campaign/runbook', 'POST', { title, node_ids: activeNodeId ? [activeNodeId] : [] });
  if (res.ok) {
    document.getElementById('camp-status').textContent = `✅ Exported Runbook to ${res.path}`;
  }
}

function copyProjectorPrompt() {
  const n = campTree.nodes.find(x => x.id === activeNodeId);
  const p = n?.projector_map_prompt || `Top-down VTT battlemap, ${n?.name || 'dungeon room'}, ${n?.description_md || ''}, 8k`;
  navigator.clipboard.writeText(p);
  document.getElementById('camp-status').textContent = '📋 Copied Projector Map Prompt to clipboard!';
}

function sendMapPromptToStudio() {
  const n = campTree.nodes.find(x => x.id === activeNodeId);
  document.getElementById('gen-prompt').value = n?.projector_map_prompt || `Top-down VTT battlemap, ${n?.name || 'dungeon room'}, ${n?.description_md || ''}, 8k`;
  switchTab('studio', document.querySelector('nav button'));
}

async function testGeminiConnection() {
  const st = document.getElementById('gemini-test-status');
  st.style.color = 'var(--amber)';
  st.textContent = '⏳ Saving key & testing Gemini API with BLOCK_NONE...';
  await api('/api/config', 'POST', {
    llm_provider_mode: document.getElementById('cfg-llm-mode').value,
    gemini_model: document.getElementById('cfg-gemini-model').value,
    gemini_api_key: document.getElementById('cfg-gemini-key').value.trim()
  });
  const res = await api('/api/test-gemini', 'POST', {});
  if (res.ok) {
    st.style.color = 'var(--green)';
    st.textContent = '✅ ' + res.reply;
    refreshStatus();
  } else {
    st.style.color = 'var(--red)';
    st.textContent = '❌ ' + (res.error || 'Failed');
  }
}

async function downloadModel() {
  const url = document.getElementById('dl-url').value.trim();
  const filename = document.getElementById('dl-filename').value.trim();
  const mtype = document.getElementById('dl-type').value;
  if (!url || !filename) return alert('Provide both Filename and Direct Download URL.');
  const res = await api('/api/models/download', 'POST', { url, filename, type: mtype });
  alert(res.message || res.error);
}

window.addEventListener('DOMContentLoaded', initDashboard);
</script>
</body>
</html>
"""

# ============================================================================
# HTTP REQUEST HANDLER
# ============================================================================
class AIHubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, obj, code=200):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            raw = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if path == "/api/setup/status":
            cfg = load_config()
            self._send_json({
                "ok": True,
                "data_dir": str(app_paths.DATA_DIR),
                "config": cfg,
                "ollama": llm_router.check_ollama_status(cfg.get("ollama_url", "http://127.0.0.1:11434")),
                "comfy": check_comfy_status(),
                "rules_status": rules_rag.get_index_status(),
            })
            return

        if path == "/api/campaign/tree":
            qs = urllib.parse.parse_qs(parsed.query)
            sys_key = (qs.get("system") or [""])[0]
            self._send_json({"ok": True, **campaign_engine.get_campaign_tree(sys_key)})
            return

        if path == "/api/rules/status":
            self._send_json(rules_rag.get_index_status())
            return

        if path == "/api/rules/search":
            qs = urllib.parse.parse_qs(parsed.query)
            sys_key = (qs.get("system") or ["dnd5e"])[0]
            q = (qs.get("q") or [""])[0]
            self._send_json({"ok": True, "hits": rules_rag.search_rules(sys_key, q, top_k=8)})
            return

        if path.startswith("/outputs/dnd5e/"):
            fname = os.path.basename(path)
            fpath = Path(dnd5e_engine.DND5E_OUTPUTS_DIR) / fname
            if fpath.exists():
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)
            return

        if path == "/api/dnd5e/characters":
            self._send_json({
                "characters": dnd5e_engine.list_characters(),
                "default_character": dnd5e_engine.default_character(),
            })
            return

        if path == "/api/dnd5e/character":
            qs = urllib.parse.parse_qs(parsed.query)
            cid = (qs.get("id") or [""])[0]
            ch = dnd5e_engine.load_character(cid) if cid else None
            self._send_json({"ok": bool(ch), "character": dnd5e_engine.calculate_character(ch)} if ch else {"ok": False, "error": "Not found"})
            return

        if path.startswith("/outputs/sw5e/"):
            fname = os.path.basename(path)
            fpath = Path(sw5e_engine.SW5E_OUTPUTS_DIR) / fname
            if fpath.exists():
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)
            return

        if path == "/api/sw5e/state":
            self._send_json({
                "characters": sw5e_engine.list_characters(),
                "ships": sw5e_engine.list_ships(),
                "default_character": sw5e_engine.default_character(),
                "default_ship": sw5e_engine.default_ship(),
            })
            return

        if path == "/api/sw5e/character":
            qs = urllib.parse.parse_qs(parsed.query)
            cid = (qs.get("id") or [""])[0]
            ch = sw5e_engine.load_character(cid) if cid else None
            self._send_json({"ok": bool(ch), "character": sw5e_engine.calculate_character(ch)} if ch else {"ok": False, "error": "Not found"})
            return

        if path == "/api/sw5e/ship":
            qs = urllib.parse.parse_qs(parsed.query)
            sid = (qs.get("id") or [""])[0]
            sh = sw5e_engine.load_ship(sid) if sid else None
            self._send_json({"ok": bool(sh), "ship": sw5e_engine.calculate_ship(sh)} if sh else {"ok": False, "error": "Not found"})
            return

        if path.startswith("/outputs/dcc/"):
            fname = os.path.basename(path)
            fpath = Path(dcc_engine.DCC_OUTPUTS_DIR) / fname
            if fpath.exists():
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)
            return

        if path == "/api/dcc/characters":
            self._send_json({
                "characters": dcc_engine.list_characters(),
                "rules": dcc_engine.load_rules_config(),
                "default_character": dcc_engine.default_character(),
            })
            return

        if path == "/api/dcc/character":
            qs = urllib.parse.parse_qs(parsed.query)
            cid = (qs.get("id") or [""])[0]
            ch = dcc_engine.load_character(cid) if cid else None
            if not ch:
                self._send_json({"ok": False, "error": "Character not found"})
                return
            self._send_json({"ok": True, "character": dcc_engine.calculate_character(ch)})
            return

        if path.startswith("/outputs/images/"):
            fname = os.path.basename(path)
            fpath = OUTPUT_IMAGES_DIR / fname
            if fpath.exists():
                mime = mimetypes.guess_type(str(fpath))[0] or "image/png"
                data = fpath.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)
            return

        if path == "/api/status":
            self._send_json({
                "comfy": check_comfy_status(),
                "llm": check_llm_status(),
                "logs": SERVICE_PROCS["agent_logs"][-80:]
            })
            return

        if path == "/api/models":
            self._send_json(list_installed_models())
            return

        if path == "/api/loras":
            self._send_json({"loras": get_available_loras()})
            return

        if path == "/api/config":
            self._send_json(load_config())
            return

        if path == "/api/gallery":
            imgs = []
            for p in sorted(OUTPUT_IMAGES_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    imgs.append({
                        "filename": p.name,
                        "url": f"/outputs/images/{p.name}",
                        "disk_path": str(p)
                    })
            self._send_json({"images": imgs[:60]})
            return

        if path == "/api/studio-skills":
            self._send_json({"skills": load_studio_skills()})
            return

        if path == "/api/learned-memory":
            self._send_json(load_learned_memory())
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            body = self._read_json()

            if path == "/api/service/start":
                svc = body.get("service")
                if svc == "comfy":
                    self._send_json(start_comfyui())
                elif svc == "unload_llm":
                    self._send_json(unload_local_llm())
                else:
                    self._send_json(start_lmstudio_server())
                return

            if path == "/api/test-gemini":
                cfg = load_config()
                key = get_effective_gemini_key(cfg)
                if not key:
                    self._send_json({"ok": False, "error": "Please enter your Gemini API Key first."})
                    return
                model_name = cfg.get("gemini_model", "gemini-2.5-flash")
                out = call_gemini_api(
                    [{"role": "user", "content": "Reply with one short sentence confirming Gemini API is connected with BLOCK_NONE safety settings."}],
                    key,
                    model_name=model_name,
                    temperature=0.3,
                    max_tokens=60
                )
                self._send_json({"ok": True, "reply": f"[{model_name}] {out}"})
                return

            if path == "/api/generate":
                res = generate_image_via_comfy(body)
                self._send_json(res)
                return

            if path == "/api/upload":
                fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(body['filename'])}"
                dest = OUTPUT_IMAGES_DIR / fname
                dest.write_bytes(base64.b64decode(body["data_b64"]))
                w, h = get_image_dimensions(dest)
                best_w, best_h = nearest_sdxl_resolution(w, h)
                self._send_json({
                    "ok": True,
                    "url": f"/outputs/images/{fname}",
                    "disk_path": str(dest),
                    "width": w,
                    "height": h,
                    "recommended_res": f"{best_w}x{best_h}"
                })
                return

            if path == "/api/gallery/delete":
                if body.get("delete_all"):
                    removed = 0
                    for p in OUTPUT_IMAGES_DIR.iterdir():
                        if p.is_file():
                            p.unlink(missing_ok=True)
                            removed += 1
                    log_agent(f"Deleted all gallery files ({removed} files).")
                    self._send_json({"ok": True, "removed": removed})
                    return
                fname = os.path.basename(body.get("filename", ""))
                if not fname:
                    self._send_json({"ok": False, "error": "Missing filename"})
                    return
                img_p = OUTPUT_IMAGES_DIR / fname
                meta_p = img_p.with_suffix(".json")
                if img_p.exists():
                    img_p.unlink(missing_ok=True)
                if meta_p.exists():
                    meta_p.unlink(missing_ok=True)
                log_agent(f"Deleted gallery image: {fname}")
                self._send_json({"ok": True})
                return

            if path == "/api/describe-image":
                prompt_out = build_edit_prompt_with_vision_ai(
                    body.get("image_path", ""),
                    body.get("edit_instruction", "")
                )
                self._send_json({"ok": True, "prompt": prompt_out})
                return

            if path == "/api/enhance-prompt":
                enhanced = enhance_sdxl_prompt(
                    body.get("prompt", ""),
                    body.get("image_path", ""),
                    skill_id=body.get("skill_id", "")
                )
                self._send_json({"ok": True, "prompt": enhanced})
                return

            if path == "/api/studio-skills/delete":
                sid = os.path.basename(body.get("skill_id", ""))
                if not sid:
                    self._send_json({"ok": False, "error": "Missing skill_id"})
                    return
                sp = STUDIO_SKILLS_DIR / f"{sid}.json"
                if sp.exists():
                    sp.unlink(missing_ok=True)
                log_agent(f"Deleted Studio Skill: {sid}")
                self._send_json({"ok": True})
                return

            if path == "/api/learned-memory":
                mem = load_learned_memory()
                for k in ("enabled", "positive_boosts", "negative_blocks", "style_lessons"):
                    if k in body:
                        mem[k] = body[k]
                save_learned_memory(mem)
                log_agent("Updated persistent learned_memory.json rules.")
                self._send_json({"ok": True, "memory": mem})
                return

            if path == "/api/fix-and-learn":
                res_fix = fix_and_learn_from_image(
                    image_path=body.get("image_path", ""),
                    feedback_text=body.get("feedback", ""),
                    current_prompt=body.get("current_prompt", ""),
                    current_negative=body.get("current_negative", ""),
                    skill_id=body.get("skill_id", ""),
                    remember_globally=bool(body.get("remember_globally", True)),
                    update_skill=bool(body.get("update_skill", False)),
                    auto_regenerate=bool(body.get("auto_regenerate", True))
                )
                self._send_json(res_fix)
                return

            if path == "/api/chat":
                res = handle_agent_chat(
                    body.get("message", ""),
                    body.get("history", []),
                    image_path=body.get("image_path", ""),
                    mask_image_b64=body.get("mask_image_b64", ""),
                    original_image_path=body.get("original_image_path", ""),
                    denoise=float(body.get("denoise", 0.60)),
                    action_mode=body.get("action_mode", "auto"),
                    preserve_face=bool(body.get("preserve_face", True)),
                    dcc_mode=bool(body.get("dcc_mode", False)),
                    dcc_character=body.get("dcc_character"),
                    sw5e_mode=bool(body.get("sw5e_mode", False)),
                    sw5e_character=body.get("sw5e_character"),
                    sw5e_ship=body.get("sw5e_ship"),
                    dm_mode=bool(body.get("dm_mode", False)),
                    dm_system=body.get("dm_system", "dnd5e"),
                    dnd5e_mode=bool(body.get("dnd5e_mode", False)),
                    dnd5e_character=body.get("dnd5e_character")
                )
                self._send_json(res)
                return

            if path == "/api/dnd5e/calculate":
                self._send_json({"ok": True, "character": dnd5e_engine.calculate_character(body)})
                return

            if path == "/api/dnd5e/save":
                ch = dnd5e_engine.save_character(body)
                self._send_json({"ok": True, "character": ch, "characters": dnd5e_engine.list_characters()})
                return

            if path == "/api/dnd5e/delete":
                ok = dnd5e_engine.delete_character(body.get("id", ""))
                self._send_json({"ok": ok, "characters": dnd5e_engine.list_characters()})
                return

            if path == "/api/dnd5e/export-pdf":
                res = dnd5e_engine.export_dnd5e_pdf(body.get("character") or body)
                self._send_json({"ok": True, **res, "characters": dnd5e_engine.list_characters()})
                return

            if path == "/api/rules/reindex":
                started = rules_rag.start_background_indexing(force=bool(body.get("force", False)), log_fn=log_agent)
                self._send_json({"ok": True, "started": started, "status": rules_rag.get_index_status()})
                return

            if path == "/api/ollama/pull":
                cfg = load_config()
                ok = llm_router.pull_ollama_model_bg(body.get("model", "qwen2.5:7b"), cfg.get("ollama_url", "http://127.0.0.1:11434"))
                self._send_json({"ok": ok})
                return

            if path == "/api/rules/upload":
                sys_key = body.get("system", "dnd5e")
                folder = rules_rag.SYSTEM_FOLDERS.get(sys_key)
                if not folder:
                    self._send_json({"ok": False, "error": "Invalid system"})
                    return
                folder.mkdir(parents=True, exist_ok=True)
                fname = os.path.basename(body.get("filename", "rulebook.pdf"))
                (folder / fname).write_bytes(base64.b64decode(body["data_b64"]))
                rules_rag.start_background_indexing(force=False, log_fn=log_agent)
                self._send_json({"ok": True, "filename": fname})
                return

            if path == "/api/campaign/hub":
                row = campaign_engine.upsert_hub(body)
                self._send_json({"ok": True, "hub": row, "tree": campaign_engine.get_campaign_tree(row.get("campaign_system", ""))})
                return

            if path == "/api/campaign/node":
                row = campaign_engine.upsert_node(body)
                self._send_json({"ok": True, "node": row, "tree": campaign_engine.get_campaign_tree(body.get("campaign_system", ""))})
                return

            if path == "/api/campaign/beat":
                row = campaign_engine.upsert_beat(body)
                self._send_json({"ok": True, "beat": row, "tree": campaign_engine.get_campaign_tree(body.get("campaign_system", ""))})
                return

            if path == "/api/campaign/entity":
                row = campaign_engine.upsert_entity(body)
                self._send_json({"ok": True, "entity": row, "tree": campaign_engine.get_campaign_tree(body.get("campaign_system", ""))})
                return

            if path == "/api/campaign/entity/live":
                row = campaign_engine.update_entity_live(body.get("id", ""), body)
                self._send_json({"ok": bool(row), "entity": row, "tree": campaign_engine.get_campaign_tree(body.get("campaign_system", ""))})
                return

            if path == "/api/campaign/delete":
                ok = campaign_engine.delete_item(body.get("table", ""), body.get("id", ""))
                self._send_json({"ok": ok, "tree": campaign_engine.get_campaign_tree(body.get("campaign_system", ""))})
                return

            if path == "/api/campaign/ingest":
                res = campaign_engine.ingest_markdown(
                    body.get("filename", "campaign_notes.md"),
                    body.get("content", ""),
                    call_local_llm,
                    system=body.get("campaign_system", "dcc"),
                )
                self._send_json(res)
                return

            if path == "/api/campaign/scan-vault":
                sys_key = body.get("campaign_system", "dcc")
                results = []
                for p in sorted(campaign_engine.VAULT_SOURCE_DIR.glob("*.md")):
                    results.append(campaign_engine.ingest_markdown(p.name, p.read_text(encoding="utf-8"), call_local_llm, system=sys_key))
                self._send_json({"ok": True, "processed": len(results), "tree": campaign_engine.get_campaign_tree(sys_key)})
                return

            if path == "/api/campaign/populate":
                res = campaign_engine.populate_node(
                    body.get("node_id", ""),
                    int(body.get("count", 2)),
                    body.get("category_mix", "1 Bopca Merchant + 1 Rival GMC"),
                    body.get("hint", ""),
                    call_local_llm,
                    beat_id=body.get("beat_id") or None,
                )
                self._send_json(res)
                return

            if path == "/api/campaign/runbook":
                res = campaign_engine.export_session_runbook(
                    body.get("title", "Session Runbook"),
                    body.get("node_ids", []),
                    body.get("beat_ids"),
                )
                self._send_json(res)
                return

            if path == "/api/campaign/loot":
                sys_key = body.get("campaign_system", "dcc")
                if sys_key == "dnd5e":
                    res = campaign_rulesets.roll_dnd5e_treasure(body.get("tier", "Tier 1 (CR 0-4)"), body.get("reason", ""))
                elif sys_key == "sw5e":
                    res = campaign_rulesets.roll_sw5e_loot(body.get("tier", "Standard"), body.get("reason", ""))
                else:
                    res = campaign_dcc.roll_loot_box(
                        int(body.get("floor_number", 1)),
                        body.get("tier", "Bronze"),
                        body.get("reason", ""),
                    )
                self._send_json({"ok": True, **res})
                return

            if path == "/api/sw5e/calculate-char":
                self._send_json({"ok": True, "character": sw5e_engine.calculate_character(body)})
                return

            if path == "/api/sw5e/calculate-ship":
                self._send_json({"ok": True, "ship": sw5e_engine.calculate_ship(body)})
                return

            if path == "/api/sw5e/save-char":
                ch = sw5e_engine.save_character(body)
                self._send_json({"ok": True, "character": ch, "characters": sw5e_engine.list_characters()})
                return

            if path == "/api/sw5e/save-ship":
                sh = sw5e_engine.save_ship(body)
                self._send_json({"ok": True, "ship": sh, "ships": sw5e_engine.list_ships()})
                return

            if path == "/api/sw5e/delete-char":
                ok = sw5e_engine.delete_character(body.get("id", ""))
                self._send_json({"ok": ok, "characters": sw5e_engine.list_characters()})
                return

            if path == "/api/sw5e/delete-ship":
                ok = sw5e_engine.delete_ship(body.get("id", ""))
                self._send_json({"ok": ok, "ships": sw5e_engine.list_ships()})
                return

            if path == "/api/sw5e/export-pdf":
                res = sw5e_engine.export_sw5e_pdfs(
                    char_data=body.get("character"),
                    ship_data=body.get("ship"),
                )
                self._send_json({
                    "ok": True,
                    **res,
                    "characters": sw5e_engine.list_characters(),
                    "ships": sw5e_engine.list_ships(),
                })
                return

            if path == "/api/dcc/rules":
                saved = dcc_engine.save_rules_config(body)
                self._send_json({"ok": True, "rules": saved})
                return

            if path == "/api/dcc/calculate":
                calc = dcc_engine.calculate_character(body)
                self._send_json({"ok": True, "character": calc})
                return

            if path == "/api/dcc/save":
                saved = dcc_engine.save_character(body)
                self._send_json({"ok": True, "character": saved, "characters": dcc_engine.list_characters()})
                return

            if path == "/api/dcc/delete":
                ok = dcc_engine.delete_character(body.get("id", ""))
                self._send_json({"ok": ok, "characters": dcc_engine.list_characters()})
                return

            if path == "/api/dcc/export-pdf":
                res = dcc_engine.export_character_pdfs(
                    body.get("character") or body,
                    export_sheet=bool(body.get("export_sheet", True)),
                    export_journal=bool(body.get("export_journal", True)),
                )
                self._send_json({"ok": True, **res, "characters": dcc_engine.list_characters()})
                return

            if path == "/api/config":
                cfg = load_config()
                for k, v in body.items():
                    cfg[k] = v
                save_config(cfg)
                self._send_json({"ok": True, "config": cfg})
                return

            if path == "/api/models/download":
                url = body["url"]
                fname = os.path.basename(body["filename"])
                target_dir = COMFY_LORAS if body.get("type") == "lora" else COMFY_CHECKPOINTS
                dest = target_dir / fname

                def _dl():
                    log_agent(f"Downloading {fname} to {target_dir}...")
                    try:
                        urllib.request.urlretrieve(url, str(dest))
                        log_agent(f"Download complete: {dest}")
                    except Exception as e:
                        log_agent(f"Download failed: {e}")

                threading.Thread(target=_dl, daemon=True).start()
                self._send_json({"ok": True, "message": f"Downloading {fname} in the background. Watch Live Logs for progress!"})
                return

            self.send_error(404)
        except Exception as e:
            log_agent(f"API Error on {path}: {e}")
            self._send_json({"ok": False, "error": str(e)}, code=200)

def main():
    port = int(os.environ.get("AI_HUB_PORT", "7860"))
    rules_rag.start_background_indexing(force=False, log_fn=log_agent)
    server = ThreadingHTTPServer(("127.0.0.1", port), AIHubHandler)
    log_agent(f"Unified Local AI Hub running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
