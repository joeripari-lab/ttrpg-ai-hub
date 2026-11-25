import json
import math
import os
import re
import time
from typing import Any, Dict, List, Optional

import pymupdf as fitz
import app_paths

BASE_DIR = str(app_paths.DATA_DIR)
SW5E_ASSETS_DIR = os.path.join(BASE_DIR, "sw5e_assets")
SW5E_TEMPLATES_DIR = os.path.join(SW5E_ASSETS_DIR, "templates")
SW5E_CHARS_DIR = os.path.join(SW5E_ASSETS_DIR, "characters")
SW5E_SHIPS_DIR = os.path.join(SW5E_ASSETS_DIR, "ships")
SW5E_OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs", "sw5e")

SW5E_RULES_MD = str(app_paths.get_resource_path("sw5e_assets/templates/sw5e_rules.md"))
SW5E_CHAR_TEMPLATE_PDF = str(app_paths.get_resource_path("sw5e_assets/templates/SW5e_Character_Sheet.pdf"))
SW5E_SHIP_TEMPLATE_PDF = str(app_paths.get_resource_path("sw5e_assets/templates/SW5e_Ship_Sheet.pdf"))

for _d in [SW5E_ASSETS_DIR, SW5E_TEMPLATES_DIR, SW5E_CHARS_DIR, SW5E_SHIPS_DIR, SW5E_OUTPUTS_DIR]:
    os.makedirs(_d, exist_ok=True)

CHAR_SKILLS = [
    ("Athletics", "STR"),
    ("Acrobatics", "DEX"),
    ("Sleight of Hand", "DEX"),
    ("Stealth", "DEX"),
    ("Investigation", "INT"),
    ("Lore", "INT"),
    ("Nature", "INT"),
    ("Piloting", "INT"),
    ("Technology", "INT"),
    ("Animal Handling", "WIS"),
    ("Insight", "WIS"),
    ("Medicine", "WIS"),
    ("Perception", "WIS"),
    ("Survival", "WIS"),
    ("Deception", "CHA"),
    ("Intimidation", "CHA"),
    ("Performance", "CHA"),
    ("Persuasion", "CHA"),
]

SHIP_SKILLS = [
    ("boost", "STR"),
    ("ram", "STR"),
    ("hide", "DEX"),
    ("manu", "DEX"),
    ("patch", "CON"),
    ("reg", "CON"),
    ("astro", "INT"),
    ("data", "INT"),
    ("probe", "INT"),
    ("scan", "WIS"),
    ("impress", "CHA"),
    ("interfere", "CHA"),
    ("menace", "CHA"),
    ("swin", "CHA"),
]

SHIP_SIZE_TABLE = {
    "Tiny": {"mod_cap": 10, "min_crew": 1, "hull_die": "d4", "shield_die": "d4"},
    "Small": {"mod_cap": 20, "min_crew": 2, "hull_die": "d6", "shield_die": "d6"},
    "Medium": {"mod_cap": 30, "min_crew": 4, "hull_die": "d8", "shield_die": "d8"},
    "Large": {"mod_cap": 50, "min_crew": 10, "hull_die": "d10", "shield_die": "d10"},
    "Huge": {"mod_cap": 60, "min_crew": 100, "hull_die": "d12", "shield_die": "d12"},
    "Gargantuan": {"mod_cap": 70, "min_crew": 1000, "hull_die": "d20", "shield_die": "d20"},
}


def ability_mod(score: int) -> int:
    return math.floor((score - 10) / 2)


def fmt_mod(val: int) -> str:
    return f"+{val}" if val >= 0 else str(val)


def _to_int(val: Any, default: int = 0) -> int:
    if isinstance(val, bool):
        return default
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        m = re.search(r"-?\d+", val)
        if m:
            return int(m.group(0))
    return default


def _slugify(name: str, fallback: str = "sw5e_item") -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "").strip()).strip("_").lower()
    return s or f"{fallback}_{int(time.time())}"


# ============================================================================
# CHARACTER MODEL & CALCULATOR
# ============================================================================
def default_character() -> Dict[str, Any]:
    return {
        "id": "",
        "name": "",
        "player_name": "",
        "species": "Human",
        "size": "Medium",
        "speed": "30 ft.",
        "class_name": "Operative",
        "level": 1,
        "alignment": "Balanced/Gray",
        "background": "Scoundrel",
        "deployment_role": "Pilot (Rank 0)",
        "xp": "0",
        "xp_next": "300",
        "ac": 13,
        "armor_notes": "Combat Suit",
        "hp_max": 10,
        "hp_current": 10,
        "hit_dice": "1d8",
        "vision": "Normal",
        "credits": "1000",
        "force_points": 0,
        "tech_points": 0,
        "starting_feat": "",
        "stats": {"STR": 10, "DEX": 15, "CON": 14, "INT": 12, "WIS": 10, "CHA": 13},
        "save_profs": ["DEX", "INT"],
        "skill_ranks": {"Piloting": 1, "Stealth": 1, "Perception": 1, "Deception": 1},
        "weapons": [
            {"name": "Blaster Pistol", "attack": "+4", "damage": "1d6+2 Energy", "range": "40/160", "weight": "2 lb", "misc": "Blaster, Reload 16"},
        ],
        "combat_features": "",
        "proficiencies": "",
        "languages": "Galactic Basic",
        "features": "",
        "equipment": "",
        "powers": "",
        "bio": {
            "age": "", "height": "", "weight": "", "eyes": "", "hair": "", "skin": "",
            "gender": "", "place_of_birth": "", "appearance": "",
            "traits": "", "ideals": "", "bonds": "", "flaws": "", "bg_feature": "", "backstory": "",
        },
    }


