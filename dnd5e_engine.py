import json
import math
import os
import re
import time
from typing import Any, Dict, List, Optional

import pymupdf as fitz
import app_paths

BASE_DIR = str(app_paths.DATA_DIR)
DND5E_ASSETS_DIR = os.path.join(BASE_DIR, "dnd5e_assets")
DND5E_TEMPLATES_DIR = os.path.join(DND5E_ASSETS_DIR, "templates")
DND5E_CHARS_DIR = os.path.join(DND5E_ASSETS_DIR, "characters")
DND5E_OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs", "dnd5e")

DND5E_GUIDE_MD = str(app_paths.get_resource_path("dnd5e_assets/templates/dnd5e_system_guide.md"))
DND5E_TEMPLATE_PDF = str(app_paths.get_resource_path("dnd5e_assets/templates/DnD5e_Character_Sheet.pdf"))

DND5E_P2_PORTRAIT_RECT = fitz.Rect(38.0, 132.0, 197.7, 347.1)

for _d in [DND5E_ASSETS_DIR, DND5E_TEMPLATES_DIR, DND5E_CHARS_DIR, DND5E_OUTPUTS_DIR]:
    os.makedirs(_d, exist_ok=True)

# (display_name, pdf_field_name, stat_key)
DND5E_SKILLS = [
    ("Acrobatics", "Acrobatics", "DEX"),
    ("Animal Handling", "Animal", "WIS"),
    ("Arcana", "Arcana", "INT"),
    ("Athletics", "Athletics", "STR"),
    ("Deception", "Deception", "CHA"),
    ("History", "History", "INT"),
    ("Insight", "Insight", "WIS"),
    ("Intimidation", "Intimidation", "CHA"),
    ("Investigation", "Investigation", "INT"),
    ("Medicine", "Medicine", "WIS"),
    ("Nature", "Nature", "INT"),
    ("Perception", "Perception", "WIS"),
    ("Performance", "Performance", "CHA"),
    ("Persuasion", "Persuasion", "CHA"),
    ("Religion", "Religion", "INT"),
    ("Sleight of Hand", "SleightofHand", "DEX"),
    ("Stealth", "Stealth", "DEX"),
    ("Survival", "Survival", "WIS"),
]

CANTRIP_FIELDS = ["Spells 1014", "Spells 1016", "Spells 1017", "Spells 1018", "Spells 1019", "Spells 1020", "Spells 1021", "Spells 1022"]
LVL1_SPELL_FIELDS = ["Spells 1015", "Spells 1023", "Spells 1024", "Spells 1025", "Spells 1026", "Spells 1027", "Spells 1028", "Spells 1029", "Spells 1030", "Spells 1031", "Spells 1032", "Spells 1033"]
LVL2_SPELL_FIELDS = ["Spells 1046", "Spells 1034", "Spells 1035", "Spells 1036", "Spells 1037", "Spells 1038", "Spells 1039", "Spells 1040", "Spells 1041", "Spells 1042", "Spells 1043", "Spells 1044", "Spells 1045"]


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


def _slugify(name: str, fallback: str = "dnd5e_char") -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "").strip()).strip("_").lower()
    return s or f"{fallback}_{int(time.time())}"


