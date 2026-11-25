import json
import random
import re
from typing import Any, Dict, List, Optional

DCC_STAT_MOD_BRACKETS = [
    (1, 2, 1),
    (3, 5, 2),
    (6, 9, 3),
    (10, 19, 4),
    (20, 49, 5),
    (50, 99, 6),
    (100, 149, 7),
    (150, 199, 8),
    (200, 299, 9),
    (300, 999999, 10),
]

LOOT_TIERS = ["Bronze", "Silver", "Gold", "Platinum", "Legendary", "Celestial"]

LOOT_TABLES = {
    "Bronze": [
        "2x Cheap Healing Potion (restores 1 HB slot)",
        "Duct Tape & Rusty Crowbar (Misc Junk)",
        "Coupon: 10% Off at Desperado Club Bar",
        "Goblin Smoke Grenade (1d6+F, obscures 10ft)",
    ],
    "Silver": [
        "Enchanted Combat Boots (+1 DEX Mod to Evade)",
        "Bandolier of Goblin Dynamite (2d6+F Explosive)",
        "Scroll of Minor Shielding (+2 DR for 3 rounds)",
        "Reinforced Leather Jacket (+1 DR)",
    ],
    "Gold": [
        "Skill Book: Pugilism Mastery (+2 Rank)",
        "Ring of Viewer Appeal (+2 CHA Mod, +1 AI Favor/floor)",
        "Enchanted Brass Knuckles (1d8+STR, Smush bonus)",
        "Vial of Troll Blood (regenerates 1 HB slot/turn for 3 turns)",
    ],
    "Platinum": [
        "Amulet of the Showrunner (Reroll 1 failed Evade/round)",
        "High-Yield Anarchist Satchel (4d6+2F AoE)",
        "Desperado VIP Pass + +2 Stat Boost Tome",
    ],
    "Legendary": [
        "Crown of the Floor Warden (+3 All Stats, +3 DR)",
        "Reality-Shattering Gauntlet (Ignores Mob DR, +2F dmg)",
    ],
    "Celestial": [
        "Celestial Patron's Blessing (Permanent +5 Primary Stat + Unique Mutation)",
        "System-Breaking Artifact: Admin Override Token (1x floor-wide anomaly)",
    ],
}


def get_dcc_stat_mod(score: int) -> int:
    try:
        s = int(score)
    except (TypeError, ValueError):
        s = 1
    if s <= 0:
        return 0
    for lo, hi, mod in DCC_STAT_MOD_BRACKETS:
        if lo <= s <= hi:
            return mod
    return 10


def fmt_mod(v: int) -> str:
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


