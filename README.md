# 🎲 TTRPG AI Studio & DM Hub

A standalone Windows desktop application (`pywebview` + local Python server) for Tabletop RPG Game Masters and players, supporting **Dungeon Crawl Classics (DCC)**, **Star Wars 5e (SW5e)**, and **D&D 5e** with **Local**, **Cloud**, or **Hybrid** AI compute.

---

## ✨ Core Features

- **🧙 First-Run Setup Wizard & 3 Compute Modes**
  - **🏠 Fully Local AI:** 100% offline via Ollama (e.g., `qwen2.5:7b`) + optional local ComfyUI (`SDXL` / `Img2Img` / `ReActor`).
  - **☁️ Fully Cloud AI:** No GPU required — uses **Google Gemini**, **OpenAI ChatGPT**, or **Anthropic Claude** (+ Cloud Image generation), and automatically hides local-only ComfyUI/VRAM UI controls.
  - **⚡ Hybrid Mode:** Cloud-first with Local fallback, or Local-first with Cloud fallback.
- **🎨 Image Studio**
  - **TTRPG Portrait Preset Builder:** Ruleset-aware Race/Species, Class, Art Style, and Backdrop dropdowns for D&D 5e, SW5e, and DCC.
  - **Studio Skills & Persistent Memory:** Save reusable style presets (`studio_skills/`) and correction rules (`learned_memory.json`).
- **💬 Agent Chat & Rulebook-Cited DM Companion**
  - Local SQLite FTS5 RAG (`rules_rag.py`) indexes your owned rulebook PDFs and grounds DM Companion answers with book/page citations.
  - Supports slash commands: `/dm`, `/dcc`, `/sw5e`, `/dnd5e`, `/skill`, and `/draw`.
- **📄 Fillable PDF Character & Ship Builders**
  - **DCC TTRPG:** Session 0 Character Sheet + 8-page Character Journal PDF (`dcc_engine.py`).
  - **SW5e:** Character Sheet + Starship Sheet PDF (`sw5e_engine.py`).
  - **D&D 5e:** 3-page Fillable Character Sheet + Spellcasting PDF (`dnd5e_engine.py`).
- **🗺️ Multi-System Campaign Organizer**
  - Two-way synced Markdown (`campaign_vault/`) + SQLite (`campaign_ops.db`) for Hubs, Nodes, Beats, Beat-to-Entity bindings (NPCs, monsters, loot), and Session Runbook export.
- **🔄 In-App GitHub Updater**
  - Check for new GitHub Releases and install updates in-place from **Models & Settings → App Updates** without losing your saved characters, rules, or settings.

---

## 📚 Rulebooks & Copyright Notice

No copyrighted rulebook PDFs are bundled in this repository or the installer.  
To unlock rulebook-cited DM Companion answers for a system, upload your own owned PDFs via the **Setup Wizard** or place them in your data folder under:

- `Rules/DCC TTRPG/`
- `Rules/DnD 5e/`
- `Rules/SW5e/`

---

## 🚀 Getting Started

### Option 1: Windows Desktop Installer (Recommended)
1. Download `TTRPG_AI_Hub_Setup.exe` from the [GitHub Releases](https://github.com/joeripari-lab/ttrpg-ai-hub/releases) page.
2. Run the installer (installs to `%LOCALAPPDATA%\Programs\TTRPG_AI_Hub` and creates Start Menu / Desktop shortcuts).
3. Launch **TTRPG AI Hub** and complete the First-Run Setup Wizard.
   - User data, rulebook indexes, campaign vaults, and outputs are stored in `%LOCALAPPDATA%\TTRPG_AI_Hub` (or `TTRPG_HUB_DATA_DIR` if set).

### Option 2: Run from Source (Development)
1. Create/activate your Python virtual environment (`venv`) and install dependencies (`pywebview`, `pymupdf`, etc.).
2. *(Optional)* Copy `config.example.json` to `config.json` (never commit `config.json` — it is `.gitignore`d).
3. Launch the native desktop window:
   ```powershell
   .\venv\Scripts\python.exe desktop_launcher.py
   ```

---

## 🛠️ Building & Publishing a Release

1. Bump `APP_VERSION` in `updater.py` and `AppVersion` in `installer.iss`.
2. Build the standalone PyInstaller bundle (`--onedir --windowed`) and compile `installer.iss` with Inno Setup 6 (`ISCC.exe`):
   ```powershell
   .\venv\Scripts\python.exe build_installer.py
   & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
   ```
3. Commit and tag the release (`vX.Y.Z`) on `main`, then attach `dist\TTRPG_AI_Hub_Setup.exe` to the GitHub Release so installed users can update in-app via **Models & Settings → App Updates**.

---

## 📁 Project Structure

| File / Folder | Purpose |
| :--- | :--- |
| `desktop_launcher.py` | Launches `hub_server` in a background thread and opens the native `pywebview` window |
| `hub_server.py` | Local HTTP API server and single-page web UI |
| `app_paths.py` | Portable bundle vs. user data directory resolution (`DATA_DIR`) |
| `llm_router.py` | Unified LLM & Cloud Image router (Ollama, LM Studio, Gemini, OpenAI, Anthropic) |
| `rules_rag.py` | PDF rulebook indexer and SQLite FTS5 retrieval for DM Companion |
| `updater.py` | In-app GitHub Releases updater + silent Inno Setup upgrade launcher |
| `dcc_engine.py`, `sw5e_engine.py`, `dnd5e_engine.py` | Rule calculations and fillable PDF exporters |
| `campaign_engine.py`, `campaign_dcc.py`, `campaign_rulesets.py` | Multi-system Campaign Organizer, beat-entity bindings, and vault sync |
| `dcc_assets/`, `sw5e_assets/`, `dnd5e_assets/`, `studio_skills/` | Fillable PDF templates, field maps, system guides, and Studio Skill presets |
| `build_installer.py`, `installer.iss` | PyInstaller and Inno Setup 6 build scripts |