def default_character() -> Dict[str, Any]:
    return {
        "id": "",
        "name": "",
        "player_name": "",
        "race": "Human",
        "class_name": "Fighter",
        "level": 1,
        "background": "Soldier",
        "alignment": "Neutral Good",
        "xp": "0",
        "ac": 16,
        "hp_max": 12,
        "hp_current": 12,
        "hp_temp": 0,
        "hit_dice": "1d10",
        "speed": "30 ft.",
        "inspiration": "",
        "portrait_path": "",
        "stats": {"STR": 15, "DEX": 14, "CON": 14, "INT": 10, "WIS": 12, "CHA": 8},
        "save_profs": ["STR", "CON"],
        "skill_ranks": {"Athletics": 1, "Intimidation": 1, "Perception": 1},
        "weapons": [
            {"name": "Longsword", "atk": "+4", "damage": "1d8+2 Slashing"},
            {"name": "Javelin", "atk": "+4", "damage": "1d6+2 Piercing"},
        ],
        "attacks_notes": "",
        "currency": {"cp": "0", "sp": "0", "ep": "0", "gp": "10", "pp": "0"},
        "proficiencies_lang": "All armor, shields, simple & martial weapons\nLanguages: Common, Dwarvish",
        "equipment": "Chain Mail\nShield\nLongsword\nExplorer's Pack",
        "personality_traits": "",
        "ideals": "",
        "bonds": "",
        "flaws": "",
        "features_traits": "Fighting Style: Defense (+1 AC)\nSecond Wind (1d10 + Level)",
        "bio": {
            "age": "", "height": "", "weight": "", "eyes": "", "skin": "", "hair": "",
            "allies": "", "backstory": "", "treasure": "", "extra_features": "",
        },
        "spellcasting": {
            "class_name": "",
            "ability": "",
            "slots_1": "",
            "slots_2": "",
            "cantrips": [],
            "level_1": [],
            "level_2": [],
        },
    }


