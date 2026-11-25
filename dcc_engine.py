import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import pymupdf as fitz
import app_paths

BASE_DIR = str(app_paths.DATA_DIR)
DCC_ASSETS_DIR = os.path.join(BASE_DIR, "dcc_assets")
DCC_TEMPLATES_DIR = os.path.join(DCC_ASSETS_DIR, "templates")
DCC_CHARACTERS_DIR = os.path.join(DCC_ASSETS_DIR, "characters")
DCC_OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs", "dcc")
RULES_MD_PATH = str(app_paths.get_resource_path("dcc_assets/templates/dcc_rules.md"))
RULES_CONFIG_PATH = os.path.join(DCC_ASSETS_DIR, "dcc_rules_config.json")
SHEET_TEMPLATE_PDF = str(app_paths.get_resource_path("dcc_assets/templates/DCC_Character_Sheet.pdf"))
JOURNAL_TEMPLATE_PDF = str(app_paths.get_resource_path("dcc_assets/templates/DCC_Character_Journal.pdf"))

os.makedirs(DCC_ASSETS_DIR, exist_ok=True)
os.makedirs(DCC_TEMPLATES_DIR, exist_ok=True)
os.makedirs(DCC_CHARACTERS_DIR, exist_ok=True)
os.makedirs(DCC_OUTPUTS_DIR, exist_ok=True)

# Exact portrait target rectangles (in PDF points)
# Journal Page 3 (0-indexed page 2): inside the green inner border above the "CHARACTER PORTRAIT" banner
JOURNAL_P3_PORTRAIT_RECT = fitz.Rect(54.0, 38.0, 373.5, 504.5)
# Character Sheet Page 1 (0-indexed page 0): Image7_af_image button rect
SHEET_P1_PORTRAIT_RECT = fitz.Rect(635.1, 79.5, 772.7, 194.3)

DEFAULT_RULES_CONFIG: Dict[str, Any] = {
    "stat_mod_brackets": [
        {"min": 0, "max": 1, "mod": 0, "label": "0-1"},
        {"min": 2, "max": 3, "mod": 1, "label": "2-3"},
        {"min": 4, "max": 5, "mod": 2, "label": "4-5 (Rulebook confirmed)"},
        {"min": 6, "max": 7, "mod": 3, "label": "6-7"},
        {"min": 8, "max": 9, "mod": 4, "label": "8-9"},
        {"min": 10, "max": 999, "mod": 5, "label": "10+"},
    ],
    "formulas": {
        "max_hp_base": 10,
        "max_hp_con_mult": 2,
        "max_mana_base": 5,
        "max_mana_int_mult": 2,
        "evade_base": 10,
        "default_move": "30 ft",
        "default_step": "5 ft",
        "default_size": "Medium",
    },
}