def calculate_dcc_entity(raw: Dict[str, Any], floor_number: int = 1) -> Dict[str, Any]:
    """Deterministically compute DCC stat mods, 10-slot HB, Evade DC, DR, and action economy."""
    f_num = max(1, _to_int(floor_number, 1))
    cat = str(raw.get("entity_category") or "Mob").strip()
    level = max(1, _to_int(raw.get("level", 1), 1))

    raw_sb = raw.get("stat_block") if isinstance(raw.get("stat_block"), dict) else {}
    raw_stats = raw_sb.get("stats") if isinstance(raw_sb.get("stats"), dict) else (raw.get("stats") if isinstance(raw.get("stats"), dict) else {})

    stats: Dict[str, int] = {}
    mods: Dict[str, int] = {}
    for s in ["STR", "INT", "CON", "DEX", "CHA"]:
        val = max(1, _to_int(raw_stats.get(s, 3 + (level // 2)), 3))
        stats[s] = val
        mods[s] = get_dcc_stat_mod(val)

    is_boss = "boss" in cat.lower() or "elite" in cat.lower()
    default_slots = 10 if ("crawler" in cat.lower() or "gmc" in cat.lower() or "npc" in cat.lower() or "bopca" in cat.lower()) else (min(10, level) if not is_boss else min(40, 10 + f_num))
    hb_slots = max(1, _to_int(raw_sb.get("hb_slots", default_slots), default_slots))
    hb_slot_value = max(1, _to_int(raw_sb.get("hb_slot_value", mods["CON"]), mods["CON"]))
    hb_damaged = max(0, min(hb_slots, _to_int(raw_sb.get("hb_damaged_slots", 0), 0)))

    evade_buffs = _to_int(raw_sb.get("evade_buffs", 0), 0)
    evade_dc = 10 + mods["DEX"] + f_num + evade_buffs
    default_dr = (f_num * 2) if "boss" in cat.lower() else f_num
    dr = max(0, _to_int(raw_sb.get("dr", default_dr), default_dr))

    atk_stat = str(raw_sb.get("primary_attack_stat", "STR")).upper()
    if atk_stat not in mods:
        atk_stat = "STR"
    attack_target_dc = 10 + mods[atk_stat] + f_num

    raw_actions = raw_sb.get("actions") if isinstance(raw_sb.get("actions"), list) else []
    actions = []
    for act in raw_actions[:6]:
        if isinstance(act, dict) and str(act.get("name", "")).strip():
            astat = str(act.get("stat", atk_stat)).upper()
            if astat not in mods:
                astat = atk_stat
            actions.append({
                "name": str(act.get("name", "")).strip(),
                "target_dc": _to_int(act.get("target_dc", 10 + mods[astat] + f_num), 10 + mods[astat] + f_num),
                "damage": str(act.get("damage", f"1d6{fmt_mod(mods[astat])}")).strip(),
                "effects": str(act.get("effects", "")).strip(),
            })
    if not actions:
        actions.append({
            "name": "Basic Attack",
            "target_dc": attack_target_dc,
            "damage": f"1d6{fmt_mod(mods[atk_stat])}",
            "effects": "Crawler rolls Evade vs Target DC",
        })

    action_economy = "1 Action per active Crawler per round" if is_boss else "1 Move + 1 Standard Action"

    return {
        "floor_number": f_num,
        "stats": stats,
        "mods": mods,
        "hb_slots": hb_slots,
        "hb_slot_value": hb_slot_value,
        "hb_damaged_slots": hb_damaged,
        "evade_buffs": evade_buffs,
        "evade_dc": evade_dc,
        "attack_target_dc": attack_target_dc,
        "dr": dr,
        "unopposed_dc": 10 + (2 * f_num),
        "stat_check_dc": 10 + f_num,
        "action_economy": action_economy,
        "ai_favor": _to_int(raw_sb.get("ai_favor", 0), 0),
        "actions": actions,
    }


def roll_loot_box(floor_number: int = 1, tier: str = "Bronze", reason: str = "") -> Dict[str, Any]:
    t = tier if tier in LOOT_TABLES else "Bronze"
    items = LOOT_TABLES[t]
    picked = random.choice(items)
    title_pool = [
        "QUESTIONABLE LIFE CHOICES",
        "CROWD PLEASER",
        "UNSANCTIONED VIOLENCE",
        "SPONSOR BAIT",
        "FLOOR SURVIVOR",
    ]
    title = random.choice(title_pool)
    quip = reason.strip() or "Congratulations, Crawler. You didn't die in the most boring way possible."
    announcement = (
        f"[NEW ACHIEVEMENT UNLOCKED!]\n"
        f"Title: {title}\n"
        f"Description: {quip}\n"
        f"Reward: You have received a {t} Loot Box (Floor {floor_number}).\n"
        f"Contents: {picked}"
    )
    return {
        "tier": t,
        "floor_number": floor_number,
        "title": title,
        "item": picked,
        "announcement": announcement,
    }


def build_ingest_markdown_prompt(filename: str, chunk_text: str) -> str:
    return f"""You are a Dungeon Crawler Carl (DCC) RPG campaign parser.
Extract structured campaign entities from the Markdown excerpt below (`{filename}`).
Respond ONLY with valid JSON inside ```json ... ``` matching this exact schema:
{{
  "macro_hubs": [
    {{
      "floor_number": 3,
      "name": "Floor 3: Over City — Heavensworth",
      "hub_type": "Floor",
      "collapse_timer_hours": 240,
      "controlling_faction": "Borant / Sponsors",
      "boss_name": "",
      "summary_md": "Brief floor/neighborhood overview"
    }}
  ],
  "micro_nodes": [
    {{
      "hub_name": "Floor 3: Over City — Heavensworth",
      "name": "The One-Eyed Narwhal",
      "node_type": "Saferoom",
      "minimap_marker": "White Dot",
      "description_md": "Safe haven tavern with vending stalls",
      "environmental_hazards": "None inside Safe Room",
      "projector_map_prompt": "Top-down VTT battlemap, cozy neon-lit dungeon saferoom tavern, wooden tables, glowing vending machines, 8k"
    }}
  ],
  "session_beats": [
    {{
      "node_name": "The One-Eyed Narwhal",
      "sequence_order": 1,
      "beat_type": "Social",
      "title": "Meet the Bopca Broker",
      "ai_announcement_md": "[SYSTEM NOTICE] Welcome to the Saferoom, Crawlers.",
      "gm_notes_md": "Bopca offers floor map intel for 200 gold.",
      "loot_reward_tier": "Bronze"
    }}
  ],
  "entities": [
    {{
      "node_name": "The One-Eyed Narwhal",
      "name": "Zev-7",
      "entity_category": "Bopca/Merchant",
      "race_or_type": "Bopca",
      "class_or_role": "Info Broker",
      "level": 3,
      "disposition": "Neutral",
      "stats": {{"STR": 3, "INT": 6, "CON": 4, "DEX": 4, "CHA": 5}},
      "personality": "Twitchy, fast-talking",
      "catchphrase": "Credits first, survival second!",
      "quest_hook": "Needs goblin ears from the subway.",
      "hotlist": ["Smoke Bomb", "Healing Potion"]
    }}
  ]
}}

MARKDOWN EXCERPT:
{chunk_text}
"""


def build_populate_node_prompt(
    hub: Dict[str, Any],
    node: Dict[str, Any],
    count: int = 2,
    category_mix: str = "1 Merchant/NPC + 1 Rival GMC or Mob",
    hint: str = "",
) -> str:
    f_num = hub.get("floor_number", 1)
    return f"""You are the Dungeon Crawler Carl (DCC) RPG System AI generating persistent NPCs/Mobs for a live tabletop session.
Parent Hub: {hub.get('name')} (Floor {f_num}, F={f_num})
Micro Node: {node.get('name')} ({node.get('node_type')}, Marker: {node.get('minimap_marker')})
Node Description: {node.get('description_md', '')}
Generate {count} distinct entities matching: {category_mix}.
Additional GM Hint: {hint or 'Make them memorable, darkly comedic, and ready for immediate table play.'}

Respond ONLY with valid JSON inside ```json ... ```:
{{
  "entities": [
    {{
      "name": "Character or Mob Name",
      "entity_category": "GMC Crawler | Elite | Non-Hostile NPC | Bopca/Merchant | Mob | Neighborhood Boss",
      "race_or_type": "Human | Goblin | Bopca | Cat-Person | etc.",
      "class_or_role": "Class or Role",
      "level": {max(1, f_num)},
      "crawler_skulls": 0,
      "boss_stars": 0,
      "sponsor_or_deity": "",
      "disposition": "Friendly | Neutral | Suspicious | Hostile",
      "stats": {{"STR": 4, "INT": 4, "CON": 4, "DEX": 4, "CHA": 4}},
      "personality": "Short vivid personality",
      "catchphrase": "Signature line",
      "quest_hook": "Immediate hook or secret",
      "hotlist": ["Item 1", "Item 2"],
      "actions": [
        {{"name": "Signature Attack", "stat": "STR", "damage": "1d6+2", "effects": "Evade"}}
      ]
    }}
  ]
}}
"""