def calculate_character(raw: Dict[str, Any]) -> Dict[str, Any]:
    ch = default_character()
    for k in [
        "id", "name", "player_name", "race", "class_name", "background",
        "alignment", "xp", "hit_dice", "speed", "inspiration", "portrait_path",
        "attacks_notes", "proficiencies_lang", "equipment",
        "personality_traits", "ideals", "bonds", "flaws", "features_traits",
    ]:
        if k in raw and raw[k] is not None:
            ch[k] = str(raw[k])

    ch["level"] = max(1, min(20, _to_int(raw.get("level", 1), 1)))
    prof_bonus = 2 + ((ch["level"] - 1) // 4)
    ch["prof_bonus"] = prof_bonus

    raw_stats = raw.get("stats") or {}
    mods: Dict[str, int] = {}
    for s in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        val = max(1, min(30, _to_int(raw_stats.get(s, ch["stats"][s]), ch["stats"][s])))
        ch["stats"][s] = val
        mods[s] = ability_mod(val)
    ch["mods"] = mods

    save_profs = [str(x).upper() for x in (raw.get("save_profs") if isinstance(raw.get("save_profs"), list) else ch["save_profs"])]
    ch["save_profs"] = save_profs
    ch["saves"] = {s: mods[s] + (prof_bonus if s in save_profs else 0) for s in mods}

    raw_ranks = raw.get("skill_ranks") if isinstance(raw.get("skill_ranks"), dict) else ch["skill_ranks"]
    skill_ranks: Dict[str, int] = {}
    skill_bonuses: Dict[str, int] = {}
    for disp, _, skey in DND5E_SKILLS:
        rank = max(0, min(2, _to_int(raw_ranks.get(disp, 0), 0)))
        skill_ranks[disp] = rank
        skill_bonuses[disp] = mods[skey] + rank * prof_bonus
    ch["skill_ranks"] = skill_ranks
    ch["skill_bonuses"] = skill_bonuses

    ch["initiative"] = mods["DEX"]
    ch["passive_perception"] = 10 + skill_bonuses["Perception"]
    ch["ac"] = _to_int(raw.get("ac", 10 + mods["DEX"]), 10 + mods["DEX"])
    ch["hp_max"] = max(1, _to_int(raw.get("hp_max", 10 + mods["CON"]), 10 + mods["CON"]))
    ch["hp_current"] = max(0, _to_int(raw.get("hp_current", ch["hp_max"]), ch["hp_max"]))
    ch["hp_temp"] = max(0, _to_int(raw.get("hp_temp", 0), 0))

    if isinstance(raw.get("weapons"), list):
        ch["weapons"] = [
            {"name": str(w.get("name", "")), "atk": str(w.get("atk", "")), "damage": str(w.get("damage", ""))}
            for w in raw["weapons"][:3]
            if isinstance(w, dict) and str(w.get("name", "")).strip()
        ]

    if isinstance(raw.get("currency"), dict):
        for ck in ["cp", "sp", "ep", "gp", "pp"]:
            if ck in raw["currency"] and raw["currency"][ck] is not None:
                ch["currency"][ck] = str(raw["currency"][ck])

    if isinstance(raw.get("bio"), dict):
        for bk in ch["bio"]:
            if bk in raw["bio"] and raw["bio"][bk] is not None:
                ch["bio"][bk] = str(raw["bio"][bk])

    raw_sp = raw.get("spellcasting") if isinstance(raw.get("spellcasting"), dict) else {}
    sp_ab = str(raw_sp.get("ability", "")).upper().strip()
    ch["spellcasting"] = {
        "class_name": str(raw_sp.get("class_name", "")),
        "ability": sp_ab,
        "slots_1": str(raw_sp.get("slots_1", "")),
        "slots_2": str(raw_sp.get("slots_2", "")),
        "cantrips": [str(x) for x in (raw_sp.get("cantrips") or []) if str(x).strip()],
        "level_1": [str(x) for x in (raw_sp.get("level_1") or []) if str(x).strip()],
        "level_2": [str(x) for x in (raw_sp.get("level_2") or []) if str(x).strip()],
    }
    if sp_ab in mods:
        ch["spellcasting"]["save_dc"] = str(8 + prof_bonus + mods[sp_ab])
        ch["spellcasting"]["atk_bonus"] = fmt_mod(prof_bonus + mods[sp_ab])
    else:
        ch["spellcasting"]["save_dc"] = ""
        ch["spellcasting"]["atk_bonus"] = ""

    return ch


def list_characters() -> List[Dict[str, Any]]:
    items = []
    for fn in sorted(os.listdir(DND5E_CHARS_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(DND5E_CHARS_DIR, fn), "r", encoding="utf-8") as f:
                d = json.load(f)
            items.append({
                "id": d.get("id") or fn[:-5],
                "name": d.get("name") or fn[:-5],
                "race": d.get("race", ""),
                "class_name": d.get("class_name", ""),
                "level": d.get("level", 1),
                "portrait_path": d.get("portrait_path", ""),
            })
        except Exception:
            continue
    return items


def load_character(char_id: str) -> Optional[Dict[str, Any]]:
    p = os.path.join(DND5E_CHARS_DIR, f"{_slugify(char_id)}.json")
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_character(raw: Dict[str, Any]) -> Dict[str, Any]:
    ch = calculate_character(raw)
    ch["id"] = _slugify(ch.get("id") or ch.get("name"), "dnd5e_char")
    with open(os.path.join(DND5E_CHARS_DIR, f"{ch['id']}.json"), "w", encoding="utf-8") as f:
        json.dump(ch, f, indent=2)
    return ch


def delete_character(char_id: str) -> bool:
    p = os.path.join(DND5E_CHARS_DIR, f"{_slugify(char_id)}.json")
    if os.path.exists(p):
        os.remove(p)
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


def fill_dnd5e_character_pdf(ch: Dict[str, Any], out_path: str) -> str:
    doc = fitz.open(DND5E_TEMPLATE_PDF)
    st = ch["stats"]
    mods = ch["mods"]
    saves = ch["saves"]
    skb = ch["skill_bonuses"]
    cur = ch["currency"]

    p1: Dict[str, str] = {
        "CharacterName": ch.get("name", ""),
        "ClassLevel": f"{ch.get('class_name', '')} {ch.get('level', 1)}".strip(),
        "Background": ch.get("background", ""),
        "PlayerName": ch.get("player_name", ""),
        "Race ": ch.get("race", ""),
        "Race": ch.get("race", ""),
        "Alignment": ch.get("alignment", ""),
        "XP": str(ch.get("xp", "")),
        "Inspiration": ch.get("inspiration", ""),
        "ProfBonus": fmt_mod(ch.get("prof_bonus", 2)),
        "AC": str(ch.get("ac", 10)),
        "Initiative": fmt_mod(ch.get("initiative", 0)),
        "Speed": ch.get("speed", ""),
        "HPMax": str(ch.get("hp_max", 10)),
        "HPCurrent": str(ch.get("hp_current", 10)),
        "HPTemp": str(ch.get("hp_temp", 0)) if ch.get("hp_temp") else "",
        "HDTotal": str(ch.get("level", 1)),
        "HD": ch.get("hit_dice", ""),
        "Passive": str(ch.get("passive_perception", 10)),
        # Stats & Mods
        "STR": str(st["STR"]), "STRmod": fmt_mod(mods["STR"]), "ST Strength": fmt_mod(saves["STR"]),
        "DEX": str(st["DEX"]), "DEXmod": fmt_mod(mods["DEX"]), "ST Dexterity": fmt_mod(saves["DEX"]),
        "CON": str(st["CON"]), "CONmod": fmt_mod(mods["CON"]), "ST Constitution": fmt_mod(saves["CON"]),
        "INT": str(st["INT"]), "INTmod": fmt_mod(mods["INT"]), "ST Intelligence": fmt_mod(saves["INT"]),
        "WIS": str(st["WIS"]), "WISmod": fmt_mod(mods["WIS"]), "ST Wisdom": fmt_mod(saves["WIS"]),
        "CHA": str(st["CHA"]), "CHamod": fmt_mod(mods["CHA"]), "ST Charisma": fmt_mod(saves["CHA"]),
        # Currency & Text blocks
        "CP": cur.get("cp", "0"), "SP": cur.get("sp", "0"), "EP": cur.get("ep", "0"),
        "GP": cur.get("gp", "0"), "PP": cur.get("pp", "0"),
        "ProficienciesLang": ch.get("proficiencies_lang", ""),
        "Equipment": ch.get("equipment", ""),
        "AttacksSpellcasting": ch.get("attacks_notes", ""),
        "PersonalityTraits ": ch.get("personality_traits", ""),
        "PersonalityTraits": ch.get("personality_traits", ""),
        "Ideals": ch.get("ideals", ""),
        "Bonds": ch.get("bonds", ""),
        "Flaws": ch.get("flaws", ""),
        "Features and Traits": ch.get("features_traits", ""),
    }
    for disp, pdf_name, _ in DND5E_SKILLS:
        p1[pdf_name] = fmt_mod(skb.get(disp, 0))

    wps = ch.get("weapons", [])
    if len(wps) > 0:
        p1["Wpn Name"], p1["Wpn1 AtkBonus"], p1["Wpn1 Damage"] = wps[0]["name"], wps[0]["atk"], wps[0]["damage"]
    if len(wps) > 1:
        p1["Wpn Name 2"], p1["Wpn2 AtkBonus "], p1["Wpn2 Damage "] = wps[1]["name"], wps[1]["atk"], wps[1]["damage"]
    if len(wps) > 2:
        p1["Wpn Name 3"], p1["Wpn3 AtkBonus  "], p1["Wpn3 Damage "] = wps[2]["name"], wps[2]["atk"], wps[2]["damage"]

    _set_page_fields(doc[0], p1)

    # Page 2: Appearance, Portrait, Backstory, Allies, Treasure
    bio = ch.get("bio") or {}
    p2: Dict[str, str] = {
        "CharacterName 2": ch.get("name", ""),
        "Age": bio.get("age", ""), "Height": bio.get("height", ""), "Weight": bio.get("weight", ""),
        "Eyes": bio.get("eyes", ""), "Skin": bio.get("skin", ""), "Hair": bio.get("hair", ""),
        "Allies": bio.get("allies", ""),
        "Backstory": bio.get("backstory", ""),
        "Treasure": bio.get("treasure", ""),
        "Feat+Traits": bio.get("extra_features", ""),
    }
    _set_page_fields(doc[1], p2)
    if ch.get("portrait_path") and os.path.exists(ch["portrait_path"]):
        for w in doc[1].widgets():
            if w.field_name == "CHARACTER IMAGE":
                doc.xref_set_key(w.xref, "F", "2")
        doc[1].insert_image(DND5E_P2_PORTRAIT_RECT, filename=ch["portrait_path"], keep_proportion=True, overlay=True)

    # Page 3: Spellcasting
    sp = ch.get("spellcasting") or {}
    p3: Dict[str, str] = {
        "Spellcasting Class 2": sp.get("class_name", ""),
        "SpellcastingAbility 2": sp.get("ability", ""),
        "SpellSaveDC  2": sp.get("save_dc", ""),
        "SpellAtkBonus 2": sp.get("atk_bonus", ""),
        "SlotsTotal 19": sp.get("slots_1", ""),
        "SlotsTotal 20": sp.get("slots_2", ""),
    }
    for fname, val in zip(CANTRIP_FIELDS, sp.get("cantrips", [])):
        p3[fname] = val
    for fname, val in zip(LVL1_SPELL_FIELDS, sp.get("level_1", [])):
        p3[fname] = val
    for fname, val in zip(LVL2_SPELL_FIELDS, sp.get("level_2", [])):
        p3[fname] = val
    _set_page_fields(doc[2], p3)

    doc.save(out_path)
    doc.close()
    return out_path


def export_dnd5e_pdf(char_data: Dict[str, Any]) -> Dict[str, Any]:
    ch = save_character(char_data)
    safe = _slugify(ch.get("name") or ch["id"])
    ts = int(time.time())
    fname = f"{safe}_5e_{ts}.pdf"
    out_p = os.path.join(DND5E_OUTPUTS_DIR, fname)
    fill_dnd5e_character_pdf(ch, out_p)
    return {
        "character": ch,
        "file": {"filename": fname, "path": out_p, "url": f"/outputs/dnd5e/{fname}"},
    }


def build_dnd5e_agent_system_prompt(current_char: Optional[Dict[str, Any]] = None) -> str:
    guide = ""
    if os.path.exists(DND5E_GUIDE_MD):
        with open(DND5E_GUIDE_MD, "r", encoding="utf-8") as f:
            guide = f.read()[:5000]
    cur_json = json.dumps(current_char, indent=2) if current_char else "{}"
    return f"""You are the Dungeons & Dragons 5th Edition (D&D 5e) Session 0 Character Creation Assistant.
Build a complete, rules-accurate Level 1+ 5e character and ALWAYS include a valid JSON block at the end wrapped in ```dnd5e_json ... ``` so the Hub UI auto-populates the printable 3-page D&D 5e PDF.

Current Loaded Character: {cur_json}

Required ```dnd5e_json``` schema:
{{
  "name": "Lyra Nightbreeze",
  "player_name": "Joe",
  "race": "High Elf",
  "class_name": "Wizard",
  "level": 1,
  "background": "Sage",
  "alignment": "Neutral Good",
  "ac": 12,
  "hp_max": 8,
  "hit_dice": "1d6",
  "speed": "30 ft.",
  "stats": {{"STR": 8, "DEX": 14, "CON": 14, "INT": 16, "WIS": 12, "CHA": 10}},
  "save_profs": ["INT", "WIS"],
  "skill_ranks": {{"Arcana": 1, "History": 1, "Investigation": 1, "Perception": 1}},
  "weapons": [
    {{"name": "Quarterstaff", "atk": "+1", "damage": "1d6-1 Bludgeoning"}},
    {{"name": "Fire Bolt", "atk": "+5", "damage": "1d10 Fire"}}
  ],
  "currency": {{"gp": "10"}},
  "proficiencies_lang": "Daggers, darts, slings, quarterstaffs, light crossbows\\nLanguages: Common, Elvish, Draconic, Celestial",
  "equipment": "Quarterstaff\\nArcane Focus (Crystal)\\nScholar's Pack\\nSpellbook",
  "features_traits": "Darkvision 60 ft.\\nFey Ancestry\\nArcane Recovery",
  "spellcasting": {{
    "class_name": "Wizard",
    "ability": "INT",
    "slots_1": "2",
    "cantrips": ["Fire Bolt", "Mage Hand", "Prestidigitation"],
    "level_1": ["Magic Missile", "Shield", "Mage Armor", "Detect Magic"]
  }}
}}

Reference Rules:
{guide}
"""


def parse_dnd5e_json_from_llm(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    for pat in [r"```dnd5e_json\s*([\s\S]*?)```", r"```json\s*([\s\S]*?)```"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                obj = json.loads(m.group(1).strip())
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
    return None