def load_rules_config() -> Dict[str, Any]:
    if os.path.exists(RULES_CONFIG_PATH):
        try:
            with open(RULES_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = json.loads(json.dumps(DEFAULT_RULES_CONFIG))
            if isinstance(data.get("stat_mod_brackets"), list) and data["stat_mod_brackets"]:
                merged["stat_mod_brackets"] = data["stat_mod_brackets"]
            if isinstance(data.get("formulas"), dict):
                merged["formulas"].update(data["formulas"])
            return merged
        except Exception:
            pass
    save_rules_config(DEFAULT_RULES_CONFIG)
    return json.loads(json.dumps(DEFAULT_RULES_CONFIG))


def save_rules_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    with open(RULES_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return cfg


def get_stat_mod(score: int, rules_cfg: Optional[Dict[str, Any]] = None) -> int:
    cfg = rules_cfg or load_rules_config()
    try:
        s = int(score)
    except (TypeError, ValueError):
        s = 0
    for bracket in cfg.get("stat_mod_brackets", DEFAULT_RULES_CONFIG["stat_mod_brackets"]):
        if int(bracket.get("min", 0)) <= s <= int(bracket.get("max", 999)):
            return int(bracket.get("mod", 0))
    return max(0, s // 2)


def fmt_mod(val: int) -> str:
    try:
        v = int(val)
    except (TypeError, ValueError):
        v = 0
    return f"+{v}" if v >= 0 else str(v)


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


def default_character() -> Dict[str, Any]:
    return {
        "id": "",
        "name": "",
        "race": "Human",
        "gender": "",
        "level": "0",
        "crawler_number": "",
        "class_name": "None",
        "floor": "1",
        "size": "Medium",
        "move": "30 ft",
        "step": "5 ft",
        "ai_favor": "1",
        "portrait_path": "",
        "stats": {
            "STR": {"unenhanced": 4, "enhanced": 4, "mod": 2},
            "INT": {"unenhanced": 4, "enhanced": 4, "mod": 2},
            "CON": {"unenhanced": 4, "enhanced": 4, "mod": 2},
            "DEX": {"unenhanced": 4, "enhanced": 4, "mod": 2},
            "CHA": {"unenhanced": 4, "enhanced": 4, "mod": 2},
        },
        "vitals": {
            "hp_current": 14,
            "hp_max": 14,
            "mana_current": 9,
            "mana_max": 9,
            "evade_buffs": 0,
            "evade_total": 12,
            "armor": 0,
            "dr_buffs": 0,
            "dr_total": 0,
            "popularity": 4,
        },
        "external_buffs": ["", "", ""],
        "attacks": [
            {
                "name": "Hand-to-Hand (Unarmed 1)",
                "rank": 3,
                "stat": "STR",
                "stat_mod": 2,
                "to_hit": "+5",
                "damage_dice": "1d4",
                "damage_stat_mod": "+2",
                "effects": "Evade | AI Favor: 0",
            },
            {
                "name": "Hand-to-Hand (Unarmed 2)",
                "rank": 3,
                "stat": "STR",
                "stat_mod": 2,
                "to_hit": "+5",
                "damage_dice": "1d4",
                "damage_stat_mod": "+2",
                "effects": "Evade | AI Favor: 0",
            },
        ],
        "skills": [],
        "gear": {
            "head": "",
            "torso": "",
            "arms": "",
            "hands": "",
            "legs": "",
            "feet": "",
            "accessories": "",
        },
        "past_trauma": "",
        "loose_ends": "",
        "regrets": "",
        "notes": "",
    }


def calculate_character(raw: Dict[str, Any], rules_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Deterministically recalculate all DCC mods, vitals, popularity, attacks, and trained skills."""
    cfg = rules_cfg or load_rules_config()
    formulas = cfg.get("formulas", DEFAULT_RULES_CONFIG["formulas"])
    char = default_character()

    for key in ["id", "name", "race", "gender", "level", "crawler_number", "class_name", "floor",
                "size", "move", "step", "ai_favor", "portrait_path", "past_trauma", "loose_ends", "regrets", "notes"]:
        if key in raw and raw[key] is not None:
            char[key] = str(raw[key])

    if not char["size"]:
        char["size"] = str(formulas.get("default_size", "Medium"))
    if not char["move"]:
        char["move"] = str(formulas.get("default_move", "30 ft"))
    if not char["step"]:
        char["step"] = str(formulas.get("default_step", "5 ft"))

    # Stats
    raw_stats = raw.get("stats") or {}
    for sname in ["STR", "INT", "CON", "DEX", "CHA"]:
        st = raw_stats.get(sname) or {}
        unenh = _to_int(st.get("unenhanced", st.get("base", 4)), 4)
        enh = _to_int(st.get("enhanced", unenh), unenh)
        if enh == 0 and unenh > 0:
            enh = unenh
        mod = get_stat_mod(enh, cfg)
        char["stats"][sname] = {"unenhanced": unenh, "enhanced": enh, "mod": mod}

    str_mod = char["stats"]["STR"]["mod"]
    int_mod = char["stats"]["INT"]["mod"]
    con_mod = char["stats"]["CON"]["mod"]
    dex_mod = char["stats"]["DEX"]["mod"]
    cha_mod = char["stats"]["CHA"]["mod"]

    # Vitals & Secondary Stats
    raw_vitals = raw.get("vitals") or {}
    evade_buffs = _to_int(raw_vitals.get("evade_buffs", 0), 0)
    armor = _to_int(raw_vitals.get("armor", 0), 0)
    dr_buffs = _to_int(raw_vitals.get("dr_buffs", 0), 0)

    calc_hp_max = _to_int(formulas.get("max_hp_base", 10), 10) + con_mod * _to_int(formulas.get("max_hp_con_mult", 2), 2)
    calc_mana_max = _to_int(formulas.get("max_mana_base", 5), 5) + int_mod * _to_int(formulas.get("max_mana_int_mult", 2), 2)
    hp_max = _to_int(raw_vitals.get("hp_max"), calc_hp_max) if raw_vitals.get("hp_max") not in (None, "", 0) else calc_hp_max
    hp_cur = _to_int(raw_vitals.get("hp_current"), hp_max) if raw_vitals.get("hp_current") not in (None, "", 0) else hp_max
    mana_max = _to_int(raw_vitals.get("mana_max"), calc_mana_max) if raw_vitals.get("mana_max") not in (None, "", 0) else calc_mana_max
    mana_cur = _to_int(raw_vitals.get("mana_current"), mana_max) if raw_vitals.get("mana_current") not in (None, "", 0) else mana_max

    evade_total = _to_int(formulas.get("evade_base", 10), 10) + dex_mod + evade_buffs
    dr_total = armor + dr_buffs
    popularity = cha_mod * 2

    char["vitals"] = {
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "mana_current": mana_cur,
        "mana_max": mana_max,
        "evade_buffs": evade_buffs,
        "evade_total": evade_total,
        "armor": armor,
        "dr_buffs": dr_buffs,
        "dr_total": dr_total,
        "popularity": popularity,
    }

    # External buffs (max 3)
    ext = raw.get("external_buffs") or ["", "", ""]
    char["external_buffs"] = [str(ext[i]) if i < len(ext) and ext[i] is not None else "" for i in range(3)]

    # Attacks (carry over to Sheet Page 1 and Journal Page 5)
    raw_attacks = raw.get("attacks")
    if isinstance(raw_attacks, list) and len(raw_attacks) > 0:
        attacks = []
        for atk in raw_attacks[:10]:
            if not isinstance(atk, dict):
                continue
            name = str(atk.get("name", "")).strip()
            if not name:
                continue
            rank = _to_int(atk.get("rank", 3), 3)
            stat = str(atk.get("stat", "STR")).upper().strip()
            if stat not in char["stats"]:
                stat = "STR"
            smod = char["stats"][stat]["mod"]
            attacks.append({
                "name": name,
                "rank": rank,
                "stat": stat,
                "stat_mod": smod,
                "to_hit": fmt_mod(rank + smod),
                "damage_dice": str(atk.get("damage_dice", "1d4")).strip() or "1d4",
                "damage_stat_mod": fmt_mod(smod),
                "effects": str(atk.get("effects", "")).strip(),
            })
        char["attacks"] = attacks
    else:
        # Update default unarmed attacks with live STR mod
        for atk in char["attacks"]:
            atk["stat_mod"] = str_mod
            atk["to_hit"] = fmt_mod(atk["rank"] + str_mod)
            atk["damage_stat_mod"] = fmt_mod(str_mod)

    # Skills (Rank 1+ only per rules)
    raw_skills = raw.get("skills") or []
    skills = []
    for sk in raw_skills:
        if not isinstance(sk, dict):
            continue
        name = str(sk.get("name", "")).strip()
        rank = _to_int(sk.get("rank", 1), 1)
        if not name or rank < 1:
            continue
        stat = str(sk.get("stat", "None")).upper().strip()
        if stat in char["stats"]:
            smod = char["stats"][stat]["mod"]
            stat_display = f"{stat} ({fmt_mod(smod)})"
            total_mod = fmt_mod(rank + smod)
        else:
            stat = "None"
            stat_display = "(None)"
            total_mod = fmt_mod(rank)
        check_type = str(sk.get("check_type", "Unopposed")).strip() or "Unopposed"
        origin = str(sk.get("origin", "")).strip()
        notes = str(sk.get("notes", "")).strip()
        skills.append({
            "name": name,
            "origin": origin,
            "rank": rank,
            "stat": stat,
            "stat_display": stat_display,
            "total_mod": total_mod,
            "check_type": check_type,
            "notes": notes,
        })
    char["skills"] = skills

    # Gear
    raw_gear = raw.get("gear") or {}
    for gk in ["head", "torso", "arms", "hands", "legs", "feet", "accessories"]:
        if gk in raw_gear and raw_gear[gk] is not None:
            char["gear"][gk] = str(raw_gear[gk])

    return char


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "crawler").strip()).strip("_").lower()
    return s or f"crawler_{int(time.time())}"


def list_characters() -> List[Dict[str, Any]]:
    items = []
    for fn in sorted(os.listdir(DCC_CHARACTERS_DIR)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(DCC_CHARACTERS_DIR, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items.append({
                "id": data.get("id") or fn[:-5],
                "name": data.get("name") or fn[:-5],
                "race": data.get("race", ""),
                "class_name": data.get("class_name", ""),
                "level": data.get("level", "0"),
                "portrait_path": data.get("portrait_path", ""),
            })
        except Exception:
            continue
    return items


def load_character(char_id: str) -> Optional[Dict[str, Any]]:
    safe_id = _slugify(char_id)
    path = os.path.join(DCC_CHARACTERS_DIR, f"{safe_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_character(raw_char: Dict[str, Any]) -> Dict[str, Any]:
    char = calculate_character(raw_char)
    if not char["id"]:
        char["id"] = _slugify(char.get("name") or f"crawler_{int(time.time())}")
    else:
        char["id"] = _slugify(char["id"])
    path = os.path.join(DCC_CHARACTERS_DIR, f"{char['id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(char, f, indent=2)
    return char


def delete_character(char_id: str) -> bool:
    safe_id = _slugify(char_id)
    path = os.path.join(DCC_CHARACTERS_DIR, f"{safe_id}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def _set_page_fields(page: fitz.Page, field_map: Dict[str, str]) -> int:
    updated = 0
    for w in page.widgets():
        if w.field_name in field_map:
            val = field_map[w.field_name]
            w.field_value = "" if val is None else str(val)
            w.update()
            updated += 1
    return updated


def _insert_portrait(page: fitz.Page, rect: fitz.Rect, portrait_path: str) -> bool:
    if not portrait_path or not os.path.exists(portrait_path):
        return False
    page.insert_image(rect, filename=portrait_path, keep_proportion=True, overlay=True)
    return True


def fill_character_sheet_pdf(char: Dict[str, Any], out_path: str) -> str:
    doc = fitz.open(SHEET_TEMPLATE_PDF)
    st = char["stats"]
    vt = char["vitals"]
    ext = char.get("external_buffs", ["", "", ""])

    # Page 1 fields
    p1_fields = {
        "Name": char.get("name", ""),
        "Race": char.get("race", ""),
        "Gender": char.get("gender", ""),
        "level": str(char.get("level", "")),
        "crawler number": str(char.get("crawler_number", "")),
        "class": char.get("class_name", ""),
        "Floor": str(char.get("floor", "")),
        # Core Stats: Enhanced, Unenhanced, Mod
        "Text Field 21": str(st["STR"]["enhanced"]),
        "Text Field 22": str(st["STR"]["unenhanced"]),
        "Text Field 23": fmt_mod(st["STR"]["mod"]),
        "Text Field 34": str(st["INT"]["enhanced"]),
        "Text Field 35": str(st["INT"]["unenhanced"]),
        "Text Field 36": fmt_mod(st["INT"]["mod"]),
        "Text Field 43": str(st["CON"]["enhanced"]),
        "Text Field 44": str(st["CON"]["unenhanced"]),
        "Text Field 45": fmt_mod(st["CON"]["mod"]),
        "Text Field 46": str(st["DEX"]["enhanced"]),
        "Text Field 47": str(st["DEX"]["unenhanced"]),
        "Text Field 48": fmt_mod(st["DEX"]["mod"]),
        "Text Field 49": str(st["CHA"]["enhanced"]),
        "Text Field 50": str(st["CHA"]["unenhanced"]),
        "Text Field 51": fmt_mod(st["CHA"]["mod"]),
        # Evade, Move, Step
        "Text Field 24": fmt_mod(st["DEX"]["mod"]),
        "Text Field 25": str(vt.get("evade_buffs", 0)),
        "Text Field 26": str(vt.get("evade_total", 10)),
        "Text Field 27": str(char.get("move", "")),
        "Text Field 28": str(char.get("step", "")),
        # DR, AI Favor, Size
        "Text Field 29": str(vt.get("armor", 0)),
        "Text Field 30": str(vt.get("dr_buffs", 0)),
        "Text Field 31": str(vt.get("dr_total", 0)),
        "Text Field 32": str(char.get("ai_favor", "")),
        "Text Field 33": str(char.get("size", "")),
        # Mana & HP summary
        "Text Field 38": str(vt.get("mana_max", 0)),
        "Text Field 37": str(vt.get("mana_current", 0)),
        "Text Field 39": f"HP: {vt.get('hp_current', 0)}/{vt.get('hp_max', 0)}",
        # External Buffs
        "Text Field 40": ext[0] if len(ext) > 0 else "",
        "Text Field 41": ext[1] if len(ext) > 1 else "",
        "Text Field 42": ext[2] if len(ext) > 2 else "",
    }

    # Attacks (5 rows on Sheet Page 1)
    sheet_attack_rows = [
        ("Text Field 55", "Text Field 551", "Text Field 52", "Text Field 53", "Text Field 54", "Text Field 56"),
        ("Text Field 61", "Text Field 57", "Text Field 59", "Text Field 58", "Text Field 60", "Text Field 62"),
        ("Text Field 67", "Text Field 63", "Text Field 65", "Text Field 64", "Text Field 66", "Text Field 68"),
        ("Text Field 73", "Text Field 69", "Text Field 71", "Text Field 70", "Text Field 72", "Text Field 74"),
        ("Text Field 79", "Text Field 75", "Text Field 77", "Text Field 76", "Text Field 78", "Text Field 80"),
    ]
    for idx, cols in enumerate(sheet_attack_rows):
        if idx < len(char.get("attacks", [])):
            atk = char["attacks"][idx]
            p1_fields[cols[0]] = atk.get("name", "")
            p1_fields[cols[1]] = str(atk.get("rank", ""))
            p1_fields[cols[2]] = fmt_mod(atk.get("stat_mod", 0))
            p1_fields[cols[3]] = atk.get("damage_dice", "")
            p1_fields[cols[4]] = atk.get("damage_stat_mod", "")
            p1_fields[cols[5]] = atk.get("effects", "")

    _set_page_fields(doc[0], p1_fields)
    if char.get("portrait_path") and os.path.exists(char["portrait_path"]):
        for w in doc[0].widgets():
            if w.field_name == "Image7_af_image":
                doc.xref_set_key(w.xref, "F", "2")  # Hide empty button placeholder
                break
        _insert_portrait(doc[0], SHEET_P1_PORTRAIT_RECT, char["portrait_path"])

    # Page 2 fields (Gear, Popularity, Trauma, Loose Ends, Regrets, Notes)
    gear = char.get("gear") or {}
    p2_fields = {
        "Text Field 92": gear.get("head", ""),
        "Text Field 93": gear.get("torso", ""),
        "Text Field 94": gear.get("arms", ""),
        "Text Field 95": gear.get("hands", ""),
        "Text Field 96": gear.get("legs", ""),
        "Text Field 97": gear.get("feet", ""),
        "Text Field 91": gear.get("accessories", ""),
        "Text Field 98": str(vt.get("popularity", 0)),
        "Text Field 99": char.get("past_trauma", ""),
        "Text Field 100": char.get("loose_ends", ""),
        "Text Field 101": char.get("regrets", ""),
        "Text Field 102": char.get("notes", ""),
    }
    _set_page_fields(doc[1], p2_fields)

    # Page 3 fields (Skills, up to 20 rows starting at Text Field 103)
    p3_fields: Dict[str, str] = {}
    for idx, sk in enumerate(char.get("skills", [])[:20]):
        base = 103 + 6 * idx
        p3_fields[f"Text Field {base}"] = f"{sk.get('name', '')} ({sk.get('total_mod', '+0')})"
        p3_fields[f"Text Field {base + 1}"] = str(sk.get("rank", ""))
        p3_fields[f"Text Field {base + 2}"] = sk.get("stat_display", "")
        p3_fields[f"Text Field {base + 3}"] = sk.get("check_type", "")
        origin_str = f"[{sk['origin']}] " if sk.get("origin") else ""
        p3_fields[f"Text Field {base + 4}"] = f"{origin_str}{sk.get('notes', '')}".strip()
    _set_page_fields(doc[2], p3_fields)

    doc.save(out_path)
    doc.close()
    return out_path


def fill_character_journal_pdf(char: Dict[str, Any], out_path: str) -> str:
    doc = fitz.open(JOURNAL_TEMPLATE_PDF)
    st = char["stats"]
    vt = char["vitals"]
    ext = char.get("external_buffs", ["", "", ""])

    # Page 3 (0-indexed 2): Character Portrait inside green border
    if char.get("portrait_path"):
        _insert_portrait(doc[2], JOURNAL_P3_PORTRAIT_RECT, char["portrait_path"])

    # Page 4 (0-indexed 3): Condensed Character Sheet
    p4_fields = {
        "Text Field 79": char.get("name", ""),
        "Text Field 81": char.get("race", ""),
        "Text Field 83": char.get("gender", ""),
        "Text Field 80": str(char.get("level", "")),
        "Text Field 82": str(char.get("crawler_number", "")),
        "Text Field 84": char.get("class_name", ""),
        "Dex Mod": fmt_mod(st["DEX"]["mod"]),
        "Buffs-01": str(vt.get("evade_buffs", 0)),
        "Evade Total": str(vt.get("evade_total", 10)),
        "Move": str(char.get("move", "")),
        "Step": str(char.get("step", "")),
        "Armor": str(vt.get("armor", 0)),
        "Buffs-02": str(vt.get("dr_buffs", 0)),
        "DR Total": str(vt.get("dr_total", 0)),
        "AI Favor": str(char.get("ai_favor", "")),
        "Size": str(char.get("size", "")),
        # Stats: Enhanced, Unenhanced, Mod
        "Text Field": str(st["STR"]["enhanced"]),
        "Text Field 2": str(st["STR"]["unenhanced"]),
        "Text Field 11": fmt_mod(st["STR"]["mod"]),
        "Text Field 3": str(st["INT"]["enhanced"]),
        "Text Field 4": str(st["INT"]["unenhanced"]),
        "Text Field 12": fmt_mod(st["INT"]["mod"]),
        "Text Field 5": str(st["CON"]["enhanced"]),
        "Text Field 7": str(st["CON"]["unenhanced"]),
        "Text Field 13": fmt_mod(st["CON"]["mod"]),
        "Text Field 6": str(st["DEX"]["enhanced"]),
        "Text Field 8": str(st["DEX"]["unenhanced"]),
        "Text Field 14": fmt_mod(st["DEX"]["mod"]),
        "Text Field 9": str(st["CHA"]["enhanced"]),
        "Text Field 10": str(st["CHA"]["unenhanced"]),
        "Text Field 15": fmt_mod(st["CHA"]["mod"]),
        # External Buffs
        "Text Field 76": ext[0] if len(ext) > 0 else "",
        "Text Field 77": ext[1] if len(ext) > 1 else "",
        "Text Field 78": ext[2] if len(ext) > 2 else "",
    }
    _set_page_fields(doc[3], p4_fields)

    # Page 5 (0-indexed 4): Attacks (10 rows)
    journal_attack_rows = [
        ("Text Field 73", "Text Field 16", "Text Field 110", "Text Field 120", "Text Field 140", "Text Field 36"),
        ("Text Field 72", "Text Field 18", "Text Field 111", "Text Field 122", "Text Field 141", "Text Field 37"),
        ("Text Field 67", "Text Field 20", "Text Field 112", "Text Field 124", "Text Field 142", "Text Field 38"),
        ("Text Field 66", "Text Field 22", "Text Field 113", "Text Field 126", "Text Field 143", "Text Field 39"),
        ("Text Field 61", "Text Field 24", "Text Field 114", "Text Field 128", "Text Field 144", "Text Field 40"),
        ("Text Field 60", "Text Field 26", "Text Field 115", "Text Field 130", "Text Field 145", "Text Field 41"),
        ("Text Field 55", "Text Field 28", "Text Field 116", "Text Field 132", "Text Field 146", "Text Field 42"),
        ("Text Field 54", "Text Field 30", "Text Field 117", "Text Field 134", "Text Field 147", "Text Field 43"),
        ("Text Field 49", "Text Field 32", "Text Field 118", "Text Field 136", "Text Field 148", "Text Field 44"),
        ("Text Field 48", "Text Field 34", "Text Field 119", "Text Field 138", "Text Field 149", "Text Field 45"),
    ]
    p5_fields: Dict[str, str] = {}
    for idx, cols in enumerate(journal_attack_rows):
        if idx < len(char.get("attacks", [])):
            atk = char["attacks"][idx]
            p5_fields[cols[0]] = atk.get("name", "")
            p5_fields[cols[1]] = str(atk.get("rank", ""))
            p5_fields[cols[2]] = fmt_mod(atk.get("stat_mod", 0))
            p5_fields[cols[3]] = atk.get("damage_dice", "")
            p5_fields[cols[4]] = atk.get("damage_stat_mod", "")
            p5_fields[cols[5]] = atk.get("effects", "")
    _set_page_fields(doc[4], p5_fields)

    doc.save(out_path)
    doc.close()
    return out_path


def export_character_pdfs(
    char_data: Dict[str, Any],
    export_sheet: bool = True,
    export_journal: bool = True,
) -> Dict[str, Any]:
    char = save_character(char_data)
    safe = _slugify(char.get("name") or char["id"])
    ts = int(time.time())
    results: Dict[str, Any] = {"character": char, "files": {}}

    if export_sheet:
        sheet_name = f"{safe}_Sheet_{ts}.pdf"
        sheet_out = os.path.join(DCC_OUTPUTS_DIR, sheet_name)
        fill_character_sheet_pdf(char, sheet_out)
        results["files"]["sheet"] = {
            "filename": sheet_name,
            "path": sheet_out,
            "url": f"/outputs/dcc/{sheet_name}",
        }

    if export_journal:
        journal_name = f"{safe}_Journal_{ts}.pdf"
        journal_out = os.path.join(DCC_OUTPUTS_DIR, journal_name)
        fill_character_journal_pdf(char, journal_out)
        results["files"]["journal"] = {
            "filename": journal_name,
            "path": journal_out,
            "url": f"/outputs/dcc/{journal_name}",
        }

    return results


def build_dcc_agent_system_prompt(current_char: Optional[Dict[str, Any]] = None) -> str:
    rules_text = ""
    if os.path.exists(RULES_MD_PATH):
        with open(RULES_MD_PATH, "r", encoding="utf-8") as f:
            rules_text = f.read()
    cfg = load_rules_config()
    cur_json = json.dumps(current_char, indent=2) if current_char else "{}"
    return f"""You are the Session 0 Dungeon Crawler World (DCC) Character Creation Assistant.
Follow the character creation rules below strictly, and ALWAYS include a valid JSON block at the end of your reply wrapped in ```dcc_json ... ``` so the Hub UI can automatically populate the Character Sheet & Character Journal PDFs.

Active Stat Mod Brackets: {json.dumps(cfg.get("stat_mod_brackets"))}
Active Vital Formulas: {json.dumps(cfg.get("formulas"))}
Current Loaded Character (update/merge with user requests if applicable): {cur_json}

Required ```dcc_json``` schema:
{{
  "name": "Carl",
  "race": "Human",
  "gender": "He/Him",
  "level": "1",
  "crawler_number": "4122",
  "class_name": "None",
  "floor": "1",
  "size": "Medium",
  "move": "30 ft",
  "step": "5 ft",
  "ai_favor": "1",
  "stats": {{
    "STR": {{"unenhanced": 5, "enhanced": 5}},
    "INT": {{"unenhanced": 4, "enhanced": 4}},
    "CON": {{"unenhanced": 5, "enhanced": 5}},
    "DEX": {{"unenhanced": 4, "enhanced": 4}},
    "CHA": {{"unenhanced": 3, "enhanced": 3}}
  }},
  "vitals": {{"evade_buffs": 0, "armor": 0, "dr_buffs": 0}},
  "external_buffs": ["", "", ""],
  "attacks": [
    {{"name": "Hand-to-Hand (Unarmed 1)", "rank": 3, "stat": "STR", "damage_dice": "1d4", "effects": "Evade | AI Favor: 0"}},
    {{"name": "Hand-to-Hand (Unarmed 2)", "rank": 3, "stat": "STR", "damage_dice": "1d4", "effects": "Evade | AI Favor: 0"}}
  ],
  "skills": [
    {{"name": "Marine Mechanics", "origin": "Career", "rank": 1, "stat": "INT", "check_type": "Unopposed", "notes": ""}}
  ],
  "gear": {{"head": "", "torso": "Leather Jacket", "arms": "", "hands": "", "legs": "Boxers", "feet": "", "accessories": ""}},
  "past_trauma": "",
  "loose_ends": "",
  "regrets": "",
  "notes": ""
}}

Rules Reference:
{rules_text}
"""


def parse_dcc_json_from_llm(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    for pat in [r"```dcc_json\s*([\s\S]*?)```", r"```json\s*([\s\S]*?)```"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                obj = json.loads(m.group(1).strip())
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
    return None
