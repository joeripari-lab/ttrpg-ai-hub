import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    _EXE_DIR = Path(sys.executable).resolve().parent
else:
    BUNDLE_DIR = Path(__file__).resolve().parent
    _EXE_DIR = BUNDLE_DIR

if os.environ.get("TTRPG_HUB_DATA_DIR"):
    DATA_DIR = Path(os.environ["TTRPG_HUB_DATA_DIR"]).expanduser().resolve()
elif not getattr(sys, "frozen", False) or (_EXE_DIR / "config.json").exists():
    DATA_DIR = _EXE_DIR
else:
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "TTRPG_AI_Hub"


def resolve_comfy_root(custom_path: str = "") -> Path:
    candidates = []
    if custom_path:
        candidates.append(Path(custom_path))
    if os.environ.get("COMFYUI_DIR"):
        candidates.append(Path(os.environ["COMFYUI_DIR"]))
    candidates.extend([
        DATA_DIR / "ComfyUI_windows_portable",
        Path(r"C:\ComfyUI_windows_portable"),
    ])
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


def get_resource_path(rel_path: str) -> Path:
    p_data = DATA_DIR / rel_path
    if p_data.exists():
        return p_data
    p_bundle = BUNDLE_DIR / rel_path
    if p_bundle.exists():
        return p_bundle
    return p_data


def ensure_data_dirs() -> None:
    for rel in [
        "outputs/images",
        "outputs/dcc",
        "outputs/sw5e",
        "outputs/dnd5e",
        "studio_skills",
        "Rules/DCC TTRPG",
        "Rules/DnD 5e",
        "Rules/SW5e",
        "campaign_vault/source_docs",
        "campaign_vault/floors",
        "campaign_vault/npcs",
        "campaign_vault/sessions",
        "dcc_assets/characters",
        "sw5e_assets/characters",
        "sw5e_assets/ships",
        "dnd5e_assets/characters",
    ]:
        (DATA_DIR / rel).mkdir(parents=True, exist_ok=True)


ensure_data_dirs()