def calculate_character(raw: Dict[str, Any]) -> Dict[str, Any]:
    ch = default_character()
    for k in [
        "id", "name", "player_name", "species", "size", "speed", "class_name",
        "alignment", "background", "deployment_role", "xp", "xp_next",
        "armor_notes", "hit_dice", "vision", "credits", "starting_feat",
        "combat_features", "proficiencies", "languages", "features", "equipment", "powers",
    ]:
        if k in raw and raw[k] is not None:
            ch[k] = str(raw[k])

    ch["level"] = max(1, _to_int(raw.get("level", 1), 1))
    prof_bonus = 2 + ((ch["level"] - 1) // 4)
    ch["prof_bonus"] = prof_bonus

    raw_stats = raw.get("stats") or {}
    mods: Dict[str, int] = {}
    for s in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        val = _to_int(raw_stats.get(s, ch["stats"][s]), ch["stats"][s])
        ch["stats"][s] = val
        mods[s] = ability_mod(val)
    ch["mods"] = mods

    save_profs = [str(x).upper() for x in (raw.get("save_profs") if isinstance(raw.get("save_profs"), list) else ch["save_profs"])]
    ch["save_profs"] = save_profs
    ch["saves"] = {s: mods[s] + (prof_bonus if s in save_profs else 0) for s in mods}

    raw_ranks = raw.get("skill_ranks") if isinstance(raw.get("skill_ranks"), dict) else ch["skill_ranks"]
    skill_ranks: Dict[str, int] = {}
    skill_bonuses: Dict[str, int] = {}
    for sk_name, stat_key in CHAR_SKILLS:
        rank = max(0, min(2, _to_int(raw_ranks.get(sk_name, 0), 0)))
        skill_ranks[sk_name] = rank
        skill_bonuses[sk_name] = mods[stat_key] + rank * prof_bonus
    ch["skill_ranks"] = skill_ranks
    ch["skill_bonuses"] = skill_bonuses

    ch["initiative"] = mods["DEX"]
    ch["passive_perception"] = 10 + skill_bonuses["Perception"]
    ch["ac"] = _to_int(raw.get("ac", 10 + mods["DEX"]), 10 + mods["DEX"])
    ch["hp_max"] = _to_int(raw.get("hp_max", 8 + mods["CON"]), 8 + mods["CON"])
    ch["hp_current"] = _to_int(raw.get("hp_current", ch["hp_max"]), ch["hp_max"])
    ch["force_points"] = max(0, _to_int(raw.get("force_points", 0), 0))
    ch["tech_points"] = max(0, _to_int(raw.get("tech_points", 0), 0))

    ch["casting"] = {
        "tech_atk": fmt_mod(prof_bonus + mods["INT"]),
        "tech_dc": str(8 + prof_bonus + mods["INT"]),
        "light_atk": fmt_mod(prof_bonus + mods["WIS"]),
        "light_dc": str(8 + prof_bonus + mods["WIS"]),
        "dark_atk": fmt_mod(prof_bonus + mods["CHA"]),
        "dark_dc": str(8 + prof_bonus + mods["CHA"]),
        "univ_atk": fmt_mod(prof_bonus + max(mods["WIS"], mods["CHA"])),
        "univ_dc": str(8 + prof_bonus + max(mods["WIS"], mods["CHA"])),
    }

    if isinstance(raw.get("weapons"), list):
        ch["weapons"] = [
            {
                "name": str(w.get("name", "")),
                "attack": str(w.get("attack", "")),
                "damage": str(w.get("damage", "")),
                "range": str(w.get("range", "")),
                "weight": str(w.get("weight", "")),
                "misc": str(w.get("misc", "")),
            }
            for w in raw["weapons"][:5]
            if isinstance(w, dict) and str(w.get("name", "")).strip()
        ]

    if isinstance(raw.get("bio"), dict):
        for bk in ch["bio"]:
            if bk in raw["bio"] and raw["bio"][bk] is not None:
                ch["bio"][bk] = str(raw["bio"][bk])

    return ch


# ============================================================================
# STARSHIP MODEL & CALCULATOR
# ============================================================================
def default_ship() -> Dict[str, Any]:
    return {
        "id": "",
        "name": "",
        "size": "Medium",
        "tier": 0,
        "role_spec": "None (Tier 0)",
        "manufacturer": "Corellian Engineering Corp.",
        "model": "YT-1300f Light Freighter",
        "credits_invested": "100,000 cr",
        "credits_next_tier": "50,000 cr",
        "ac": 14,
        "dr": "4",
        "armor_notes": "Stock Durasteel Plating",
        "flying_speed": "300 ft.",
        "turning_speed": "200 ft.",
        "hyperdrive": "Class 2.0 (Backup 12)",
        "shield_type": "Deflector Shield",
        "hp_max": 36,
        "hp_current": 36,
        "hull_dice": "3d8",
        "sp_max": 36,
        "sp_current": 36,
        "shield_dice": "3d8",
        "reactor": "Stock Ionization Reactor",
        "power_coupling": "Stock Power Coupling",
        "system_damage": "None",
        "stats": {"STR": 14, "DEX": 12, "CON": 14, "INT": 12, "WIS": 10, "CHA": 10},
        "save_profs": ["CON", "DEX"],
        "skill_ranks": {"manu": 1, "astro": 1, "scan": 1},
        "weapons": [
            {"name": "Dual Laser Cannon", "attack": "+3", "damage": "2d8 Energy", "range": "300/1200", "arc": "Turret 360", "notes": "Turret Hardpoint"},
        ],
        "mod_cap": 30,
        "total_fixed": 2,
        "fixed_used": 0,
        "total_turret": 1,
        "turret_used": 1,
        "modifications": [],
        "min_crew": 4,
        "current_crew": 1,
        "cargo_cap": "100 tons",
        "cargo_used": "0 tons",
        "fuel_cap": "50 units",
        "current_fuel": "50 units",
        "hidden_cargo_cap": "5 tons",
        "hidden_cargo_used": "0 tons",
        "cargo_items": [],
        "crew": [],
        "ship_features": "",
        "debt": "",
    }


def calculate_ship(raw: Dict[str, Any]) -> Dict[str, Any]:
    sh = default_ship()
    for k in [
        "id", "name", "size", "role_spec", "manufacturer", "model",
        "credits_invested", "credits_next_tier", "dr", "armor_notes",
        "flying_speed", "turning_speed", "hyperdrive", "shield_type",
        "hull_dice", "shield_dice", "reactor", "power_coupling", "system_damage",
        "cargo_cap", "cargo_used", "fuel_cap", "current_fuel",
        "hidden_cargo_cap", "hidden_cargo_used", "ship_features", "debt",
    ]:
        if k in raw and raw[k] is not None:
            sh[k] = str(raw[k])

    if sh["size"] not in SHIP_SIZE_TABLE:
        sh["size"] = "Medium"
    size_info = SHIP_SIZE_TABLE[sh["size"]]

    sh["tier"] = max(0, min(5, _to_int(raw.get("tier", 0), 0)))
    prof_bonus = 2 + (sh["tier"] // 2)
    sh["prof_bonus"] = prof_bonus

    raw_stats = raw.get("stats") or {}
    mods: Dict[str, int] = {}
    for s in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        val = _to_int(raw_stats.get(s, sh["stats"][s]), sh["stats"][s])
        sh["stats"][s] = val
        mods[s] = ability_mod(val)
    sh["mods"] = mods

    save_profs = [str(x).upper() for x in (raw.get("save_profs") if isinstance(raw.get("save_profs"), list) else sh["save_profs"])]
    sh["save_profs"] = save_profs
    sh["saves"] = {s: mods[s] + (prof_bonus if s in save_profs else 0) for s in mods}

    raw_ranks = raw.get("skill_ranks") if isinstance(raw.get("skill_ranks"), dict) else sh["skill_ranks"]
    skill_ranks: Dict[str, int] = {}
    skill_bonuses: Dict[str, int] = {}
    for sk_name, stat_key in SHIP_SKILLS:
        rank = max(0, min(2, _to_int(raw_ranks.get(sk_name, 0), 0)))
        skill_ranks[sk_name] = rank
        skill_bonuses[sk_name] = mods[stat_key] + rank * prof_bonus
    sh["skill_ranks"] = skill_ranks
    sh["skill_bonuses"] = skill_bonuses

    sh["passive_scan"] = 10 + skill_bonuses["scan"]
    sh["ac"] = _to_int(raw.get("ac", 12 + mods["DEX"]), 12 + mods["DEX"])
    sh["hp_max"] = _to_int(raw.get("hp_max", 24 + 3 * mods["CON"]), 24 + 3 * mods["CON"])
    sh["hp_current"] = _to_int(raw.get("hp_current", sh["hp_max"]), sh["hp_max"])
    sh["sp_max"] = _to_int(raw.get("sp_max", 24 + 3 * mods["STR"]), 24 + 3 * mods["STR"])
    sh["sp_current"] = _to_int(raw.get("sp_current", sh["sp_max"]), sh["sp_max"])

    sh["mod_cap"] = _to_int(raw.get("mod_cap", size_info["mod_cap"]), size_info["mod_cap"])
    sh["min_crew"] = _to_int(raw.get("min_crew", size_info["min_crew"]), size_info["min_crew"])
    sh["max_suites"] = 0 if sh["size"] == "Tiny" else max(0, 3 + 2 * mods["CON"])

    sh["total_fixed"] = _to_int(raw.get("total_fixed", 2), 2)
    sh["fixed_used"] = _to_int(raw.get("fixed_used", 0), 0)
    sh["total_turret"] = _to_int(raw.get("total_turret", 1), 1)
    sh["turret_used"] = _to_int(raw.get("turret_used", 1), 1)

    if isinstance(raw.get("weapons"), list):
        sh["weapons"] = [
            {
                "name": str(w.get("name", "")),
                "attack": str(w.get("attack", fmt_mod(2 + mods["INT"]))),
                "damage": str(w.get("damage", "")),
                "range": str(w.get("range", "")),
                "arc": str(w.get("arc", "")),
                "notes": str(w.get("notes", "")),
            }
            for w in raw["weapons"][:4]
            if isinstance(w, dict) and str(w.get("name", "")).strip()
        ]

    if isinstance(raw.get("modifications"), list):
        sh["modifications"] = [
            {
                "name": str(m.get("name", "")),
                "type": str(m.get("type", "")),
                "description": str(m.get("description", "")),
                "price": str(m.get("price", "")),
            }
            for m in raw["modifications"][:22]
            if isinstance(m, dict) and str(m.get("name", "")).strip()
        ]
    sh["total_mods"] = len(sh["modifications"])
    sh["total_suites"] = sum(1 for m in sh["modifications"] if "suite" in m["type"].lower())

    if isinstance(raw.get("crew"), list):
        sh["crew"] = [
            {"name": str(c.get("name", "")), "role": str(c.get("role", ""))}
            for c in raw["crew"]
            if isinstance(c, dict) and str(c.get("name", "")).strip()
        ]
    sh["current_crew"] = _to_int(raw.get("current_crew", len(sh["crew"])), len(sh["crew"]))

    if isinstance(raw.get("cargo_items"), list):
        sh["cargo_items"] = [
            {"item": str(ci.get("item", "")), "weight": str(ci.get("weight", ""))}
            for ci in raw["cargo_items"]
            if isinstance(ci, dict) and str(ci.get("item", "")).strip()
        ]

    return sh


# ============================================================================
# STORAGE CRUD
# ============================================================================
def _list_dir_items(folder: str, summary_keys: List[str]) -> List[Dict[str, Any]]:
    out = []
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, fn), "r", encoding="utf-8") as f:
                data = json.load(f)
            row = {"id": data.get("id") or fn[:-5]}
            for k in summary_keys:
                row[k] = data.get(k, "")
            out.append(row)
        except Exception:
            continue
    return out


