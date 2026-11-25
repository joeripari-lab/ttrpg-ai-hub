# Unified Local AI Hub — Inpainting, Multi-LoRA & Face-Lock Implementation Plan

**Workspace:** `C:\AI_Workspace`
**Target Files:** `hub_server.py`, `config.json`, `studio_skills/*.json`
**ComfyUI Root:** `C:\ComfyUI_windows_portable\ComfyUI`
**Hardware Constraint:** NVIDIA RTX 4070 (12 GB VRAM) — strict sequential VRAM discipline (`lms unload --all` prior to ComfyUI execution).

---

## Phase 1: Audit & Repair Existing Brush Inpainting Pipeline (Solution 1)

**Objective:** Fix spatial misalignment, mask polarity bugs, and hard seams in the existing HTML5 Brush Canvas + ComfyUI inpaint workflow across both **🎨 Image Studio** and **💬 Agent Chat**.

### 1.1 Frontend Canvas Mask Export Audit (`hub_server.py` embedded HTML/JS)
* **Inspect:** Locate the `<canvas>` mask export function in both Image Studio and Agent Chat.
* **Fix Natural Resolution Scaling:** Ensure the exported mask PNG is drawn onto an offscreen canvas sized to `img.naturalWidth x img.naturalHeight` (not `img.clientWidth x img.clientHeight`).
* **Fix Binary Mask Polarity:** Render painted brush strokes as pure white (`#FFFFFF`, alpha `255`) over a pure black (`#000000`, alpha `255`) background so `LoadImage` / `ImageToMask` receives unambiguous grayscale values (`1.0` = inpaint target, `0.0` = locked original).
* **Verify Payload Routing:** Confirm both `/api/generate` (Image Studio) and `/api/chat` (Agent Chat multi-turn edit) transmit `mask_base64` (or saved mask file path) alongside `init_image_path` whenever any brush strokes exist on the canvas.

### 1.2 ComfyUI Inpaint Node Graph Repair (`build_sdxl_workflow` in `hub_server.py`)
* **Inspect:** Trace how `build_sdxl_workflow()` builds the node dictionary when `mask_path` is provided.
* **Fix Mask Wiring & Soft Blending:**
  1. Load original image via `LoadImage` (`node_orig`) and mask image via `LoadImage` (`node_mask`) or `ImageToMask` (`channel="red"`).
  2. Insert `GrowMask` (`expand=6`, `tapered_corners=True`) followed by `FeatherMask` (`left=12, top=12, right=12, bottom=12`) so edits blend smoothly into surrounding skin/fabric.
  3. Wire the feathered mask into `SetLatentNoiseMask` (feeding `KSampler` with `denoise` clamped between `0.78` and `0.88` for masked runs, ignoring low whole-image denoise defaults).
  4. Wire the decoded `VAEDecode` output + `node_orig` + feathered mask into `ImageCompositeMasked` (`x=0, y=0, resize_source=False`) as the final output before `SaveImage`, guaranteeing 100% pixel preservation outside the painted region.

### Phase 1 Verification Gate
* Restart `hub_server.py`, upload a test portrait in Image Studio, paint a mask strictly over the chest/shirt area, and prompt for a color/texture change.
* **Pass Criteria:** Output PNG matches input pixel dimensions exactly; face, hair, and background match the source image 1:1; edited region has soft, artifact-free edges.

---

## Phase 2: Dynamic Multi-LoRA Stacker & Trigger Preservation (Solution 2)

**Objective:** Allow `Juggernaut-X-RunDiffusion-NSFW.safetensors` to dynamically load one or more SDXL effect LoRAs from `C:\ComfyUI_windows_portable\ComfyUI\models\loras` based on Studio Skills or prompt tags.

### 2.1 LoRA Discovery & Config Schema
* **Add Helper `get_available_loras()` in `hub_server.py`:** Scan `C:\ComfyUI_windows_portable\ComfyUI\models\loras` recursively for `.safetensors` files and return relative paths compatible with ComfyUI's `LoraLoader` dropdown format.
* **Add Endpoint `/api/loras`:** Expose available LoRAs to the frontend so Image Studio and Studio Skill JSONs (`C:\AI_Workspace\studio_skills\*.json`) can attach `loras: [{"name": "effect.safetensors", "strength_model": 0.85, "strength_clip": 0.85, "trigger_words": "..."}]`.

### 2.2 Chained `LoraLoader` Injection in `build_sdxl_workflow()`
* **Implement Model/CLIP Chaining:**
  * Start with `current_model = [checkpoint_node_id, 0]` and `current_clip = [checkpoint_node_id, 1]`.
  * For each active LoRA in the request or matched Studio Skill, instantiate a `LoraLoader` node (`lora_name`, `strength_model`, `strength_clip`), wiring `model=current_model` and `clip=current_clip`, then update `current_model` and `current_clip` to the new `LoraLoader` outputs.
  * Wire the final `current_model` into `KSampler` (or IP-Adapter/ReActor in Phase 3) and final `current_clip` into positive/negative `CLIPTextEncode` nodes.

### 2.3 Protect Trigger Words in `clean_instruction_to_sdxl_tags()`
* **Inspect & Update:** Ensure `clean_instruction_to_sdxl_tags()` and `learned_memory.json` prompt assembly prepend/preserve explicit LoRA `trigger_words` verbatim without stripping underscores, parentheses, or emphasis weights `(tag:1.25)`.

### Phase 2 Verification Gate
* Verify `/api/loras` returns `.safetensors` files from `ComfyUI\models\loras`.
* Inspect generated workflow JSON payload logged prior to ComfyUI `/prompt` submission to confirm `LoraLoader` nodes chain cleanly into `CLIPTextEncode` and `KSampler` without validation errors.

---

## Phase 3: Full-Pose Identity Lock via ReActor FaceSwap & CodeFormer (Solution 3) — ✅ COMPLETED

**Objective:** Support brand-new poses and scenes (where pixel inpainting is not used) while locking the subject's facial identity to the uploaded reference photo (`chatOriginalImagePath` or Image Studio reference upload).

### 3.1 Custom Node & Dependencies Setup (Completed)
- Installed `ComfyUI-ReActor` in `C:\ComfyUI_windows_portable\ComfyUI\custom_nodes\ComfyUI-ReActor`.
- Installed dependencies into ComfyUI's embedded Python: `onnxruntime-gpu`, `insightface`, `albumentations`, `ultralytics`, `opencv-python`.
- Downloaded `inswapper_128.onnx` into `C:\ComfyUI_windows_portable\ComfyUI\models\insightface\`.
- Downloaded `codeformer-v0.1.0.pth` into `C:\ComfyUI_windows_portable\ComfyUI\models\facerestore_models\`.

### 3.2 Workflow & UI Integration (Completed)
- **ComfyUI Graph Injection:** Added `ReActorFaceSwap` node post-`VAEDecode` in `build_sdxl_workflow()` with `inswapper_128.onnx` + CodeFormer restoration (`visibility=0.85`, `weight=0.60`).
- **Image Studio UI:** Added **🎭 ReActor Identity Swap (Brand-New Poses / Angles)** toggle (`#gen-enable-reactor`).
- **Agent Chat UI:** Added **🎭 Brand-New Pose + ReActor Face-Lock** mode in the action dropdown. Automatically runs text-to-image with your reference face swapped and restored onto the generated subject.