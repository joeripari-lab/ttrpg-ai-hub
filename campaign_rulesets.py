import math
import random
import re
from typing import Any, Dict, List


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


# ============================================================================
# D&D 5E CAMPAIGN ENTITY MATH & TREASURE
# ============================================================================
DND5E_TREASURE_TABLES = {
    "Tier 1 (CR 0-4)": [
        "120 gp + Potion of Healing (2d4+2 HP) + Scroll of Identify",
        "85 gp + +1 Ammunition (10x Arrows/Bolts) + Moon-Touched Shortsword",
        "150 gp + Bag of Holding (Uncommon) + Silvered Dagger",
    ],
    "Tier 2 (CR 5-10)": [
        "850 gp + +1 Weapon or +1 Shield + 2x Greater Healing Potions",
        "1,200 gp + Cloak of Protection (+1 AC & Saves) + Pearl of Power",
        "950 gp + Boots of Elvenkind + Spell Scroll (3rd Level)",
    ],
    "Tier 3 (CR 11-16)": [
        "4,500 gp + +2 Armor or +2 Weapon + Ring of Spell Storing",
        "6,200 gp + Flame Tongue Longsword + Potion of Superior Healing",
    ],
    "Tier 4 (CR 17+)": [
        "24,000 gp + +3 Legendary Weapon / Staff of Power + Potion of Supreme Healing",
        "35,000 gp + Robe of the Archmagi / Belt of Storm Giant Strength",
    ],
}