def list_characters() -> List[Dict[str, Any]]:
    return _list_dir_items(SW5E_CHARS_DIR, ["name", "species", "class_name", "level"])


def list_ships() -> List[Dict[str, Any]]:
    return _list_dir_items(SW5E_SHIPS_DIR, ["name", "size", "tier", "model"])


def load_character(char_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(SW5E_CHARS_DIR, f"{_slugify(char_id)}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ship(ship_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(SW5E_SHIPS_DIR, f"{_slugify(ship_id)}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_character(raw: Dict[str, Any]) -> Dict[str, Any]:
    ch = calculate_character(raw)
    ch["id"] = _slugify(ch.get("id") or ch.get("name"), "sw5e_char")
    with open(os.path.join(SW5E_CHARS_DIR, f"{ch['id']}.json"), "w", encoding="utf-8") as f:
        json.dump(ch, f, indent=2)
    return ch


def save_ship(raw: Dict[str, Any]) -> Dict[str, Any]:
    sh = calculate_ship(raw)
    sh["id"] = _slugify(sh.get("id") or sh.get("name"), "sw5e_ship")
    with open(os.path.join(SW5E_SHIPS_DIR, f"{sh['id']}.json"), "w", encoding="utf-8") as f:
        json.dump(sh, f, indent=2)
    return sh


def delete_character(char_id: str) -> bool:
    p = os.path.join(SW5E_CHARS_DIR, f"{_slugify(char_id)}.json")
    if os.path.exists(p):
        os.remove(p)
        return True
    return False


def delete_ship(ship_id: str) -> bool:
    p = os.path.join(SW5E_SHIPS_DIR, f"{_slugify(ship_id)}.json")
    if os.path.exists(p):
        os.remove(p)
        return True
    return False


# ============================================================================
# PDF FILLING
# ============================================================================
def _set_page_fields(page: fitz.Page, field_map: Dict[str, str]) -> int:
    updated = 0
    for w in page.widgets():
        if w.field_name in field_map:
            val = field_map[w.field_name]
            w.field_value = "" if val is None else str(val)
            w.update()
            updated += 1
    return updated


def _split_lines(text: str, count: int) -> List[str]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return [lines[i] if i < len(lines) else "" for i in range(count)]


def fill_sw5e_character_pdf(ch: Dict[str, Any], out_path: str) -> str:
    doc = fitz.open(SW5E_CHAR_TEMPLATE_PDF)
    st = ch["stats"]
    mods = ch["mods"]
    saves = ch["saves"]
    skb = ch["skill_bonuses"]
    cast = ch["casting"]

    p1: Dict[str, str] = {
        "Character Name": ch.get("name", ""),
        "Classes  Level": ch.get("class_name", ""),
        "LEVEL": str(ch.get("level", 1)),
        "Alignment": ch.get("alignment", ""),
        "Species": ch.get("species", ""),
        "Background": ch.get("background", ""),
        "Experience Points": str(ch.get("xp", "")),
        "XP Next Level": str(ch.get("xp_next", "")),
        "Players Name": ch.get("player_name", ""),
        "PROF BONUS": fmt_mod(ch.get("prof_bonus", 2)),
        "INITIATIVE": fmt_mod(ch.get("initiative", 0)),
        "ARMOR CLASS": str(ch.get("ac", 10)),
        "HIT POINTS MAXIMUM": str(ch.get("hp_max", 0)),
        "CURRENT HIT POINTS": str(ch.get("hp_current", 0)),
        "undefined": ch.get("hit_dice", ""),
        "PASSIVE PERCEPTION": str(ch.get("passive_perception", 10)),
        "VISION": ch.get("vision", ""),
        "base": ch.get("speed", ""),
        "special movement": ch.get("deployment_role", ""),
        # Ability scores & mods
        "STR": str(st["STR"]), "BASE STR BONUS": fmt_mod(mods["STR"]), "SAVING THROW 1": fmt_mod(saves["STR"]),
        "DEX": str(st["DEX"]), "BASE DEX BONUS": fmt_mod(mods["DEX"]), "SAVING THROW 3": fmt_mod(saves["DEX"]),
        "CON": str(st["CON"]), "BASE CON BONUS": fmt_mod(mods["CON"]), "SAVING THROW 7": fmt_mod(saves["CON"]),
        "INT": str(st["INT"]), "BASE INT BONUS": fmt_mod(mods["INT"]), "SAVING THROW 8": fmt_mod(saves["INT"]),
        "WIS": str(st["WIS"]), "BASE WIS BONUS": fmt_mod(mods["WIS"]), "SAVING THROW 14": fmt_mod(saves["WIS"]),
        "CHA": str(st["CHA"]), "BASE CHA BONUS": fmt_mod(mods["CHA"]), "SAVING THROW 20": fmt_mod(saves["CHA"]),
    }
    for sk_name, _ in CHAR_SKILLS:
        p1[sk_name] = fmt_mod(skb.get(sk_name, 0))

    # Armor notes (1_2..3_2)
    armor_lines = _split_lines(ch.get("armor_notes", ""), 3)
    p1["1_2"], p1["2_2"], p1["3_2"] = armor_lines[0], armor_lines[1], armor_lines[2]

    # Weapons (1..5)
    for idx, wp in enumerate(ch.get("weapons", [])[:5], start=1):
        p1[f"WEAPON {idx}"] = wp.get("name", "")
        p1[f"ATTACK {idx}"] = wp.get("attack", "")
        p1[f"DAMAGE {idx}"] = wp.get("damage", "")
        p1[f"RANGE {idx}"] = wp.get("range", "")
        p1[f"WEIGHT {idx}"] = wp.get("weight", "")
        p1[f"MISC {idx}"] = wp.get("misc", "")

    # Combat features (COMBAT FEAT 1..11)
    cf_lines = _split_lines(ch.get("combat_features", ""), 11)
    for idx, txt in enumerate(cf_lines, start=1):
        p1[f"COMBAT FEAT {idx}"] = txt

    _set_page_fields(doc[0], p1)

    # Page 2: Bio, Traits, Proficiencies, Languages, Features
    bio = ch.get("bio") or {}
    p2: Dict[str, str] = {
        "BIO 1": bio.get("age", ""), "BIO 5": bio.get("gender", ""),
        "BIO 2": bio.get("height", ""), "BIO 6": bio.get("weight", ""),
        "BIO 3": ch.get("size", ""), "BIO 7": bio.get("hair", ""),
        "BIO 4": bio.get("eyes", ""), "BIO 8": bio.get("skin", ""),
        "Place of Birth 1": bio.get("place_of_birth", ""),
    }
    app_lines = _split_lines(bio.get("appearance", ""), 2)
    p2["Appearance 1"], p2["Appearance 2"] = app_lines[0], app_lines[1]

    tr_lines = _split_lines(bio.get("traits", ""), 2)
    p2["1_6"], p2["2_6"] = tr_lines[0], tr_lines[1]
    id_lines = _split_lines(bio.get("ideals", ""), 3)
    p2["1_7"], p2["2_7"], p2["3_6"] = id_lines[0], id_lines[1], id_lines[2]
    bd_lines = _split_lines(bio.get("bonds", ""), 3)
    p2["1_8"], p2["2_8"], p2["3_7"] = bd_lines[0], bd_lines[1], bd_lines[2]
    fl_lines = _split_lines(bio.get("flaws", ""), 3)
    p2["1_9"], p2["2_9"], p2["3_8"] = fl_lines[0], fl_lines[1], fl_lines[2]

    bg_lines = _split_lines(bio.get("bg_feature", ""), 4)
    p2["1_10"], p2["2_10"], p2["3_9"], p2["4_5"] = bg_lines[0], bg_lines[1], bg_lines[2], bg_lines[3]

    bs_lines = _split_lines(bio.get("backstory", ""), 4)
    p2["1_11"], p2["2_11"], p2["3_10"], p2["4_6"] = bs_lines[0], bs_lines[1], bs_lines[2], bs_lines[3]

    prof_lines = _split_lines(ch.get("proficiencies", ""), 4)
    p2["1_3"], p2["2_3"], p2["3_3"], p2["4_2"] = prof_lines[0], prof_lines[1], prof_lines[2], prof_lines[3]

    lang_lines = _split_lines(ch.get("languages", ""), 4)
    p2["1_4"], p2["2_4"], p2["3_4"], p2["4_3"] = lang_lines[0], lang_lines[1], lang_lines[2], lang_lines[3]

    feat_text = ch.get("features", "")
    if ch.get("starting_feat"):
        feat_text = f"Starting Feat: {ch['starting_feat']}\n{feat_text}".strip()
    feat_lines = _split_lines(feat_text, 10)
    feat_keys = ["1_5", "2_5", "3_5", "4_4", "5_3", "6_3", "7_3", "8_3", "9_2", "10"]
    for fk, val in zip(feat_keys, feat_lines):
        p2[fk] = val

    _set_page_fields(doc[1], p2)

    # Page 3: Equipment & Credits
    p3: Dict[str, str] = {"CREDITS 1": str(ch.get("credits", ""))}
    eq_lines = _split_lines(ch.get("equipment", ""), 20)
    for idx, txt in enumerate(eq_lines, start=1):
        p3[f"ItemRow{idx}"] = txt
    _set_page_fields(doc[2], p3)

    # Page 4: Force/Tech Casting
    p4: Dict[str, str] = {
        "TECH POINTS": str(ch.get("tech_points", 0)),
        "FORCE POINTS": str(ch.get("force_points", 0)),
        "TECH ATTACK MODIFIER": cast["tech_atk"],
        "TECH SAVE DC": cast["tech_dc"],
        "FORCE ATTACK MODIFIER": cast["univ_atk"],
        "FORCE SAVE DC": cast["univ_dc"],
        "LIGHT ATTACK MODIFIER": cast["light_atk"],
        "LIGHT SAVE DC": cast["light_dc"],
        "DARK ATTACK MODIFIER": cast["dark_atk"],
        "DARK SAVE DC": cast["dark_dc"],
        "UNIVERSAL ATTACK MODIFIER": cast["univ_atk"],
        "UNIVERSAL SAVE DC": cast["univ_dc"],
    }
    pow_lines = _split_lines(ch.get("powers", ""), 4)
    for idx, txt in enumerate(pow_lines, start=1):
        p4[f"{idx}_15"] = txt
    _set_page_fields(doc[3], p4)

    doc.save(out_path)
    doc.close()
    return out_path


def fill_sw5e_ship_pdf(sh: Dict[str, Any], out_path: str) -> str:
    doc = fitz.open(SW5E_SHIP_TEMPLATE_PDF)
    st = sh["stats"]
    mods = sh["mods"]
    saves = sh["saves"]
    skb = sh["skill_bonuses"]

    p1: Dict[str, str] = {
        "Ship name": sh.get("name", ""),
        "SIze & class": f"{sh.get('size', 'Medium')} / Tier {sh.get('tier', 0)}",
        "Role": sh.get("role_spec", ""),
        "Manufacturer": sh.get("manufacturer", ""),
        "Model": sh.get("model", ""),
        "invested": sh.get("credits_invested", ""),
        "next tier": sh.get("credits_next_tier", ""),
        "AC": str(sh.get("ac", 12)),
        "DR": str(sh.get("dr", "0")),
        "armor notes": sh.get("armor_notes", ""),
        "flying": sh.get("flying_speed", ""),
        "turning": sh.get("turning_speed", ""),
        "hyperdrive": sh.get("hyperdrive", ""),
        "sp max": str(sh.get("sp_max", 0)),
        "sp curr": str(sh.get("sp_current", 0)),
        "sd max": sh.get("shield_dice", ""),
        "shield type": sh.get("shield_type", ""),
        "hp max": str(sh.get("hp_max", 0)),
        "hp curr": str(sh.get("hp_current", 0)),
        "hd max": sh.get("hull_dice", ""),
        "passive wis": str(sh.get("passive_scan", 10)),
        "reactor": sh.get("reactor", ""),
        "power coupling": sh.get("power_coupling", ""),
        "system damage": sh.get("system_damage", ""),
        # Ability scores & mods
        "str": str(st["STR"]), "str mod": fmt_mod(mods["STR"]), "str sav": fmt_mod(saves["STR"]),
        "dex": str(st["DEX"]), "dex mod": fmt_mod(mods["DEX"]), "dex sav": fmt_mod(saves["DEX"]),
        "con": str(st["CON"]), "con mod": fmt_mod(mods["CON"]), "con save": fmt_mod(saves["CON"]),
        "int": str(st["INT"]), "int mod": fmt_mod(mods["INT"]), "int save": fmt_mod(saves["INT"]),
        "wis": str(st["WIS"]), "wis mod": fmt_mod(mods["WIS"]), "wis save": fmt_mod(saves["WIS"]),
        "cha": str(st["CHA"]), "cha mod": fmt_mod(mods["CHA"]), "cha save": fmt_mod(saves["CHA"]),
    }
    for sk_name, _ in SHIP_SKILLS:
        p1[sk_name] = fmt_mod(skb.get(sk_name, 0))

    for idx, wp in enumerate(sh.get("weapons", [])[:4], start=1):
        p1[f"weap {idx}"] = wp.get("name", "")
        p1[f"weap {idx} atk"] = wp.get("attack", "")
        p1[f"weap {idx} dmg"] = wp.get("damage", "")
        p1[f"weap {idx} rng"] = wp.get("range", "")
        p1[f"weap {idx} arc"] = wp.get("arc", "")
        p1[f"weap {idx} notes"] = wp.get("notes", "")

    _set_page_fields(doc[0], p1)

    # Page 2 & 3: Modifications & Hardpoints
    p2: Dict[str, str] = {
        "mod cap": str(sh.get("mod_cap", 30)),
        "total mods": str(sh.get("total_mods", 0)),
        "total fixed": str(sh.get("total_fixed", 0)),
        "fixed used": str(sh.get("fixed_used", 0)),
        "total turret": str(sh.get("total_turret", 0)),
        "turret used": str(sh.get("turret_used", 0)),
        "max suites": str(sh.get("max_suites", 0)),
        "total suites": str(sh.get("total_suites", 0)),
    }
    p3: Dict[str, str] = {}
    for idx, mod in enumerate(sh.get("modifications", [])[:22], start=1):
        target = p2 if idx <= 12 else p3
        target[f"mod {idx}"] = mod.get("name", "")
        target[f"type {idx}"] = mod.get("type", "")
        target[f"descr {idx}"] = mod.get("description", "")
        target[f"price {idx}"] = mod.get("price", "")
    _set_page_fields(doc[1], p2)
    _set_page_fields(doc[2], p3)

    # Page 4: Cargo & Crew
    p4: Dict[str, str] = {
        "min crew": str(sh.get("min_crew", 1)),
        "current crew": str(sh.get("current_crew", 0)),
        "suite cap": str(sh.get("max_suites", 0)),
        "total available suite spaces": str(max(0, sh.get("max_suites", 0) - sh.get("total_suites", 0))),
        "reg cargo cap": sh.get("cargo_cap", ""),
        "reg cargo used": sh.get("cargo_used", ""),
        "fuel cap": sh.get("fuel_cap", ""),
        "current fuel": sh.get("current_fuel", ""),
        "hid cargo cap": sh.get("hidden_cargo_cap", ""),
        "hid cargo used": sh.get("hidden_cargo_used", ""),
    }
    for idx, cr in enumerate(sh.get("crew", [])[:20], start=1):
        p4[f"crew {idx}"] = cr.get("name", "")
        p4[f"role {idx}"] = cr.get("role", "")
    for idx, ci in enumerate(sh.get("cargo_items", [])[:20], start=1):
        p4[f"cargo {idx}"] = ci.get("item", "")
        p4[f"weight {idx}"] = ci.get("weight", "")
    _set_page_fields(doc[3], p4)

    doc.save(out_path)
    doc.close()
    return out_path


def export_sw5e_pdfs(
    char_data: Optional[Dict[str, Any]] = None,
    ship_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ts = int(time.time())
    results: Dict[str, Any] = {"files": {}}

    if char_data and (char_data.get("name") or char_data.get("species")):
        ch = save_character(char_data)
        safe = _slugify(ch.get("name") or ch["id"], "sw5e_char")
        fname = f"{safe}_SW5e_Character_{ts}.pdf"
        out_p = os.path.join(SW5E_OUTPUTS_DIR, fname)
        fill_sw5e_character_pdf(ch, out_p)
        results["character"] = ch
        results["files"]["character"] = {"filename": fname, "path": out_p, "url": f"/outputs/sw5e/{fname}"}

    if ship_data and (ship_data.get("name") or ship_data.get("model")):
        sh = save_ship(ship_data)
        safe = _slugify(sh.get("name") or sh["id"], "sw5e_ship")
        fname = f"{safe}_SW5e_Ship_{ts}.pdf"
        out_p = os.path.join(SW5E_OUTPUTS_DIR, fname)
        fill_sw5e_ship_pdf(sh, out_p)
        results["ship"] = sh
        results["files"]["ship"] = {"filename": fname, "path": out_p, "url": f"/outputs/sw5e/{fname}"}

    return results


# ============================================================================
# AGENT CHAT PROMPT & PARSER
# ============================================================================
def build_sw5e_agent_system_prompt(
    current_char: Optional[Dict[str, Any]] = None,
    current_ship: Optional[Dict[str, Any]] = None,
) -> str:
    rules_text = ""
    if os.path.exists(SW5E_RULES_MD):
        with open(SW5E_RULES_MD, "r", encoding="utf-8") as f:
            rules_text = f.read()
    cur_c = json.dumps(current_char, indent=2) if current_char else "{}"
    cur_s = json.dumps(current_ship, indent=2) if current_ship else "{}"
    return f"""You are the Star Wars 5e (SW5e) Session 0 Character & Starship Creation Assistant.
Follow the SW5e rules below strictly (Credits in cr, Blasters/Vibroweapons/Lightweapons, Size & Tier locks for ships, 1 Bonus Feat from background).
ALWAYS include a valid JSON block at the end of your reply wrapped in ```sw5e_json ... ``` containing `"character"` and/or `"ship"` so the Hub UI auto-populates both separate SW5e fillable PDFs.

Current Loaded Character: {cur_c}
Current Loaded Starship: {cur_s}

Required ```sw5e_json``` schema:
{{
  "character": {{
    "name": "Kaelen Voss",
    "species": "Twi'lek",
    "size": "Medium",
    "speed": "30 ft.",
    "class_name": "Operative",
    "level": 1,
    "alignment": "Balanced/Gray",
    "background": "Scoundrel",
    "deployment_role": "Pilot (Rank 0)",
    "starting_feat": "Charmer",
    "ac": 14,
    "armor_notes": "Combat Suit",
    "hp_max": 10,
    "hit_dice": "1d8",
    "credits": "1200",
    "force_points": 0,
    "tech_points": 0,
    "stats": {{"STR": 8, "DEX": 16, "CON": 14, "INT": 12, "WIS": 10, "CHA": 15}},
    "save_profs": ["DEX", "INT"],
    "skill_ranks": {{"Piloting": 1, "Stealth": 1, "Deception": 1, "Persuasion": 1}},
    "weapons": [
      {{"name": "Blaster Pistol", "attack": "+5", "damage": "1d6+3 Energy", "range": "40/160", "weight": "2 lb", "misc": "Blaster, Reload 16"}}
    ],
    "languages": "Galactic Basic, Twi'leki",
    "equipment": "Combat Suit\\nBlaster Pistol\\nDatapad"
  }},
  "ship": {{
    "name": "The Kessel Runner",
    "size": "Medium",
    "tier": 0,
    "role_spec": "None (Tier 0)",
    "manufacturer": "Corellian Engineering Corp.",
    "model": "YT-1300f Light Freighter",
    "ac": 14,
    "dr": "4",
    "flying_speed": "300 ft.",
    "turning_speed": "200 ft.",
    "hyperdrive": "Class 2.0",
    "hp_max": 36,
    "sp_max": 36,
    "stats": {{"STR": 14, "DEX": 12, "CON": 14, "INT": 12, "WIS": 10, "CHA": 10}},
    "weapons": [
      {{"name": "Dual Laser Cannon", "attack": "+3", "damage": "2d8 Energy", "range": "300/1200", "arc": "Turret 360", "notes": "Turret Hardpoint"}}
    ],
    "crew": [{{"name": "Kaelen Voss", "role": "Pilot"}}]
  }}
}}

Rules Reference:
{rules_text}
"""


def parse_sw5e_json_from_llm(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    for pat in [r"```sw5e_json\s*([\s\S]*?)```", r"```json\s*([\s\S]*?)```"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                obj = json.loads(m.group(1).strip())
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
    return None
