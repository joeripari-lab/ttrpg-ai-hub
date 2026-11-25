#!/usr/bin/env python3
"""
Playwright Persistent Browser Agent for Etsy & Mayhem Marketplace
Modes:
  1. login    -> Opens persistent browser so user can log into Etsy & Mayhem Marketplace once
  2. record   -> Opens persistent browser + injects live click/input recorder that saves steps to a workflow JSON
  3. execute  -> Runs a saved workflow JSON with product data (images, title, description, price, quantity, tags)
"""
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

import app_paths

BASE_DIR = app_paths.DATA_DIR
BROWSER_PROFILE_DIR = BASE_DIR / "browser_profile"
WORKFLOWS_DIR = BASE_DIR / "workflows"

RECORDER_JS = """
(() => {
    if (window.__aiHubRecorderInstalled) return;
    window.__aiHubRecorderInstalled = true;

    const banner = document.createElement('div');
    banner.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:2147483647;background:#111827;color:#10b981;padding:12px 16px;border-radius:10px;border:2px solid #10b981;font-family:sans-serif;font-size:13px;box-shadow:0 10px 25px rgba(0,0,0,0.5);';
    banner.innerHTML = '<b>🔴 AI Hub Teach Mode Active</b><br><span style="color:#d1d5db;font-size:11px;">Click & fill fields normally. Close browser when finished to save playbook.</span>';
    document.documentElement.appendChild(banner);

    function bestSelector(el) {
        if (!el || el === document.body) return '';
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.getAttribute('data-testid')) return `[data-testid="${el.getAttribute('data-testid')}"]`;
        if (el.getAttribute('name')) return `${el.tagName.toLowerCase()}[name="${el.getAttribute('name')}"]`;
        if (el.getAttribute('placeholder')) return `${el.tagName.toLowerCase()}[placeholder="${el.getAttribute('placeholder')}"]`;
        if (el.getAttribute('aria-label')) return `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;
        const text = (el.innerText || '').trim();
        if ((el.tagName === 'BUTTON' || el.tagName === 'A') && text && text.length < 35) {
            return `${el.tagName.toLowerCase()}:has-text("${text.replace(/"/g, '\\"')}")`;
        }
        let path = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
            const cls = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
            if (cls) path += '.' + cls;
        }
        return path;
    }

    function guessVariable(el, val) {
        const meta = ((el.name || '') + ' ' + (el.id || '') + ' ' + (el.placeholder || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
        if (meta.includes('title') || meta.includes('name')) return '{{title}}';
        if (meta.includes('desc')) return '{{description}}';
        if (meta.includes('price')) return '{{price}}';
        if (meta.includes('quant') || meta.includes('stock')) return '{{quantity}}';
        if (meta.includes('tag')) return '{{tags}}';
        return val;
    }

    document.addEventListener('change', (e) => {
        const el = e.target;
        const sel = bestSelector(el);
        if (!sel) return;
        if (el.type === 'file') {
            window.recordStep(JSON.stringify({
                action: 'upload_files',
                selector: sel,
                value: '{{images}}',
                url: location.href,
                note: 'Upload files into ' + sel
            }));
        } else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
            const mappedVal = guessVariable(el, el.value);
            window.recordStep(JSON.stringify({
                action: 'fill',
                selector: sel,
                value: mappedVal,
                raw_sample: el.value,
                url: location.href,
                note: `Fill ${sel} with ${mappedVal}`
            }));
        }
    }, true);

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('button, a, [role="button"], input[type="submit"]');
        if (!btn) return;
        const sel = bestSelector(btn);
        if (!sel) return;
        window.recordStep(JSON.stringify({
            action: 'click',
            selector: sel,
            url: location.href,
            note: 'Click ' + ((btn.innerText || btn.value || sel).trim().slice(0, 40))
        }));
    }, true);
})();
"""

def first_matching_locator(page, selector_group, timeout=4000):
    selectors = [s.strip() for s in selector_group.split(",") if s.strip()]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                return loc
        except Exception:
            continue
    # Wait briefly on the first selector as fallback
    if selectors:
        try:
            loc = page.locator(selectors[0]).first
            loc.wait_for(state="attached", timeout=timeout)
            return loc
        except Exception:
            pass
    return None

