import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf as fitz
import app_paths

BASE_DIR = app_paths.DATA_DIR
RULES_DIR = BASE_DIR / "Rules"
INDEX_DB_PATH = BASE_DIR / "rules_index.db"

SYSTEM_FOLDERS = {
    "dcc": RULES_DIR / "DCC TTRPG",
    "dnd5e": RULES_DIR / "DnD 5e",
    "sw5e": RULES_DIR / "SW5e",
}

SYSTEM_LABELS = {
    "dcc": "Dungeon Crawler Carl TTRPG (DCC)",
    "dnd5e": "Dungeons & Dragons 5e (D&D 5e)",
    "sw5e": "Star Wars 5e (SW5e)",
}

SYSTEM_GUIDES = {
    "dcc": app_paths.get_resource_path("dcc_assets/templates/dcc_system_guide.md"),
    "sw5e": app_paths.get_resource_path("sw5e_assets/templates/sw5e_system_guide.md"),
    "dnd5e": app_paths.get_resource_path("dnd5e_assets/templates/dnd5e_system_guide.md"),
}

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "do", "does",
    "for", "from", "how", "i", "if", "in", "into", "is", "it", "its", "me", "my",
    "of", "on", "or", "our", "out", "should", "so", "that", "the", "their", "them",
    "then", "there", "these", "they", "this", "to", "us", "was", "we", "were",
    "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
}

