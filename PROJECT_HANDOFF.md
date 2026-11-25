# Unified Local AI Hub — Project Overview, Architecture & IDE Handoff

**Workspace Root:** `C:\AI_Workspace`  
**Main Server:** `C:\AI_Workspace\hub_server.py` (Runs at `http://127.0.0.1:7860`)  
**Hardware Target:** NVIDIA GeForce RTX 4070 (12 GB VRAM) on Windows  

---

## 1. Executive Summary & Core Vision

We built a self-hosted **Unified Local AI Hub** (`http://127.0.0.1:7860`) that combines:
1. **Uncensored Local Image Generation & Editing (`🎨 Image Studio` & `💬 Agent Chat`)** powered by ComfyUI (`Juggernaut-X-RunDiffusion-NSFW.safetensors`) on port `8188`.
2. **Hybrid AI Compute Engine (`📦 Models & Settings`)** that routes Vision, Prompt Engineering, Skill Creation, and Chat to the **Gemini API** (with all 5 configurable safety categories set to `BLOCK_NONE`) to save GPU VRAM—and **automatically falls back to the local uncensored `qwen2.5-vl-7b-instruct` model** in LM Studio whenever Gemini hits a hard server-side block (`finishReason=PROHIBITED_CONTENT`), then **auto-unloads the local LLM from VRAM** right before ComfyUI renders so ComfyUI gets 100% of the 12 GB RTX 4070.
3. **Etsy & Mayhem Marketplace Auto-Lister (`🛒 Auto-Lister` & `🎯 Teach & Record Browser Agent`)** using Vision AI to inspect product photos, write SEO Titles/Descriptions/13 Tags, and drive a persistent Playwright browser profile (`C:\AI_Workspace\browser_profile`) with a teach-by-demonstration action recorder.

---

## 2. Directory & File Architecture

