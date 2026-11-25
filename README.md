# ⚡ Unified Local AI Hub & Teachable Action Agent (`C:\AI_Workspace`)

This workspace unites your local uncensored image generation (`ComfyUI` + `Juggernaut-X-RunDiffusion-NSFW` on your RTX 4070), your local Vision/Chat AI (`Qwen2.5-VL-7B-Instruct` via LM Studio), and a **Teachable Browser Action Agent** that creates and auto-publishes product listings on **Etsy** and **Mayhem Marketplace**.

---

## 🚀 Quick Start (One Click)

Double-click **[Start_AI_Hub.bat](file:///C:/AI_Workspace/Start_AI_Hub.bat)** in `C:\AI_Workspace`.

On first launch, it will automatically:
1. Create a local virtual environment (`C:\AI_Workspace\venv`).
2. Install **Playwright** and its persistent **Chromium** browser for marketplace automation.
3. Launch the **Unified Local AI Hub** web dashboard at **`http://127.0.0.1:7860`**.

---

## 🧩 What's Inside the Dashboard (`http://127.0.0.1:7860`)

### 1. 🎨 Image Studio
* **Direct ComfyUI Integration**: Connects directly to `C:\ComfyUI_windows_portable` and defaults to your installed **`Juggernaut-X-RunDiffusion-NSFW.safetensors`** checkpoint.
* **1-Click Engine Start**: Click **Start ComfyUI** in the top bar if ComfyUI isn't already running.
* **AI Prompt Enhancer**: Click **✨ Enhance Prompt with Local AI** to expand short ideas into detailed SDXL prompts using your local LLM.
* **1-Click Send to Lister**: Every generated image in `C:\AI_Workspace\outputs\images` has a **🛒 Use in Listing** button to send it straight to the Etsy & Mayhem auto-lister.

### 2. 🎯 Teach & Record Browser Agent (Etsy & Mayhem Marketplace)
* **Step 1 — One-Time Login**:
  * Go to the **🎯 Teach & Record Browser Agent** tab and click **🔑 Open Browser to Log into Etsy** and **🔑 Open Browser to Log into Mayhem**.
  * Log into your seller accounts once. Because the agent uses a persistent browser profile (`C:\AI_Workspace\browser_profile`), your login session stays saved across runs.
* **Step 2 — Teach by Demonstration (Record Mode)**:
  * Select **`Mayhem Marketplace Playbook (mayhem_listing)`** or **`Etsy Listing Playbook (etsy_listing)`**, enter your seller create-listing URL, and click **🔴 Launch Browser & Record My Actions Now**.
  * Perform a listing once in the browser window. The live recorder automatically captures your file uploads, button clicks, and text inputs — converting Title, Description, Price, Quantity, and Tags into dynamic variables (`{{title}}`, `{{description}}`, `{{price}}`, `{{quantity}}`, `{{tags}}`).
  * Close the browser window when done to save your playbook to `C:\AI_Workspace\workflows\`.

### 3. 🛒 Auto-Lister & Drop-Folder Automation
* **Interactive Mode**:
  * Upload product photos (or pick from your generated gallery) in **🛒 Auto-Lister (Etsy & Mayhem)**.
  * Click **🧠 Step 1: Auto-Write Title, Description & Tags with Local Vision AI** — `Qwen2.5-VL-7B` inspects your product photos and writes the SEO title, description, and 13 Etsy tags.
  * Click **🚀 Step 2: Launch Agent & Publish to Selected Marketplaces** — the browser agent opens Etsy and Mayhem Marketplace, uploads your photos, fills every field, and **clicks Publish automatically**.
* **Hands-Free Drop Folder (`C:\AI_Workspace\drop_inbox`)**:
  * Drop any product folder containing photos (and an optional `notes.txt`) into `C:\AI_Workspace\drop_inbox\<Product_Name>`.
  * Check **Auto-Watch & Publish New Folders Automatically** (or click **Process All Drop-Inbox Folders Now**) and the agent will automatically write the listing copy, publish to Etsy & Mayhem Marketplace, and move the completed folder to `C:\AI_Workspace\drop_processed`.

### 4. 💬 Agent Chat
* Chat freely with your local LLM.
* Type `/draw <prompt>` in chat to generate images right inside the chat stream.
* Type `teach mayhem marketplace` or `teach etsy` to launch the teaching browser directly from chat.
