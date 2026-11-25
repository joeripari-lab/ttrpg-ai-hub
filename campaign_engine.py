import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import app_paths
import campaign_dcc
import campaign_rulesets

BASE_DIR = app_paths.DATA_DIR
CAMPAIGN_DB_PATH = BASE_DIR / "campaign_ops.db"
VAULT_DIR = BASE_DIR / "campaign_vault"
VAULT_SOURCE_DIR = VAULT_DIR / "source_docs"
VAULT_FLOORS_DIR = VAULT_DIR / "floors"
VAULT_NPCS_DIR = VAULT_DIR / "npcs"
VAULT_SESSIONS_DIR = VAULT_DIR / "sessions"

for _d in [VAULT_DIR, VAULT_SOURCE_DIR, VAULT_FLOORS_DIR, VAULT_NPCS_DIR, VAULT_SESSIONS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


def _slugify(text: str, prefix: str = "item") -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (text or "").strip()).strip("_").lower()
    return s or f"{prefix}_{uuid.uuid4().hex[:6]}"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(CAMPAIGN_DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS macro_hubs (
            id TEXT PRIMARY KEY,
            campaign_system TEXT NOT NULL DEFAULT 'dcc',
            floor_number INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL,
            hub_type TEXT NOT NULL DEFAULT 'Floor',
            collapse_timer_hours INTEGER NOT NULL DEFAULT 240,
            controlling_faction TEXT DEFAULT '',
            boss_name TEXT DEFAULT '',
            summary_md TEXT DEFAULT '',
            source_file TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS micro_nodes (
            id TEXT PRIMARY KEY,
            hub_id TEXT NOT NULL REFERENCES macro_hubs(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            node_type TEXT NOT NULL DEFAULT 'Encounter Zone',
            minimap_marker TEXT NOT NULL DEFAULT 'White Dot',
            description_md TEXT DEFAULT '',
            environmental_hazards TEXT DEFAULT '',
            projector_map_prompt TEXT DEFAULT '',
            is_populated INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS session_beats (
            id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL REFERENCES micro_nodes(id) ON DELETE CASCADE,
            session_number INTEGER,
            sequence_order INTEGER NOT NULL DEFAULT 1,
            beat_type TEXT NOT NULL DEFAULT 'Exploration',
            title TEXT NOT NULL,
            ai_announcement_md TEXT DEFAULT '',
            gm_notes_md TEXT DEFAULT '',
            loot_reward_tier TEXT DEFAULT 'Bronze',
            status TEXT NOT NULL DEFAULT 'Unplayed',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            entity_category TEXT NOT NULL DEFAULT 'Mob',
            race_or_type TEXT DEFAULT 'Human',
            class_or_role TEXT DEFAULT '',
            level INTEGER NOT NULL DEFAULT 1,
            crawler_skulls INTEGER NOT NULL DEFAULT 0,
            boss_stars INTEGER NOT NULL DEFAULT 0,
            sponsor_or_deity TEXT DEFAULT '',
            home_node_id TEXT REFERENCES micro_nodes(id) ON DELETE SET NULL,
            current_node_id TEXT REFERENCES micro_nodes(id) ON DELETE SET NULL,
            beat_id TEXT REFERENCES session_beats(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'Alive',
            disposition TEXT NOT NULL DEFAULT 'Neutral',
            character_sheet_json TEXT NOT NULL DEFAULT '{}',
            stat_block_json TEXT NOT NULL DEFAULT '{}',
            markdown_path TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()}
        if "beat_id" not in cols:
            conn.execute("ALTER TABLE entities ADD COLUMN beat_id TEXT REFERENCES session_beats(id) ON DELETE SET NULL")
            conn.commit()
    except Exception:
        pass
    return conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_entity(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["character_sheet"] = json.loads(d.get("character_sheet_json") or "{}")
    except Exception:
        d["character_sheet"] = {}
    try:
        d["stat_block"] = json.loads(d.get("stat_block_json") or "{}")
    except Exception:
        d["stat_block"] = {}
    return d


# ============================================================================
# TREE & CRUD
# ============================================================================
def get_campaign_tree(system: str = "") -> Dict[str, Any]:
    conn = _get_conn()
    try:
        if system in ("dcc", "dnd5e", "sw5e"):
            hubs = [dict(r) for r in conn.execute(
                "SELECT * FROM macro_hubs WHERE campaign_system=? ORDER BY floor_number ASC, name ASC", (system,)
            ).fetchall()]
            hub_ids = [h["id"] for h in hubs]
            if hub_ids:
                qm = ",".join("?" for _ in hub_ids)
                nodes = [dict(r) for r in conn.execute(f"SELECT * FROM micro_nodes WHERE hub_id IN ({qm}) ORDER BY name ASC", hub_ids).fetchall()]
            else:
                nodes = []
            node_ids = [n["id"] for n in nodes]
            if node_ids:
                qn = ",".join("?" for _ in node_ids)
                beats = [dict(r) for r in conn.execute(f"SELECT * FROM session_beats WHERE node_id IN ({qn}) ORDER BY sequence_order ASC, title ASC", node_ids).fetchall()]
                entities = [_row_to_entity(r) for r in conn.execute(f"SELECT * FROM entities WHERE current_node_id IN ({qn}) ORDER BY name ASC", node_ids).fetchall()]
            else:
                beats, entities = [], []
        else:
            hubs = [dict(r) for r in conn.execute("SELECT * FROM macro_hubs ORDER BY floor_number ASC, name ASC").fetchall()]
            nodes = [dict(r) for r in conn.execute("SELECT * FROM micro_nodes ORDER BY name ASC").fetchall()]
            beats = [dict(r) for r in conn.execute("SELECT * FROM session_beats ORDER BY sequence_order ASC, title ASC").fetchall()]
            entities = [_row_to_entity(r) for r in conn.execute("SELECT * FROM entities ORDER BY name ASC").fetchall()]
        source_files = sorted([p.name for p in VAULT_SOURCE_DIR.glob("*.md")])
        return {
            "system": system or "all",
            "hubs": hubs,
            "nodes": nodes,
            "beats": beats,
            "entities": entities,
            "source_files": source_files,
        }
    finally:
        conn.close()


def upsert_hub(data: Dict[str, Any]) -> Dict[str, Any]:
    conn = _get_conn()
    try:
        hid = data.get("id") or _slugify(data.get("name") or "floor", "hub")
        now = _now()
        conn.execute(
            """
            INSERT INTO macro_hubs (id, campaign_system, floor_number, name, hub_type, collapse_timer_hours, controlling_faction, boss_name, summary_md, source_file, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                campaign_system=excluded.campaign_system,
                floor_number=excluded.floor_number,
                name=excluded.name,
                hub_type=excluded.hub_type,
                collapse_timer_hours=excluded.collapse_timer_hours,
                controlling_faction=excluded.controlling_faction,
                boss_name=excluded.boss_name,
                summary_md=excluded.summary_md,
                source_file=excluded.source_file,
                updated_at=excluded.updated_at
            """,
            (
                hid,
                data.get("campaign_system", "dcc"),
                int(data.get("floor_number", 1) or 1),
                data.get("name", "Unnamed Floor"),
                data.get("hub_type", "Floor"),
                int(data.get("collapse_timer_hours", 240) or 240),
                data.get("controlling_faction", ""),
                data.get("boss_name", ""),
                data.get("summary_md", ""),
                data.get("source_file", ""),
                now,
            ),
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM macro_hubs WHERE id=?", (hid,)).fetchone())
    finally:
        conn.close()
    sync_hub_to_vault(row["id"])
    return row


def upsert_node(data: Dict[str, Any]) -> Dict[str, Any]:
    conn = _get_conn()
    try:
        nid = data.get("id") or _slugify(f"{data.get('hub_id','')}_{data.get('name','')}", "node")
        now = _now()
        conn.execute(
            """
            INSERT INTO micro_nodes (id, hub_id, name, node_type, minimap_marker, description_md, environmental_hazards, projector_map_prompt, is_populated, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                hub_id=excluded.hub_id,
                name=excluded.name,
                node_type=excluded.node_type,
                minimap_marker=excluded.minimap_marker,
                description_md=excluded.description_md,
                environmental_hazards=excluded.environmental_hazards,
                projector_map_prompt=excluded.projector_map_prompt,
                is_populated=excluded.is_populated,
                updated_at=excluded.updated_at
            """,
            (
                nid,
                data["hub_id"],
                data.get("name", "Unnamed Node"),
                data.get("node_type", "Encounter Zone"),
                data.get("minimap_marker", "White Dot"),
                data.get("description_md", ""),
                data.get("environmental_hazards", ""),
                data.get("projector_map_prompt", ""),
                1 if data.get("is_populated") else 0,
                now,
            ),
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM micro_nodes WHERE id=?", (nid,)).fetchone())
    finally:
        conn.close()
    sync_hub_to_vault(row["hub_id"])
    return row


def upsert_beat(data: Dict[str, Any]) -> Dict[str, Any]:
    conn = _get_conn()
    try:
        bid = data.get("id") or _slugify(f"{data.get('node_id','')}_{data.get('title','')}", "beat")
        now = _now()
        conn.execute(
            """
            INSERT INTO session_beats (id, node_id, session_number, sequence_order, beat_type, title, ai_announcement_md, gm_notes_md, loot_reward_tier, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                node_id=excluded.node_id,
                session_number=excluded.session_number,
                sequence_order=excluded.sequence_order,
                beat_type=excluded.beat_type,
                title=excluded.title,
                ai_announcement_md=excluded.ai_announcement_md,
                gm_notes_md=excluded.gm_notes_md,
                loot_reward_tier=excluded.loot_reward_tier,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                bid,
                data["node_id"],
                data.get("session_number"),
                int(data.get("sequence_order", 1) or 1),
                data.get("beat_type", "Exploration"),
                data.get("title", "Session Beat"),
                data.get("ai_announcement_md", ""),
                data.get("gm_notes_md", ""),
                data.get("loot_reward_tier", "Bronze"),
                data.get("status", "Unplayed"),
                now,
            ),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM session_beats WHERE id=?", (bid,)).fetchone())
    finally:
        conn.close()


def _get_system_and_floor_for_node(conn: sqlite3.Connection, node_id: Optional[str]) -> tuple:
    if not node_id:
        return ("dcc", 1)
    row = conn.execute(
        "SELECT h.campaign_system, h.floor_number FROM micro_nodes n JOIN macro_hubs h ON n.hub_id = h.id WHERE n.id=?",
        (node_id,),
    ).fetchone()
    return (row["campaign_system"] or "dcc", int(row["floor_number"])) if row else ("dcc", 1)


def upsert_entity(data: Dict[str, Any], append_note: str = "") -> Dict[str, Any]:
    conn = _get_conn()
    try:
        eid = data.get("id") or _slugify(data.get("name") or "npc", "ent")
        cur_node = data.get("current_node_id") or data.get("home_node_id")
        home_node = data.get("home_node_id") or cur_node
        beat_id = data.get("beat_id") or None
        sys_key, f_num = _get_system_and_floor_for_node(conn, cur_node)
        if data.get("campaign_system") in ("dcc", "dnd5e", "sw5e"):
            sys_key = data["campaign_system"]

        if sys_key == "dnd5e":
            stat_block = campaign_rulesets.calculate_dnd5e_entity(data, tier_level=f_num)
        elif sys_key == "sw5e":
            stat_block = campaign_rulesets.calculate_sw5e_entity(data, tier_level=f_num)
        else:
            stat_block = campaign_dcc.calculate_dcc_entity(data, floor_number=f_num)
        char_sheet = data.get("character_sheet") if isinstance(data.get("character_sheet"), dict) else {}
        for k in ["personality", "catchphrase", "quest_hook", "hotlist", "notes"]:
            if k in data and data[k] is not None:
                char_sheet[k] = data[k]
        if append_note:
            prev = char_sheet.get("notes", "")
            char_sheet["notes"] = f"{prev}\n[{_now()}] {append_note}".strip()

        md_path = str(VAULT_NPCS_DIR / f"{eid}.md")
        now = _now()
        conn.execute(
            """
            INSERT INTO entities (id, name, entity_category, race_or_type, class_or_role, level, crawler_skulls, boss_stars, sponsor_or_deity, home_node_id, current_node_id, beat_id, status, disposition, character_sheet_json, stat_block_json, markdown_path, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                entity_category=excluded.entity_category,
                race_or_type=excluded.race_or_type,
                class_or_role=excluded.class_or_role,
                level=excluded.level,
                crawler_skulls=excluded.crawler_skulls,
                boss_stars=excluded.boss_stars,
                sponsor_or_deity=excluded.sponsor_or_deity,
                home_node_id=excluded.home_node_id,
                current_node_id=excluded.current_node_id,
                beat_id=excluded.beat_id,
                status=excluded.status,
                disposition=excluded.disposition,
                character_sheet_json=excluded.character_sheet_json,
                stat_block_json=excluded.stat_block_json,
                markdown_path=excluded.markdown_path,
                updated_at=excluded.updated_at
            """,
            (
                eid,
                data.get("name", "Unnamed Entity"),
                data.get("entity_category", "Mob"),
                data.get("race_or_type", "Human"),
                data.get("class_or_role", ""),
                int(data.get("level", 1) or 1),
                int(data.get("crawler_skulls", 0) or 0),
                int(data.get("boss_stars", 0) or 0),
                data.get("sponsor_or_deity", ""),
                home_node,
                cur_node,
                beat_id,
                data.get("status", "Alive"),
                data.get("disposition", "Neutral"),
                json.dumps(char_sheet),
                json.dumps(stat_block),
                md_path,
                now,
            ),
        )
        conn.commit()
        row = _row_to_entity(conn.execute("SELECT * FROM entities WHERE id=?", (eid,)).fetchone())
    finally:
        conn.close()
    sync_entity_to_vault(row["id"])
    return row


def update_entity_live(entity_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
        if not row:
            return None
        ent = _row_to_entity(row)
        note = ""
        if "hb_damaged_slots" in updates:
            sb = ent["stat_block"]
            sb["hb_damaged_slots"] = max(0, min(int(sb.get("hb_slots", 10)), int(updates["hb_damaged_slots"])))
            ent["stat_block"] = sb
        if "hp_delta" in updates:
            sb = ent["stat_block"]
            hp_max = int(sb.get("hp_max", 10))
            hp_cur = int(sb.get("hp_current", hp_max)) + int(updates["hp_delta"])
            sb["hp_current"] = max(0, min(hp_max, hp_cur))
            ent["stat_block"] = sb
        if "hp_current" in updates:
            sb = ent["stat_block"]
            sb["hp_current"] = max(0, min(int(sb.get("hp_max", 10)), int(updates["hp_current"])))
            ent["stat_block"] = sb
        if "current_node_id" in updates and updates["current_node_id"] != ent.get("current_node_id"):
            ent["current_node_id"] = updates["current_node_id"]
            if "beat_id" not in updates:
                ent["beat_id"] = None
            note = f"Moved to node `{updates['current_node_id']}`"
        if "beat_id" in updates:
            ent["beat_id"] = updates["beat_id"] or None
        for k in ["status", "disposition", "crawler_skulls", "boss_stars"]:
            if k in updates:
                if k == "status" and updates[k] != ent.get("status"):
                    note = (note + f"; Status -> {updates[k]}").strip("; ")
                ent[k] = updates[k]
    finally:
        conn.close()
    return upsert_entity(ent, append_note=note)


def delete_item(table: str, item_id: str) -> bool:
    if table not in {"macro_hubs", "micro_nodes", "session_beats", "entities"}:
        return False
    conn = _get_conn()
    try:
        cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============================================================================
# VAULT MARKDOWN TWO-WAY SYNC
# ============================================================================
def sync_hub_to_vault(hub_id: str) -> Optional[str]:
    conn = _get_conn()
    try:
        hub = conn.execute("SELECT * FROM macro_hubs WHERE id=?", (hub_id,)).fetchone()
        if not hub:
            return None
        hub_d = dict(hub)
        nodes = [dict(r) for r in conn.execute("SELECT * FROM micro_nodes WHERE hub_id=? ORDER BY name", (hub_id,)).fetchall()]
        lines = [
            f"# {hub_d['name']} (Floor {hub_d['floor_number']})",
            f"- **Type:** {hub_d['hub_type']} | **Collapse Timer:** {hub_d['collapse_timer_hours']} hrs",
            f"- **Controlling Faction:** {hub_d['controlling_faction'] or 'None'} | **Boss:** {hub_d['boss_name'] or 'TBD'}",
            "",
            hub_d.get("summary_md", ""),
            "",
            "## Micro Nodes",
        ]
        for n in nodes:
            lines.append(f"### {n['name']} [{n['node_type']} | {n['minimap_marker']}]")
            if n.get("description_md"):
                lines.append(n["description_md"])
            if n.get("environmental_hazards"):
                lines.append(f"- **Hazards:** {n['environmental_hazards']}")
            lines.append("")
        out_path = VAULT_FLOORS_DIR / f"{hub_d['id']}.md"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return str(out_path)
    finally:
        conn.close()


def sync_entity_to_vault(entity_id: str) -> Optional[str]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
        if not row:
            return None
        e = _row_to_entity(row)
        sb = e["stat_block"]
        cs = e["character_sheet"]
        st = sb.get("stats", {})
        md = sb.get("mods", {})
        if sb.get("system") in ("dnd5e", "sw5e"):
            lines = [
                f"# {e['name']} ({e['entity_category']} — {sb.get('system', '').upper()})",
                f"- **Race/Species:** {e['race_or_type']} | **Class/Role:** {e['class_or_role']} | **Level:** {e['level']} ({sb.get('cr', '')})",
                f"- **Status:** {e['status']} | **Disposition:** {e['disposition']} | **Current Node:** `{e.get('current_node_id') or 'Unassigned'}`",
                "",
                "## Stat Block",
                f"- **STR:** {st.get('STR', 10)} ({campaign_dcc.fmt_mod(md.get('STR', 0))}) | **DEX:** {st.get('DEX', 10)} ({campaign_dcc.fmt_mod(md.get('DEX', 0))}) | **CON:** {st.get('CON', 10)} ({campaign_dcc.fmt_mod(md.get('CON', 0))}) | **INT:** {st.get('INT', 10)} ({campaign_dcc.fmt_mod(md.get('INT', 0))}) | **WIS:** {st.get('WIS', 10)} ({campaign_dcc.fmt_mod(md.get('WIS', 0))}) | **CHA:** {st.get('CHA', 10)} ({campaign_dcc.fmt_mod(md.get('CHA', 0))})",
                f"- **AC:** {sb.get('ac', 12)} | **HP:** {sb.get('hp_current', 10)}/{sb.get('hp_max', 10)} | **Proficiency Bonus:** +{sb.get('prof_bonus', 2)}",
                "",
                "## Actions",
            ]
            for a in sb.get("actions", []):
                lines.append(f"- **{a['name']}:** Attack `{a.get('atk', '+0')}` | Damage `{a.get('damage', '')}` | {a.get('effects', '')}")
        else:
            lines = [
                f"# {e['name']} ({e['entity_category']})",
                f"- **Race/Type:** {e['race_or_type']} | **Class/Role:** {e['class_or_role']} | **Level:** {e['level']}",
                f"- **Status:** {e['status']} | **Disposition:** {e['disposition']} | **Skulls:** {e['crawler_skulls']} | **Boss Stars:** {e['boss_stars']}",
                f"- **Current Node:** `{e.get('current_node_id') or 'Unassigned'}` | **Floor (F):** {sb.get('floor_number', 1)}",
                "",
                "## DCC Stat Block",
                f"- **STR:** {st.get('STR', 3)} ({campaign_dcc.fmt_mod(md.get('STR', 2))}) | **INT:** {st.get('INT', 3)} ({campaign_dcc.fmt_mod(md.get('INT', 2))}) | **CON:** {st.get('CON', 3)} ({campaign_dcc.fmt_mod(md.get('CON', 2))}) | **DEX:** {st.get('DEX', 3)} ({campaign_dcc.fmt_mod(md.get('DEX', 2))}) | **CHA:** {st.get('CHA', 3)} ({campaign_dcc.fmt_mod(md.get('CHA', 2))})",
                f"- **Health Bar:** {sb.get('hb_slots', 10) - sb.get('hb_damaged_slots', 0)}/{sb.get('hb_slots', 10)} slots ({sb.get('hb_slot_value', 2)} HP/slot)",
                f"- **Evade DC:** {sb.get('evade_dc', 13)} | **DR:** {sb.get('dr', 1)} | **Economy:** {sb.get('action_economy', '')}",
                "",
                "## Actions",
            ]
            for a in sb.get("actions", []):
                lines.append(f"- **{a['name']}:** Target Evade DC `{a.get('target_dc', 13)}` | Damage `{a.get('damage', '')}` | {a.get('effects', '')}")
        if cs.get("personality") or cs.get("catchphrase") or cs.get("quest_hook"):
            lines.extend([
                "",
                "## Roleplay & Hooks",
                f"- **Personality:** {cs.get('personality', '')}",
                f"- **Catchphrase:** {cs.get('catchphrase', '')}",
                f"- **Hook:** {cs.get('quest_hook', '')}",
            ])
        if cs.get("notes"):
            lines.extend(["", "## Log", cs["notes"]])
        out_path = VAULT_NPCS_DIR / f"{e['id']}.md"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return str(out_path)
    finally:
        conn.close()


# ============================================================================
# MARKDOWN INGESTION, NODE POPULATION & RUNBOOK EXPORT
# ============================================================================
def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    for pat in [r"```json\s*([\s\S]*?)```", r"\{[\s\S]*\}"]:
        m = re.search(pat, text or "", re.IGNORECASE)
        if m:
            raw = m.group(1) if m.lastindex else m.group(0)
            try:
                obj = json.loads(raw.strip())
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
    return None


def _chunk_markdown(content: str, max_chars: int = 7500) -> List[str]:
    sections = re.split(r"(?m)^(?=#{1,2}\s+)", content or "")
    chunks = []
    buf = ""
    for sec in sections:
        if len(buf) + len(sec) > max_chars and buf.strip():
            chunks.append(buf.strip())
            buf = sec
        else:
            buf += "\n" + sec
    if buf.strip():
        chunks.append(buf.strip())
    return chunks or [content[:max_chars]]


def ingest_markdown(filename: str, content: str, llm_fn, system: str = "dcc") -> Dict[str, Any]:
    sys_key = system if system in ("dcc", "dnd5e", "sw5e") else "dcc"
    safe_name = os.path.basename(filename or f"campaign_{int(time.time())}.md")
    if not safe_name.lower().endswith(".md"):
        safe_name += ".md"
    (VAULT_SOURCE_DIR / safe_name).write_text(content, encoding="utf-8")

    chunks = _chunk_markdown(content)
    counts = {"hubs": 0, "nodes": 0, "beats": 0, "entities": 0}
    hub_name_to_id: Dict[str, str] = {}
    node_name_to_id: Dict[str, str] = {}

    for ch in chunks:
        prompt = (
            campaign_dcc.build_ingest_markdown_prompt(safe_name, ch)
            if sys_key == "dcc"
            else campaign_rulesets.build_ingest_prompt(sys_key, safe_name, ch)
        )
        reply = llm_fn([{"role": "system", "content": "Output valid JSON only."}, {"role": "user", "content": prompt}])
        parsed = _extract_json_block(reply)
        if not parsed:
            continue

        for h in parsed.get("macro_hubs") or []:
            if not isinstance(h, dict) or not h.get("name"):
                continue
            h["campaign_system"] = sys_key
            h["source_file"] = safe_name
            saved = upsert_hub(h)
            hub_name_to_id[saved["name"].lower()] = saved["id"]
            counts["hubs"] += 1

        default_hub_id = next(iter(hub_name_to_id.values()), None)
        if not default_hub_id:
            fallback = upsert_hub({"name": safe_name[:-3], "campaign_system": sys_key, "floor_number": 1, "source_file": safe_name})
            default_hub_id = fallback["id"]
            hub_name_to_id[fallback["name"].lower()] = default_hub_id
            counts["hubs"] += 1

        for n in parsed.get("micro_nodes") or []:
            if not isinstance(n, dict) or not n.get("name"):
                continue
            hname = str(n.get("hub_name", "")).lower()
            n["hub_id"] = hub_name_to_id.get(hname, default_hub_id)
            saved_n = upsert_node(n)
            node_name_to_id[saved_n["name"].lower()] = saved_n["id"]
            counts["nodes"] += 1

        default_node_id = next(iter(node_name_to_id.values()), None)
        for b in parsed.get("session_beats") or []:
            if not isinstance(b, dict) or not b.get("title"):
                continue
            nname = str(b.get("node_name", "")).lower()
            nid = node_name_to_id.get(nname, default_node_id)
            if not nid:
                continue
            b["node_id"] = nid
            upsert_beat(b)
            counts["beats"] += 1

        for e in parsed.get("entities") or []:
            if not isinstance(e, dict) or not e.get("name"):
                continue
            nname = str(e.get("node_name", "")).lower()
            nid = node_name_to_id.get(nname, default_node_id)
            e["home_node_id"] = nid
            e["current_node_id"] = nid
            e["campaign_system"] = sys_key
            upsert_entity(e)
            counts["entities"] += 1

    return {"ok": True, "file": safe_name, "counts": counts, "tree": get_campaign_tree(sys_key)}


def populate_node(node_id: str, count: int, category_mix: str, hint: str, llm_fn, beat_id: Optional[str] = None) -> Dict[str, Any]:
    conn = _get_conn()
    try:
        node = conn.execute("SELECT * FROM micro_nodes WHERE id=?", (node_id,)).fetchone()
        if not node:
            return {"ok": False, "error": "Node not found"}
        node_d = dict(node)
        hub = conn.execute("SELECT * FROM macro_hubs WHERE id=?", (node_d["hub_id"],)).fetchone()
        hub_d = dict(hub) if hub else {"name": "Hub 1", "floor_number": 1, "campaign_system": "dcc"}
    finally:
        conn.close()

    sys_key = hub_d.get("campaign_system") or "dcc"
    prompt = (
        campaign_dcc.build_populate_node_prompt(hub_d, node_d, count=count, category_mix=category_mix, hint=hint)
        if sys_key == "dcc"
        else campaign_rulesets.build_populate_prompt(sys_key, hub_d, node_d, count=count, category_mix=category_mix, hint=hint)
    )
    reply = llm_fn([{"role": "system", "content": "Output valid JSON only."}, {"role": "user", "content": prompt}])
    parsed = _extract_json_block(reply)
    if not parsed or not isinstance(parsed.get("entities"), list):
        return {"ok": False, "error": "LLM did not return valid entity JSON."}

    created = []
    for e in parsed["entities"]:
        if not isinstance(e, dict) or not e.get("name"):
            continue
        e["home_node_id"] = node_id
        e["current_node_id"] = node_id
        if beat_id:
            e["beat_id"] = beat_id
        e["campaign_system"] = sys_key
        created.append(upsert_entity(e))

    if created:
        node_d["is_populated"] = 1
        upsert_node(node_d)

    return {"ok": True, "created": created, "tree": get_campaign_tree(sys_key)}


def export_session_runbook(title: str, node_ids: List[str], beat_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    conn = _get_conn()
    try:
        nodes = []
        if node_ids:
            q_marks = ",".join("?" for _ in node_ids)
            nodes = [dict(r) for r in conn.execute(f"SELECT * FROM micro_nodes WHERE id IN ({q_marks})", node_ids).fetchall()]
        elif beat_ids:
            q_marks = ",".join("?" for _ in beat_ids)
            nodes = [
                dict(r)
                for r in conn.execute(
                    f"SELECT DISTINCT n.* FROM micro_nodes n JOIN session_beats b ON b.node_id = n.id WHERE b.id IN ({q_marks})",
                    beat_ids,
                ).fetchall()
            ]
        else:
            nodes = [dict(r) for r in conn.execute("SELECT * FROM micro_nodes ORDER BY name").fetchall()]

        lines = [f"# {title or 'DCC Session Runbook'}", f"*Generated: {_now()}*", ""]
        for n in nodes:
            hub = conn.execute("SELECT * FROM macro_hubs WHERE id=?", (n["hub_id"],)).fetchone()
            f_num = int(hub["floor_number"]) if hub else 1
            lines.extend([
                f"## {n['name']} ({n['node_type']} — Floor {f_num})",
                f"- **DC Quick Reference:** Stat Check `{10+f_num}` | Unopposed `{10+2*f_num}` | Marker: `{n['minimap_marker']}`",
                n.get("description_md", ""),
                "",
            ])
            beats = [dict(r) for r in conn.execute("SELECT * FROM session_beats WHERE node_id=? ORDER BY sequence_order", (n["id"],)).fetchall()]
            if beats:
                lines.append("### Session Beats")
                for b in beats:
                    lines.append(f"- **[{b['beat_type']}] {b['title']}** ({b['status']} | Loot: {b['loot_reward_tier']})")
                    if b.get("ai_announcement_md"):
                        lines.append(f"  > {b['ai_announcement_md']}")
                    if b.get("gm_notes_md"):
                        lines.append(f"  *GM:* {b['gm_notes_md']}")
                lines.append("")

            ents = [_row_to_entity(r) for r in conn.execute("SELECT * FROM entities WHERE current_node_id=? ORDER BY name", (n["id"],)).fetchall()]
            if ents:
                lines.append("### Present Entities")
                for e in ents:
                    sb = e["stat_block"]
                    lines.append(
                        f"- **{e['name']}** ({e['entity_category']}, Lv.{e['level']}, {e['status']}) — "
                        f"HB `{sb.get('hb_slots',10)-sb.get('hb_damaged_slots',0)}/{sb.get('hb_slots',10)}` ({sb.get('hb_slot_value',2)}/slot) | "
                        f"Evade DC `{sb.get('evade_dc',13)}` | DR `{sb.get('dr',1)}`"
                    )
                lines.append("")

        fname = f"{_slugify(title or 'session_runbook')}.md"
        out_path = VAULT_SESSIONS_DIR / fname
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return {"ok": True, "filename": fname, "path": str(out_path), "content": "\n".join(lines)}
    finally:
        conn.close()


def build_campaign_context_for_chat(query: str, limit: int = 6, system: str = "") -> str:
    if not CAMPAIGN_DB_PATH.exists():
        return ""
    tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", query or "") if len(t) >= 3]
    conn = _get_conn()
    try:
        if system in ("dcc", "dnd5e", "sw5e"):
            hubs = [dict(r) for r in conn.execute("SELECT * FROM macro_hubs WHERE campaign_system=? ORDER BY floor_number", (system,)).fetchall()]
        else:
            hubs = [dict(r) for r in conn.execute("SELECT * FROM macro_hubs ORDER BY floor_number").fetchall()]
        hub_ids = {h["id"] for h in hubs}
        nodes = [dict(r) for r in conn.execute("SELECT * FROM micro_nodes").fetchall() if r["hub_id"] in hub_ids]
        node_ids = {n["id"] for n in nodes}
        ents = [_row_to_entity(r) for r in conn.execute("SELECT * FROM entities").fetchall() if r["current_node_id"] in node_ids]
        if not hubs and not nodes and not ents:
            return ""

        node_map = {n["id"]: n for n in nodes}
        hub_map = {h["id"]: h for h in hubs}

        matched_ents = []
        for e in ents:
            n = node_map.get(e.get("current_node_id"), {})
            blob = f"{e['name']} {e['entity_category']} {e['race_or_type']} {n.get('name','')}".lower()
            if not tokens or any(t in blob for t in tokens):
                matched_ents.append((e, n))
        if not matched_ents:
            matched_ents = [(e, node_map.get(e.get("current_node_id"), {})) for e in ents[:limit]]

        lines = [f"LIVE CAMPAIGN STATE ({system or 'all'} — `campaign_ops.db`):"]
        for h in hubs[:4]:
            lines.append(f"- Hub: {h['name']} (Tier/Floor={h['floor_number']})")
        for e, n in matched_ents[:limit]:
            sb = e["stat_block"]
            h = hub_map.get(n.get("hub_id"), {})
            if sb.get("system") in ("dnd5e", "sw5e"):
                lines.append(
                    f"- Entity `{e['name']}` ({e['entity_category']}, {e['status']}) @ Node `{n.get('name','Unassigned')}`: "
                    f"AC {sb.get('ac')}, HP {sb.get('hp_current')}/{sb.get('hp_max')}, {sb.get('cr','')}"
                )
            else:
                lines.append(
                    f"- Entity `{e['name']}` ({e['entity_category']}, {e['status']}) @ Node `{n.get('name','Unassigned')}` "
                    f"(Floor {h.get('floor_number', sb.get('floor_number',1))}): "
                    f"Evade DC {sb.get('evade_dc')}, DR {sb.get('dr')}, "
                    f"HB {sb.get('hb_slots',10)-sb.get('hb_damaged_slots',0)}/{sb.get('hb_slots',10)} ({sb.get('hb_slot_value',2)}/slot)"
                )
        return "\n".join(lines)
    finally:
        conn.close()