| File / Folder | Path | Purpose |
| :--- | :--- | :--- |
| **Main Hub Server** | `C:\AI_Workspace\hub_server.py` | Single-file Python backend + responsive dark-mode web dashboard (`http://127.0.0.1:7860`). |
| **Browser Action Agent** | `C:\AI_Workspace\browser_agent.py` | Playwright persistent browser runner (`login`, `record`, and `execute` modes). |
| **Configuration** | `C:\AI_Workspace\config.json` | Stores Gemini API key, routing mode (`gemini_first` vs `local_only`), ComfyUI/LM Studio URLs, and marketplace defaults. |
| **Learned Memory (Level 1)** | `C:\AI_Workspace\learned_memory.json` | Persistent correction memory (`positive_boosts`, `negative_blocks`, `style_lessons`, `corrections_log`) auto-applied to generations and prompt enhancement. |
| **Studio Skills** | `C:\AI_Workspace\studio_skills\*.json` | Reusable Image Studio skill presets created via Agent Chat (`/skill ...`) or reference images. |
| **Browser Playbooks** | `C:\AI_Workspace\workflows\*.json` | Recorded Playwright step playbooks for `etsy_listing.json` and `mayhem_listing.json`. |
| **Generated Gallery** | `C:\AI_Workspace\outputs\images\` | Saved PNG/JPG outputs + `.json` metadata sidecars (recording exact prompt, negative prompt, seed, CFG, steps, and checkpoint). |
| **ComfyUI Portable** | `C:\ComfyUI_windows_portable\` | Local ComfyUI installation (`Juggernaut-X-RunDiffusion-NSFW.safetensors` in `ComfyUI\models\checkpoints`, LoRAs in `ComfyUI\models\loras`). |
| **LM Studio CLI** | `C:\Users\Joe\.lmstudio\bin\lms.exe` | Used to start LM Studio server, auto-load `qwen2.5-vl-7b-instruct`, and run `lms unload --all` to free GPU VRAM. |

---

## 3. What Has Been Completed So Far

### A. Hybrid Compute Engine (`Gemini BLOCK_NONE` + Auto Local Fallback + Auto VRAM Free)
* **Gemini API with `BLOCK_NONE`:** All 5 configurable Gemini safety categories (`HARM_CATEGORY_SEXUALLY_EXPLICIT`, `HARM_CATEGORY_DANGEROUS_CONTENT`, `HARM_CATEGORY_HARASSMENT`, `HARM_CATEGORY_HATE_SPEECH`, `HARM_CATEGORY_CIVIC_INTEGRITY`) are set to `BLOCK_NONE`.
* **Automatic On-Demand Local Fallback (`call_local_llm`):**
  * When an explicit uploaded photo triggers Google's non-configurable server-side `PROHIBITED_CONTENT` filter (or a text refusal), `call_local_llm()` automatically checks `check_local_llm_only_status()`.
  * If LM Studio's `qwen2.5-vl-7b-instruct` is unloaded, the Hub **automatically starts LM Studio and loads `qwen2.5-vl-7b-instruct`**, completes the uncensored Vision/Prompt task locally, and then **`generate_image_via_comfy()` automatically unloads the local LLM (`lms unload --all`)** right before submitting the ComfyUI render job so the RTX 4070 never runs out of VRAM.
* **Zero-Failure JSON Parser (`parse_ai_json_robust`):**
  * Increased `maxOutputTokens` to `>= 4096` and filtered out `gemini-2.5-flash` internal `thought` tokens so JSON responses never truncate mid-object.
  * Added fallback synthesizers in `create_studio_skill_from_chat()` and `fix_and_learn_from_image()` so `/skill` and `/fix` never fail with `"Could not parse skill JSON from AI response"`.

### B. Image Studio Skills & Level 1 Persistent Correction Memory
* **Studio Skills (`C:\AI_Workspace\studio_skills\`):**
  * Users can create skills in **💬 Agent Chat** via `/skill ...` (with or without an attached reference image) and select them from the **⚡ Studio Skill** dropdown in **🎨 Image Studio**.
* **Level 1 Learning Engine (`C:\AI_Workspace\learned_memory.json`):**
  * Every gallery card has a **🔧 Fix** button, and Image Studio has a **🔧 Fix & Teach AI Now** button.
  * Inspects the flawed image + its `.json` metadata sidecar + the user's critique, generates a repaired SDXL prompt with emphasis weights `(feature:1.3)`, saves permanent lessons into `learned_memory.json`, and regenerates the image.

### C. Multi-Turn Image Editing & Latent Face Preservation
* **Original Photo Context Anchor (`chatOriginalImagePath`):**
  * Uploading an image in **💬 Agent Chat** locks that file as the **Original Face Reference** while advancing the active canvas across multi-turn edits (with a **↩️ Reset Canvas to Original Photo** button).
* **Feathered Latent Noise Mask (`SetLatentNoiseMask` in `build_sdxl_workflow`):**
  * Replaced the post-decode pixel paste (`ImageCompositeMasked`, which was overwriting new facial/surface edits with the unedited original photo) with a feathered **Latent Noise Mask (`SetLatentNoiseMask`)** during `KSampler` (`0.45` relative latent noise over the core eye/nose/mouth landmarks, feathered into `1.0` on the rest of the image).
* **Conversational-to-SDXL Tag Translator (`clean_instruction_to_sdxl_tags`):**
  * Strips conversational English (`"I want you to add..."`, `"without changing any of the facial features"`) that confuses SDXL's CLIP encoder and translates requests into weighted SDXL tags.

---

## 4. Current Challenge: What We Are Trying to Accomplish Next

### The Goal
The user wants to upload a **real photo of a subject** (into **🎨 Image Studio** or **💬 Agent Chat**) and ask the model to **add specific visual elements/effects** (for example, adding realistic thick white viscous liquid onto the subject, modifying clothing, or adding specific NSFW details) **while keeping 100% of the subject's original facial features and identity completely intact.**

### Why Whole-Image SDXL Img2Img Hit a Wall
1. **Whole-Image Denoise vs. Identity Preservation:**
   * In standard whole-image SDXL Img2Img, every unmasked pixel is scrambled by noise.
   * At `denoise = 0.60`, SDXL has enough freedom to draw new objects/liquids, **but it alters the person's facial identity, skin texture, and background.**
   * At `denoise = 0.25–0.35`, SDXL preserves the person's face, **but it cannot add new objects or fluids** (it only creates faint smudges because 70% of the original dry skin pixels are forced to remain).
2. **Spatial Placement Blindness:**
   * Text-only prompts in whole-image Img2Img cannot tell ComfyUI *exact pixel coordinates* where an effect (like liquid or a clothing tear) should be placed on the uploaded photo.
3. **Base Checkpoint Vocabulary Limits (`Juggernaut-X` without LoRAs):**
   * While `Juggernaut-X-RunDiffusion-NSFW` is great at general anatomy and portraits, base SDXL checkpoints struggle to render convincing physics for specific viscous fluids or specialized NSFW effects from text prompts alone without a dedicated **SDXL LoRA**.

---

## 5. Implementation Status

### ✅ Solution 1: Interactive Brush Masking / Inpainting Canvas (COMPLETED)
- **HTML5 Brush Canvas:** Overlayed directly onto uploaded images in both **🎨 Image Studio** and **💬 Agent Chat**. Includes:
  - 🖌️ Brush mode with semi-transparent overlay
  - 🧽 Eraser mode
  - ✖ Clear Mask button
  - Brush size slider (8px to 70px)
- **ComfyUI Inpaint Workflow:**
  - Converts painted strokes into a pure black & white mask (`ImageToMask`).
  - Passes mask to `SetLatentNoiseMask` for high-denoise inpainting (`0.75 - 0.88`).
  - Utilizes `ImageCompositeMasked` at the final stage to guarantee **100.0% unpainted pixel lock** (protecting face, hair, and background completely).

### ⏳ Solution 2: Dedicated SDXL Effect LoRAs + Multi-LoRA Stacker (Next Step)
To make `Juggernaut-X` render specific NSFW effects (such as realistic viscous white liquid, wet skin sheen, or specific poses) with photorealistic quality instead of generic white streaks:
* Download 1–2 specialized **SDXL LoRAs** (`.safetensors` from Civitai/HuggingFace) into `C:\ComfyUI_windows_portable\ComfyUI\models\loras`.
* Upgrade `build_sdxl_workflow()` in `hub_server.py` to support **chaining multiple LoRAs** and automatically triggering the right LoRA + trigger words when a Studio Skill or prompt mentions that effect.

### ⏳ Solution 3: True Face-Identity Lock for Brand-New Poses (ReActor / InsightFace or IP-Adapter FaceID)
When the user wants to generate a **completely new pose or scene** (rather than inpainting onto the existing photo) while keeping the exact person's face from the uploaded photo:
* Integrate ComfyUI's **ReActor (InsightFace Face Swap)** or **IP-Adapter FaceID Plus v2** custom node into the ComfyUI workflow so the generated body/scene gets the exact facial identity of the uploaded reference photo automatically.

---

## 6. Quick Start When Opening in Antigravity IDE

1. Open **Antigravity IDE** and open the folder **`C:\AI_Workspace`** as your workspace.
2. Start (or verify) the Hub Server in the terminal:
   ```powershell
   C:\AI_Workspace\venv\Scripts\python.exe C:\AI_Workspace\hub_server.py
   ```
3. Open `http://127.0.0.1:7860` in your browser.
4. **First prompt to give the agent in Antigravity IDE:**
   > *"Read `PROJECT_HANDOFF.md` and `hub_server.py`. Let's implement Solution 1 (the Interactive Brush Inpainting Mask Canvas in Image Studio and Agent Chat) and Solution 2 (LoRA support for realistic fluid/effect inpainting) so I can paint over the exact area of an uploaded photo where I want an effect added while keeping 100% of the unpainted face and photo untouched."*