def run():
    if len(sys.argv) < 2:
        print("Usage: browser_agent.py <payload.json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        job = json.load(f)

    mode = job.get("mode", "login")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else context.new_page()

        if mode == "login":
            target_url = job.get("url", "https://www.etsy.com/your/shops/me/tools/listings/create")
            print(f"[BrowserAgent] Opening {target_url} for login/session setup...")
            page.goto(target_url)
            print("[BrowserAgent] Log in to your accounts. Close the browser window when done.")
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
            context.close()
            return

        if mode == "record":
            wf_id = job.get("workflow_id", "custom_workflow")
            wf_name = job.get("workflow_name", "Recorded Marketplace Workflow")
            start_url = job.get("url", "https://mayhemmarketplace.com")
            recorded_steps = [
                {"action": "goto", "url": start_url, "note": f"Navigate to {start_url}"}
            ]

            def on_record_step(step_json):
                step = json.loads(step_json)
                print(f"[Recorded] {step['action']} -> {step.get('selector')} ({step.get('value', '')})")
                recorded_steps.append(step)

            context.expose_binding("recordStep", lambda source, step_json: on_record_step(step_json))
            context.add_init_script(RECORDER_JS)
            page.goto(start_url)
            page.evaluate(RECORDER_JS)
            print("[BrowserAgent] Recording mode active! Perform your listing actions in the browser, then close the browser window to save.")
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass

            wf_path = WORKFLOWS_DIR / f"{wf_id}.json"
            wf_obj = {
                "id": wf_id,
                "name": wf_name,
                "marketplace": wf_id.split("_")[0],
                "start_url": start_url,
                "description": f"Recorded by user demonstration on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "updated_at": datetime.now().isoformat(),
                "steps": recorded_steps
            }
            with open(wf_path, "w", encoding="utf-8") as wf_f:
                json.dump(wf_obj, wf_f, indent=2)
            print(f"[BrowserAgent] Saved {len(recorded_steps)} steps to {wf_path}")
            context.close()
            return

        if mode == "execute":
            wf_path = WORKFLOWS_DIR / f"{job['workflow_id']}.json"
            with open(wf_path, "r", encoding="utf-8") as wf_f:
                workflow = json.load(wf_f)

            variables = job.get("variables", {})
            auto_publish = bool(job.get("auto_publish", True))

            def sub_vars(val):
                if not isinstance(val, str):
                    return val
                out = val
                for k, v in variables.items():
                    if isinstance(v, (str, int, float)):
                        out = out.replace(f"{{{{{k}}}}}", str(v))
                return out

            print(f"[BrowserAgent] Executing workflow: {workflow.get('name')} (auto_publish={auto_publish})")
            for idx, step in enumerate(workflow.get("steps", []), start=1):
                action = step.get("action")
                sel = step.get("selector", "")
                val = step.get("value", "")
                print(f"  Step {idx}: {action} - {step.get('note', sel)}")

                try:
                    if action == "goto":
                        target = sub_vars(step.get("url", workflow.get("start_url", "")))
                        page.goto(target, wait_until="domcontentloaded", timeout=45000)

                    elif action == "wait":
                        time.sleep(float(step.get("seconds", 2)))

                    elif action == "upload_files":
                        imgs = variables.get("images", [])
                        if isinstance(imgs, str):
                            imgs = [imgs]
                        imgs = [str(p) for p in imgs if os.path.exists(str(p))]
                        if imgs:
                            loc = first_matching_locator(page, sel, timeout=8000)
                            if loc:
                                loc.set_input_files(imgs)
                                time.sleep(2)
                            else:
                                print(f"  [Warn] File input not found for selector: {sel}")

                    elif action == "fill":
                        text_val = sub_vars(val)
                        loc = first_matching_locator(page, sel, timeout=6000)
                        if loc:
                            loc.scroll_into_view_if_needed()
                            loc.fill(str(text_val))
                            time.sleep(0.5)
                        else:
                            print(f"  [Warn] Input not found for selector: {sel}")

                    elif action == "add_tags":
                        tags = variables.get("tags", [])
                        if isinstance(tags, str):
                            tags = [t.strip() for t in tags.split(",") if t.strip()]
                        loc = first_matching_locator(page, sel, timeout=5000)
                        if loc and tags:
                            loc.scroll_into_view_if_needed()
                            for t in tags[:13]:
                                loc.fill(str(t)[:20])
                                loc.press("Enter")
                                time.sleep(0.3)

                    elif action == "click":
                        loc = first_matching_locator(page, sel, timeout=5000)
                        if loc:
                            loc.scroll_into_view_if_needed()
                            loc.click()
                            time.sleep(1.0)

                    elif action == "publish_or_draft":
                        target_sel = step.get("publish_selector") if auto_publish else step.get("draft_selector")
                        loc = first_matching_locator(page, target_sel, timeout=6000)
                        if loc:
                            loc.scroll_into_view_if_needed()
                            loc.click()
                            print(f"  [Success] Clicked {'Publish' if auto_publish else 'Save Draft'} button!")
                            time.sleep(5.0)
                        else:
                            print(f"  [Notice] Final submit button ({target_sel}) not auto-clicked. Browser remains open for 15s so you can inspect.")
                            time.sleep(15.0)
                except Exception as step_err:
                    print(f"  [Step Error] {step_err}")

            print("[BrowserAgent] Workflow complete! Keeping browser open for 8 seconds...")
            time.sleep(8)
            context.close()

if __name__ == "__main__":
    run()