_INDEX_LOCK = threading.Lock()
_INDEX_STATE: Dict[str, Any] = {
    "indexing": False,
    "current_book": "",
    "progress": "",
    "last_error": "",
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(INDEX_DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS indexed_files (
            path TEXT PRIMARY KEY,
            system TEXT NOT NULL,
            book TEXT NOT NULL,
            mtime REAL NOT NULL,
            size INTEGER NOT NULL,
            page_count INTEGER NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS rules_fts USING fts5(
            system UNINDEXED,
            book UNINDEXED,
            page UNINDEXED,
            content,
            tokenize='porter unicode61'
        );
        """
    )
    conn.commit()
    return conn


def get_index_status() -> Dict[str, Any]:
    counts = {"dcc": 0, "dnd5e": 0, "sw5e": 0}
    books = {"dcc": [], "dnd5e": [], "sw5e": []}
    if INDEX_DB_PATH.exists():
        try:
            conn = _get_conn()
            for sys_key, book, pages in conn.execute(
                "SELECT system, book, page_count FROM indexed_files ORDER BY system, book"
            ):
                if sys_key in counts:
                    counts[sys_key] += int(pages or 0)
                    books[sys_key].append({"book": book, "pages": int(pages or 0)})
            conn.close()
        except Exception as e:
            _INDEX_STATE["last_error"] = str(e)
    return {
        **_INDEX_STATE,
        "indexed_pages": counts,
        "books": books,
    }


def _extract_pdf_pages(pdf_path: Path) -> List[tuple]:
    doc = fitz.open(str(pdf_path))
    rows = []
    try:
        for i in range(len(doc)):
            txt = doc[i].get_text("text") or ""
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                rows.append((i + 1, txt))
    finally:
        doc.close()
    return rows


def index_all_rules(force: bool = False, log_fn=None) -> Dict[str, Any]:
    if not _INDEX_LOCK.acquire(blocking=False):
        return {"ok": False, "message": "Indexing already in progress."}

    _INDEX_STATE["indexing"] = True
    _INDEX_STATE["last_error"] = ""
    indexed_now = 0
    try:
        conn = _get_conn()
        if force:
            conn.execute("DELETE FROM indexed_files;")
            conn.execute("DELETE FROM rules_fts;")
            conn.commit()

        existing = {
            row[0]: (row[1], row[2])
            for row in conn.execute("SELECT path, mtime, size FROM indexed_files").fetchall()
        }

        all_targets = []
        for sys_key, folder in SYSTEM_FOLDERS.items():
            if folder.exists():
                for p in sorted(folder.rglob("*.pdf")):
                    all_targets.append((sys_key, p))

        total_files = len(all_targets)
        for idx, (sys_key, pdf_path) in enumerate(all_targets, start=1):
            st = pdf_path.stat()
            p_str = str(pdf_path)
            if not force and p_str in existing:
                old_mtime, old_size = existing[p_str]
                if abs(old_mtime - st.st_mtime) < 1.0 and old_size == st.st_size:
                    continue

            book_name = pdf_path.stem
            _INDEX_STATE["current_book"] = book_name
            _INDEX_STATE["progress"] = f"{idx}/{total_files}: {book_name}"
            if log_fn:
                log_fn(f"[RulesRAG] Indexing [{sys_key.upper()}] {book_name}...")

            # Remove stale rows for this book if re-indexing
            conn.execute("DELETE FROM rules_fts WHERE system=? AND book=?;", (sys_key, book_name))
            conn.execute("DELETE FROM indexed_files WHERE path=?;", (p_str,))

            pages = _extract_pdf_pages(pdf_path)
            if pages:
                conn.executemany(
                    "INSERT INTO rules_fts(system, book, page, content) VALUES (?, ?, ?, ?);",
                    [(sys_key, book_name, pno, txt) for pno, txt in pages],
                )
            conn.execute(
                "INSERT INTO indexed_files(path, system, book, mtime, size, page_count) VALUES (?, ?, ?, ?, ?, ?);",
                (p_str, sys_key, book_name, st.st_mtime, st.st_size, len(pages)),
            )
            conn.commit()
            indexed_now += 1
            if log_fn:
                log_fn(f"[RulesRAG] Indexed {book_name} ({len(pages)} text pages).")

        conn.close()
        _INDEX_STATE["current_book"] = ""
        _INDEX_STATE["progress"] = "Ready"
        return {"ok": True, "indexed_files": indexed_now, "status": get_index_status()}
    except Exception as e:
        _INDEX_STATE["last_error"] = str(e)
        if log_fn:
            log_fn(f"[RulesRAG Error] {e}")
        return {"ok": False, "error": str(e)}
    finally:
        _INDEX_STATE["indexing"] = False
        _INDEX_LOCK.release()


def start_background_indexing(force: bool = False, log_fn=None) -> bool:
    if _INDEX_STATE["indexing"]:
        return False
    threading.Thread(target=index_all_rules, args=(force, log_fn), daemon=True).start()
    return True


def _build_fts_query(query: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9]+", (query or "").lower())
    keywords = [t for t in tokens if len(t) >= 2 and t not in STOP_WORDS]
    if not keywords:
        keywords = tokens[:6]
    if not keywords:
        return ""
    # Combine unique keywords with OR so BM25 ranks pages matching more terms highest
    seen = []
    for k in keywords:
        if k not in seen:
            seen.append(k)
        if len(seen) >= 12:
            break
    return " OR ".join(f'"{k}"' for k in seen)


def search_rules(system: str, query: str, top_k: int = 6) -> List[Dict[str, Any]]:
    sys_key = system if system in SYSTEM_FOLDERS else "dnd5e"
    fts_q = _build_fts_query(query)
    if not fts_q or not INDEX_DB_PATH.exists():
        return []

    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT book, page, snippet(rules_fts, 3, '【', '】', ' ... ', 48) AS snip,
                   substr(content, 1, 1400) AS body,
                   bm25(rules_fts) AS rank
            FROM rules_fts
            WHERE rules_fts MATCH ? AND system = ?
            ORDER BY rank
            LIMIT ?;
            """,
            (fts_q, sys_key, int(top_k)),
        ).fetchall()
        results = []
        for book, page, snip, body, rank in rows:
            results.append({
                "book": book,
                "page": int(page),
                "snippet": snip,
                "excerpt": body,
                "score": round(float(rank), 3),
            })
        return results
    except Exception:
        return []
    finally:
        conn.close()


def build_dm_system_prompt(system: str, user_query: str, top_k: int = 6) -> tuple:
    sys_key = system if system in SYSTEM_FOLDERS else "dnd5e"
    label = SYSTEM_LABELS.get(sys_key, sys_key)
    hits = search_rules(sys_key, user_query, top_k=top_k)

    guide_block = ""
    guide_path = SYSTEM_GUIDES.get(sys_key)
    if guide_path and guide_path.exists():
        try:
            guide_text = guide_path.read_text(encoding="utf-8").strip()
            guide_block = f"\n\nSYSTEM GUIDE & PERSONA DIRECTIVES ({label}):\n{guide_text}\n"
        except Exception:
            pass

    if hits:
        ref_blocks = []
        for h in hits:
            ref_blocks.append(f"[{h['book']} — Page {h['page']}]\n{h['excerpt']}")
        refs_text = "\n\n---\n\n".join(ref_blocks)
    else:
        refs_text = (
            "(No indexed rulebook excerpts matched yet. If indexing is still running or hasn't run, "
            "answer using standard rules and note that the local rulebook index did not return a match.)"
        )

    prompt = f"""You are an expert Tabletop RPG Dungeon Master / Game Master Companion running a live **{label}** session.
Your job is to help the DM run the table smoothly: adjudicate rules accurately, look up stats/mechanics, suggest encounters, NPCs, loot, DCs, or pacing, and keep answers concise and table-ready.

STRICT GROUNDING RULES:
1. Follow the System Guide & Persona Directives below (if provided) AND prioritize the retrieved **{label}** rulebook excerpts from `C:\\AI_Workspace\\Rules\\`.
2. Whenever you cite a rule, mechanic, table, or stat from the rulebook excerpts, include the exact citation in parentheses, e.g. `(CarlRPG_Core_Rulebook_Digital_Low-Res_081226, p. 142)`.
3. If the retrieved excerpts do not cover a specific edge case, state clearly what is from the System Guide / Core Rulebook vs. what is an improvised ruling.
{guide_block}
RETRIEVED RULEBOOK EXCERPTS ({label}):
{refs_text}
"""
    return prompt, hits