def calculate_dnd5e_entity(raw: Dict[str, Any], tier_level: int = 1) -> Dict[str, Any]:
    lvl = max(1, _to_int(raw.get("level", tier_level), tier_level))
    pb = 2 + ((lvl - 1) // 4)
    raw_sb = raw.get("stat_block") if isinstance(raw.get("stat_block"), dict) else {}
    raw_stats = raw_sb.get("stats") if isinstance(raw_sb.get("stats"), dict) else (raw.get("stats") if isinstance(raw.get("stats"), dict) else {})

    stats: Dict[str, int] = {}
    mods: Dict[str, int] = {}
    for s in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        val = max(1, min(30, _to_int(raw_stats.get(s, 10 + (lvl // 3)), 10)))
        stats[s] = val
        mods[s] = ability_mod(val)

    ac = max(5, _to_int(raw_sb.get("ac", 11 + mods["DEX"]), 11 + mods["DEX"]))
    hp_max = max(1, _to_int(raw_sb.get("hp_max", max(6, lvl * (6 + mods["CON"]))), 10))
    hp_current = max(0, min(hp_max, _to_int(raw_sb.get("hp_current", hp_max), hp_max)))
    speed = str(raw_sb.get("speed", "30 ft."))
    cr = str(raw_sb.get("cr", f"CR {max(1, lvl // 2)}" if lvl >= 2 else "CR 1/2"))

    raw_actions = raw_sb.get("actions") if isinstance(raw_sb.get("actions"), list) else []
    actions = []
    for act in raw_actions[:6]:
        if isinstance(act, dict) and str(act.get("name", "")).strip():
            actions.append({
                "name": str(act.get("name", "")).strip(),
                "atk": str(act.get("atk", fmt_mod(pb + max(mods["STR"], mods["DEX"])))),
                "damage": str(act.get("damage", f"1d8{fmt_mod(mods['STR'])}")).strip(),
                "effects": str(act.get("effects", "")).strip(),
            })
    if not actions:
        actions.append({
            "name": "Weapon Attack",
            "atk": fmt_mod(pb + max(mods["STR"], mods["DEX"])),
            "damage": f"1d8{fmt_mod(max(mods['STR'], mods['DEX']))}",
            "effects": "Melee or Ranged",
        })

    return {
        "system": "dnd5e",
        "tier_level": lvl,
        "prof_bonus": pb,
        "stats": stats,
        "mods": mods,
        "ac": ac,
        "hp_max": hp_max,
        "hp_current": hp_current,
        "speed": speed,
        "cr": cr,
        "spell_dc": 8 + pb + max(mods["INT"], mods["WIS"], mods["CHA"]),
        "actions": actions,
    }


def roll_dnd5e_treasure(tier: str = "Tier 1 (CR 0-4)", reason: str = "") -> Dict[str, Any]:
    t = tier if tier in DND5E_TREASURE_TABLES else "Tier 1 (CR 0-4)"
    picked = random.choice(DND5E_TREASURE_TABLES[t])
    note = f"Context: {reason}\n" if reason.strip() else ""
    return {
        "tier": t,
        "item": picked,
        "announcement": f"[D&D 5e TREASURE HOARD — {t}]\n{note}Loot Rolled: {picked}",
    }


# ============================================================================
# SW5E CAMPAIGN ENTITY MATH & CONTRABAND/BOUNTY LOOT
# ============================================================================
SW5E_LOOT_TABLES = {
    "Standard": [
        "350 cr + 2x Power Cells + Medpac (2d4+2 HP)",
        "500 cr + Thermal Detonator (Class-A) + Encrypted Datapad",
    ],
    "Premium": [
        "1,400 cr + Upgraded Blaster Carbine (+1 Attack) + Combat Suit",
        "1,800 cr + Vibrosword (Keen) + Wristpad Focus (+1 Tech DC)",
    ],
    "Prototype": [
        "4,500 cr + Deflector Belt (+1 AC) + Prototype Shield Generator (Ship Mod)",
        "5,200 cr + Beskar Vambraces (+1 AC, +1 DEX Saves)",
    ],
    "Advanced": [
        "12,000 cr + +2 Lightweapon Crystal + Advanced Hyperdrive Motivator",
        "15,000 cr + Stealth Field Generator + Mandalorian Jetboot Kit",
    ],
    "Artifact": [
        "35,000 cr + Ancient Sith/Jedi Holocron (+2 Casting DC) + +3 Weapon",
    ],
    "Legendary": [
        "80,000 cr + Beskar'gam Full Armor Set + Experimental Capital Turret Blueprint",
    ],
}


def calculate_sw5e_entity(raw: Dict[str, Any], tier_level: int = 1) -> Dict[str, Any]:
    lvl = max(1, _to_int(raw.get("level", tier_level), tier_level))
    pb = 2 + ((lvl - 1) // 4)
    raw_sb = raw.get("stat_block") if isinstance(raw.get("stat_block"), dict) else {}
    raw_stats = raw_sb.get("stats") if isinstance(raw_sb.get("stats"), dict) else (raw.get("stats") if isinstance(raw.get("stats"), dict) else {})

    stats: Dict[str, int] = {}
    mods: Dict[str, int] = {}
    for s in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        val = max(1, min(30, _to_int(raw_stats.get(s, 10 + (lvl // 3)), 10)))
        stats[s] = val
        mods[s] = ability_mod(val)

    ac = max(5, _to_int(raw_sb.get("ac", 12 + mods["DEX"]), 12 + mods["DEX"]))
    hp_max = max(1, _to_int(raw_sb.get("hp_max", max(8, lvl * (6 + mods["CON"]))), 10))
    hp_current = max(0, min(hp_max, _to_int(raw_sb.get("hp_current", hp_max), hp_max)))
    sp_max = max(0, _to_int(raw_sb.get("sp_max", 0), 0))
    sp_current = max(0, min(sp_max, _to_int(raw_sb.get("sp_current", sp_max), sp_max)))
    cr = str(raw_sb.get("cr", f"CR {max(1, lvl // 2)}" if lvl >= 2 else "CR 1/2"))

    raw_actions = raw_sb.get("actions") if isinstance(raw_sb.get("actions"), list) else []
    actions = []
    for act in raw_actions[:6]:
        if isinstance(act, dict) and str(act.get("name", "")).strip():
            actions.append({
                "name": str(act.get("name", "")).strip(),
                "atk": str(act.get("atk", fmt_mod(pb + max(mods["STR"], mods["DEX"])))),
                "damage": str(act.get("damage", f"1d8{fmt_mod(mods['DEX'])} Energy")).strip(),
                "effects": str(act.get("effects", "")).strip(),
            })
    if not actions:
        actions.append({
            "name": "Blaster Pistol",
            "atk": fmt_mod(pb + mods["DEX"]),
            "damage": f"1d6{fmt_mod(mods['DEX'])} Energy",
            "effects": "Range 40/160, Reload 16",
        })

    return {
        "system": "sw5e",
        "tier_level": lvl,
        "prof_bonus": pb,
        "stats": stats,
        "mods": mods,
        "ac": ac,
        "hp_max": hp_max,
        "hp_current": hp_current,
        "sp_max": sp_max,
        "sp_current": sp_current,
        "cr": cr,
        "tech_dc": 8 + pb + mods["INT"],
        "force_dc": 8 + pb + max(mods["WIS"], mods["CHA"]),
        "actions": actions,
    }


def roll_sw5e_loot(tier: str = "Standard", reason: str = "") -> Dict[str, Any]:
    t = tier if tier in SW5E_LOOT_TABLES else "Standard"
    picked = random.choice(SW5E_LOOT_TABLES[t])
    note = f"Contract / Target: {reason}\n" if reason.strip() else ""
    return {
        "tier": t,
        "item": picked,
        "announcement": f"[SW5e BOUNTY & CONTRABAND CACHE — {t}]\n{note}Cache Contents: {picked}",
    }


# ============================================================================
# SYSTEM-AWARE PROMPTS (INGESTION + NODE POPULATION)
# ============================================================================
def build_ingest_prompt(system: str, filename: str, chunk_text: str) -> str:
    sys_label = {"dnd5e": "D&D 5e", "sw5e": "Star Wars 5e (SW5e)"}.get(system, system)
    extra = (
        "Use Credits (cr), Blasters/Vibroweapons/Lightweapons, Force/Tech DCs, and Star Wars locations."
        if system == "sw5e"
        else "Use GP, D&D 5e CR, AC, HP, and fantasy locations."
    )
    return f"""You are a {sys_label} campaign parser. {extra}
Extract structured campaign data from the Markdown excerpt below (`{filename}`).
Respond ONLY with valid JSON inside ```json ... ```:
{{
  "macro_hubs": [
    {{
      "floor_number": 1,
      "name": "Region / Sector / City Name",
      "hub_type": "Region | City | Dungeon | Planet | Sector | Space Station",
      "collapse_timer_hours": 0,
      "controlling_faction": "Faction Name",
      "boss_name": "",
      "summary_md": "Brief overview"
    }}
  ],
  "micro_nodes": [
    {{
      "hub_name": "Region / Sector / City Name",
      "name": "Location / Venue Name",
      "node_type": "Tavern | Cantina | Spaceport | Dungeon Room | Shop | Guildhall | Encounter Zone",
      "minimap_marker": "White Dot",
      "description_md": "Description",
      "environmental_hazards": "",
      "projector_map_prompt": "Top-down VTT battlemap prompt, 8k"
    }}
  ],
  "session_beats": [
    {{
      "node_name": "Location / Venue Name",
      "sequence_order": 1,
      "beat_type": "Exploration | Social | Combat | Quest | Boss",
      "title": "Beat Title",
      "ai_announcement_md": "Read-aloud box text",
      "gm_notes_md": "GM notes & DCs",
      "loot_reward_tier": "Tier 1 (CR 0-4) | Standard"
    }}
  ],
  "entities": [
    {{
      "node_name": "Location / Venue Name",
      "name": "NPC or Enemy Name",
      "entity_category": "Ally NPC | Merchant | Rival Party | Mob | Boss",
      "race_or_type": "Species / Race",
      "class_or_role": "Role / Class",
      "level": 3,
      "disposition": "Friendly | Neutral | Suspicious | Hostile",
      "stats": {{"STR": 12, "DEX": 14, "CON": 12, "INT": 10, "WIS": 12, "CHA": 14}},
      "ac": 14,
      "hp_max": 24,
      "personality": "Personality",
      "catchphrase": "Signature quote",
      "quest_hook": "Hook"
    }}
  ]
}}

MARKDOWN EXCERPT:
{chunk_text}
"""


def build_populate_prompt(system: str, hub: Dict[str, Any], node: Dict[str, Any], count: int, category_mix: str, hint: str) -> str:
    sys_label = {"dnd5e": "D&D 5e", "sw5e": "Star Wars 5e (SW5e)"}.get(system, system)
    lvl = max(1, int(hub.get("floor_number", 1) or 1))
    return f"""You are a {sys_label} Game Master generating persistent NPCs/enemies for a live session.
Parent Hub: {hub.get('name')} (Tier/Level {lvl})
Location Node: {node.get('name')} ({node.get('node_type')})
Description: {node.get('description_md', '')}
Generate {count} distinct entities matching: {category_mix}.
GM Hint: {hint or 'Make them vivid, system-accurate, and ready for immediate play.'}

Respond ONLY with valid JSON inside ```json ... ```:
{{
  "entities": [
    {{
      "name": "Name",
      "entity_category": "Ally NPC | Merchant | Rival Party | Mob | Boss",
      "race_or_type": "Species / Race",
      "class_or_role": "Class or Role",
      "level": {lvl},
      "disposition": "Friendly | Neutral | Suspicious | Hostile",
      "stats": {{"STR": 12, "DEX": 14, "CON": 12, "INT": 12, "WIS": 10, "CHA": 12}},
      "ac": 14,
      "hp_max": {max(10, lvl * 8)},
      "personality": "Vivid trait",
      "catchphrase": "Quote",
      "quest_hook": "Hook",
      "actions": [
        {{"name": "Primary Attack", "atk": "+5", "damage": "1d8+3", "effects": ""}}
      ]
    }}
  ]
}}
"""
