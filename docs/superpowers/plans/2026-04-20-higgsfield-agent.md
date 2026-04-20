# Higgsfield Telegram Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Hermes skill that receives an inspiration image from Telegram, generates 4 FUFU character variations on Higgsfield's Soul v2 web app via browser automation, and sends the share links back to the user.

**Architecture:** Single Hermes skill (`higgsfield-generate`) using native browser tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_vision`) to drive the Higgsfield web UI, and the native Telegram gateway for messaging. One helper script (`get_aspect_ratio.py`) detects image dimensions. Persistent browser profile keeps the Higgsfield session logged in.

**Tech Stack:** Hermes Agent (v2026.4.16), native browser toolset (Camofox with managed persistence), native Telegram gateway, Python 3.11+, Pillow

**Spec:** `docs/superpowers/specs/2026-04-20-higgsfield-telegram-agent-design.md`

---

## File Structure

```
HiggsfieldAgent/
├── .env.example                    # env var template
├── .hermes.md                      # Hermes context file (do not modify skills)
├── config/
│   └── hermes-config-snippet.yaml  # merge into ~/.hermes/config.yaml
├── scripts/
│   └── get_aspect_ratio.py         # image dimension → closest Higgsfield aspect ratio
├── skills/
│   └── higgsfield-generate/
│       └── SKILL.md                # the full Hermes skill definition
├── tests/
│   └── test_get_aspect_ratio.py    # unit tests for aspect ratio script
└── docs/
    └── superpowers/
        ├── specs/
        │   └── 2026-04-20-higgsfield-telegram-agent-design.md
        └── plans/
            └── 2026-04-20-higgsfield-agent.md
```

---

### Task 1: Initialize the Repo

**Files:**
- Create: `.env.example`
- Create: `.hermes.md`
- Create: `config/hermes-config-snippet.yaml`

- [ ] **Step 1: Initialize git**

```bash
cd "/mnt/c/Users/Jamaal/Documents/Phantom Systems Inc/HiggsfieldAgent"
git init
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Telegram (configured via Hermes gateway)
TELEGRAM_BOT_TOKEN=<from BotFather>

# Higgsfield browser profile (persistent login)
HIGGSFIELD_BROWSER_PROFILE_PATH=~/.hermes/browser-profiles/higgsfield
```

- [ ] **Step 3: Create `.hermes.md`**

```markdown
# HiggsfieldAgent

HiggsfieldAgent is a Hermes skill that receives an inspiration image from Telegram,
generates 4 FUFU character variations on Higgsfield's Soul v2 web app using browser
automation, and sends the resulting share links back to the user on Telegram.

## Key Paths

- `skills/higgsfield-generate/` — Hermes skill for the full generation workflow
- `scripts/get_aspect_ratio.py` — helper to detect image aspect ratio
- `config/hermes-config-snippet.yaml` — merge into ~/.hermes/config.yaml

## Instructions for Hermes

- **Do not create, edit, or delete skills.**
- **Do not call `skill_manage`.**
- The `higgsfield-generate` skill is source-controlled in this repo and managed via git.
  Any changes to the skill workflow must go through a git commit, not in-session edits.
```

- [ ] **Step 4: Create `config/hermes-config-snippet.yaml`**

```yaml
# Merge this into ~/.hermes/config.yaml with:
#   yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
#     ~/.hermes/config.yaml config/hermes-config-snippet.yaml \
#     > /tmp/hermes-merged.yaml && mv /tmp/hermes-merged.yaml ~/.hermes/config.yaml
#
# Or manually copy the block below into your existing config.yaml.

skills:
  external_dirs:
    - ${HOME}/HiggsfieldAgent/skills

  config:
    higgsfield-generate:
      browser_profile: ${HIGGSFIELD_BROWSER_PROFILE_PATH}

# Enable persistent browser sessions (cookies survive restarts)
browser:
  camofox:
    managed_persistence: true
```

- [ ] **Step 5: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
*.egg-info/
.venv/
```

- [ ] **Step 6: Commit**

```bash
git add .env.example .hermes.md config/hermes-config-snippet.yaml .gitignore
git commit -m "feat: initialize repo with env template, hermes context, and config"
```

---

### Task 2: Write `get_aspect_ratio.py` (TDD)

**Files:**
- Create: `scripts/get_aspect_ratio.py`
- Create: `tests/test_get_aspect_ratio.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_get_aspect_ratio.py`:

```python
import subprocess
import sys
import os
import tempfile

import pytest
from PIL import Image

SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "get_aspect_ratio.py"
)

# Higgsfield Soul v2 aspect ratio options (confirm during integration):
# 1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9

def _run(width: int, height: int) -> str:
    """Create a temp image of given dimensions, run the script, return stdout."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new("RGB", (width, height), color="red")
        img.save(f, format="PNG")
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, tmp_path],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    finally:
        os.unlink(tmp_path)


def test_square_image():
    assert _run(1024, 1024) == "1:1"


def test_portrait_9_16():
    # 1080x1920 is exactly 9:16
    assert _run(1080, 1920) == "9:16"


def test_landscape_16_9():
    # 1920x1080 is exactly 16:9
    assert _run(1920, 1080) == "16:9"


def test_portrait_3_4():
    # 768x1024 is exactly 3:4
    assert _run(768, 1024) == "3:4"


def test_landscape_4_3():
    # 1024x768 is exactly 4:3
    assert _run(1024, 768) == "4:3"


def test_portrait_2_3():
    # 800x1200 is exactly 2:3
    assert _run(800, 1200) == "2:3"


def test_landscape_3_2():
    # 1200x800 is exactly 3:2
    assert _run(1200, 800) == "3:2"


def test_near_square_rounds_to_1_1():
    # 1000x1050 is close to 1:1
    assert _run(1000, 1050) == "1:1"


def test_iphone_photo_maps_to_3_4():
    # 3024x4032 = 3:4 ratio
    assert _run(3024, 4032) == "3:4"


def test_ultrawide_maps_to_16_9():
    # 2560x1080 ~= 2.37:1 — closest standard is 16:9 (1.78)
    assert _run(2560, 1080) == "16:9"


def test_missing_file_exits_nonzero():
    result = subprocess.run(
        [sys.executable, SCRIPT, "/nonexistent/image.png"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/mnt/c/Users/Jamaal/Documents/Phantom Systems Inc/HiggsfieldAgent"
pip install Pillow pytest
pytest tests/test_get_aspect_ratio.py -v
```

Expected: FAIL — `scripts/get_aspect_ratio.py` does not exist.

- [ ] **Step 3: Write the implementation**

Create `scripts/get_aspect_ratio.py`:

```python
#!/usr/bin/env python3
"""Given an image path, print the closest Higgsfield aspect ratio to stdout.

Usage:
    python get_aspect_ratio.py <image_path>

Output (stdout):
    One of: 1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9
"""
import sys
from PIL import Image

# Higgsfield Soul v2 aspect ratio options.
# Each entry is (label, width/height ratio).
RATIOS = [
    ("1:1", 1.0),
    ("2:3", 2 / 3),
    ("3:2", 3 / 2),
    ("3:4", 3 / 4),
    ("4:3", 4 / 3),
    ("9:16", 9 / 16),
    ("16:9", 16 / 9),
]


def closest_ratio(width: int, height: int) -> str:
    actual = width / height
    best_label = RATIOS[0][0]
    best_diff = abs(actual - RATIOS[0][1])
    for label, ratio in RATIOS[1:]:
        diff = abs(actual - ratio)
        if diff < best_diff:
            best_diff = diff
            best_label = label
    return best_label


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: get_aspect_ratio.py <image_path>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    try:
        with Image.open(path) as img:
            width, height = img.size
    except (FileNotFoundError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(closest_ratio(width, height))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_get_aspect_ratio.py -v
```

Expected: All 11 tests PASS.

- [ ] **Step 5: Create `tests/__init__.py`**

```bash
touch tests/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git add scripts/get_aspect_ratio.py tests/
git commit -m "feat: get_aspect_ratio.py with tests — maps image dimensions to Higgsfield ratios"
```

---

### Task 3: Write the `higgsfield-generate` SKILL.md

This is the core deliverable. The SKILL.md contains the full procedure that Hermes follows when the skill is triggered.

**Files:**
- Create: `skills/higgsfield-generate/SKILL.md`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p skills/higgsfield-generate
```

- [ ] **Step 2: Write `skills/higgsfield-generate/SKILL.md`**

```markdown
---
name: higgsfield-generate
description: Generate FUFU character variations on Higgsfield from a Telegram inspiration image.
version: 1.0.0
metadata:
  hermes:
    tags: [image-generation, higgsfield, telegram, browser-automation]
    category: creative
    requires_toolsets: [browser]
    config:
      - key: browser_profile
        description: "Path to persistent browser profile for Higgsfield login"
        default: "~/.hermes/browser-profiles/higgsfield"
        prompt: "Browser profile path for Higgsfield sessions"
---

# Higgsfield FUFU Generator

Generate 4 FUFU character variations from an inspiration image using Higgsfield's
Soul v2 web app, then send the share links back to the user on Telegram.

## When to Use

Use this skill when a user sends a photo/image in a Telegram chat. The image is the
inspiration reference for Higgsfield generation.

If the user sends a text message with no image, reply with:
"Send me an image and I'll generate FUFU variations on Higgsfield."

## Procedure

### Phase 1: Confirm and Prepare

1. Send a message to the user on Telegram:
   "Got your image! Starting Higgsfield generation — this takes about 8-10 minutes."

2. Determine the image aspect ratio by running:
   ```
   python scripts/get_aspect_ratio.py <image_path>
   ```
   The script prints one of: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `9:16`, `16:9`.
   Save the output as `ASPECT_RATIO`.

### Phase 2: Navigate and Configure Higgsfield

3. Navigate to the Higgsfield Soul v2 page:
   ```
   browser_navigate(url="https://higgsfield.ai/mobile/image/soul-v2")
   ```

4. Take a snapshot to verify the page loaded and identify elements:
   ```
   browser_snapshot()
   ```
   Confirm the page contains the Soul v2 generation interface. If the page shows a
   login screen instead, send this message to Telegram and stop:
   "Higgsfield session expired. Please log in manually and try again."

5. Click the **"Image Reference"** tab at the top of the page:
   ```
   browser_click(ref="<ref for Image Reference tab>")
   ```

6. Take a snapshot to see the Soul Character options:
   ```
   browser_snapshot()
   ```

7. Click the **"FUFU"** Soul Character:
   ```
   browser_click(ref="<ref for FUFU>")
   ```

8. Take a snapshot to find the image upload element:
   ```
   browser_snapshot()
   ```

9. Click the image upload area/button to trigger the file chooser, then provide
   the user's image file path. If the upload area is a file input element, click
   it and the browser will handle the file chooser with the provided path:
   ```
   browser_click(ref="<ref for upload area/input>")
   ```
   Provide the image file path from the Telegram message attachment.

10. Take a snapshot to verify the image uploaded successfully:
    ```
    browser_snapshot()
    ```
    Confirm the upload area now shows a preview of the image rather than an empty
    drop zone. If the preview is not visible, use `browser_vision` to visually
    verify:
    ```
    browser_vision(prompt="Is there an uploaded image preview visible in the upload area?")
    ```

11. Select the aspect ratio that matches `ASPECT_RATIO` (from step 2):
    ```
    browser_click(ref="<ref for ASPECT_RATIO button>")
    ```

12. Set **Batch Size** to **4**:
    ```
    browser_click(ref="<ref for batch size 4>")
    ```

13. Set **Quality** to **2K**:
    ```
    browser_click(ref="<ref for 2K quality>")
    ```

### Phase 3: Pre-Generation Checklist

14. Take a full snapshot to verify all settings:
    ```
    browser_snapshot(full=true)
    ```

15. Verify ALL of the following in the snapshot. Check each one:

    - [ ] **Image Reference tab** is the active/selected tab
    - [ ] **FUFU** is the selected Soul Character (highlighted/active)
    - [ ] **Image uploaded** — the upload area shows a preview, not an empty state
    - [ ] **Aspect ratio** — the button matching `ASPECT_RATIO` is selected/highlighted
    - [ ] **Batch Size = 4** — the "4" option is selected
    - [ ] **Quality = 2K** — the "2K" option is selected

    If the text snapshot is insufficient to confirm these visually, use:
    ```
    browser_vision(prompt="Verify: Is Image Reference tab active? Is FUFU selected? Is an image uploaded? What aspect ratio is selected? What batch size? What quality setting?")
    ```

16. If **any** check fails, send a message to Telegram specifying which check
    failed, and **DO NOT** proceed to generation:
    "Generation aborted — pre-check failed: [specific check that failed]. Please try again."
    Stop here.

### Phase 4: Generate

17. Click the **Generate** button:
    ```
    browser_click(ref="<ref for Generate button>")
    ```

18. Take a snapshot to confirm generation started:
    ```
    browser_snapshot()
    ```
    Look for a progress indicator, loading spinner, or confirmation that the job
    was submitted. If generation did not start (e.g., an error message appeared),
    send a failure message to Telegram and stop:
    "Generation failed to start: [error message from page]. Please try again."

### Phase 5: Wait and Collect Results

19. Wait **8 minutes** for the images to generate.

20. Navigate to the assets page:
    ```
    browser_navigate(url="https://higgsfield.ai/asset/image")
    ```

21. Take a snapshot to check if the images are ready:
    ```
    browser_snapshot()
    ```
    Look at the top 4 images in the grid. Check for:
    - Completed status (no loading spinners or progress bars)
    - Recent timestamps matching this generation job

    If images are still loading or not yet visible, use `browser_vision` to
    visually check:
    ```
    browser_vision(prompt="Are the top 4 images in the grid fully loaded and complete, or are any still showing loading/progress indicators?")
    ```

22. If images are **NOT ready**:
    - Wait **7 more minutes** (15 minutes total from generation start).
    - Navigate to the assets page again:
      ```
      browser_navigate(url="https://higgsfield.ai/asset/image")
      ```
    - Take another snapshot and re-check:
      ```
      browser_snapshot()
      ```

23. If images are **STILL NOT ready** after 15 minutes total, send a failure
    message to Telegram and stop:
    "Generation didn't complete after 15 minutes. Please try again or check Higgsfield manually."

### Phase 6: Extract Share Links

24. For each of the **4 newest images** in the grid (starting from the top-left),
    repeat steps 25–29:

25. Click the **3-dot menu** icon in the top-right corner of the image card:
    ```
    browser_click(ref="<ref for 3-dot menu>")
    ```

26. Take a snapshot to see the dropdown menu:
    ```
    browser_snapshot()
    ```

27. Hover over or click **"Share"** to expand the share sub-menu:
    ```
    browser_click(ref="<ref for Share option>")
    ```

28. Take a snapshot to see the share options:
    ```
    browser_snapshot()
    ```

29. Click **"Copy link"**:
    ```
    browser_click(ref="<ref for Copy link>")
    ```
    After clicking, take a snapshot to capture the link:
    ```
    browser_snapshot()
    ```
    Look for the link in a toast notification, a URL displayed in the share
    dialog, or any visible text containing a Higgsfield URL. Save this as
    `LINK_N` (where N is 1-4).

    If the link is not visible in the text snapshot, use:
    ```
    browser_vision(prompt="What URL or link was just copied or displayed after clicking Copy link?")
    ```

    Close the menu by clicking elsewhere on the page or pressing Escape:
    ```
    browser_press(key="Escape")
    ```

30. After collecting all 4 links, send a single message to Telegram:

    ```
    Your FUFU generations are ready!

    1. {LINK_1}
    2. {LINK_2}
    3. {LINK_3}
    4. {LINK_4}
    ```

## Pitfalls

- **Session expired**: If the page shows a login screen at step 4, the browser
  profile cookies have expired. The user must manually log in again. Send a
  message and stop — do not attempt to log in programmatically.
- **File upload**: The file chooser interaction depends on the browser profile
  having the correct permissions. If the upload fails, try using `browser_vision`
  to see what the upload area looks like and adjust the interaction accordingly.
- **Clipboard vs. visible link**: Hermes browser tools use accessibility trees,
  not the system clipboard. "Copy link" puts the URL in the clipboard, but we
  need to read it from visible page elements (toast, dialog, URL field). If
  nothing is visible, try `browser_console()` to check if the URL was logged.
- **Rate limits**: Higgsfield may throttle generation requests. If the Generate
  button produces an error about rate limits or credits, report to the user.
- **3-dot menu positioning**: The 3-dot menu is in the top-right corner of each
  image card. If the grid layout changes, the ref IDs will be different. Always
  use `browser_snapshot()` to find the correct ref before clicking.

## Verification

After sending the 4 links to Telegram, the skill is complete. The user can click
each link to verify the generated images on Higgsfield.
```

- [ ] **Step 3: Commit**

```bash
git add skills/higgsfield-generate/SKILL.md
git commit -m "feat: higgsfield-generate skill — full browser automation workflow"
```

---

### Task 4: Integration Test — Manual Dry Run

This task is a manual verification step, not automated tests.

**Files:** None (manual browser verification)

- [ ] **Step 1: Merge config into Hermes**

```bash
yq eval-all 'select(fileIndex == 0) * select(fileIndex == 1)' \
  ~/.hermes/config.yaml config/hermes-config-snippet.yaml > /tmp/hermes-merged.yaml \
  && mv /tmp/hermes-merged.yaml ~/.hermes/config.yaml
```

- [ ] **Step 2: Add env vars to `~/.hermes/.env`**

Add these lines to `~/.hermes/.env`:

```bash
TELEGRAM_BOT_TOKEN=<your bot token>
HIGGSFIELD_BROWSER_PROFILE_PATH=~/.hermes/browser-profiles/higgsfield
```

- [ ] **Step 3: Set up Telegram gateway**

```bash
hermes gateway setup
# Choose Telegram, paste bot token, enter user ID when prompted
```

- [ ] **Step 4: Log into Higgsfield manually**

```bash
hermes browser --profile ~/.hermes/browser-profiles/higgsfield
```

Navigate to `https://higgsfield.ai` and log in with your subscription account. Close the browser — cookies are persisted.

- [ ] **Step 5: Verify Higgsfield aspect ratios**

Navigate to `https://higgsfield.ai/mobile/image/soul-v2` in the Hermes browser and note the exact aspect ratio options available. If they differ from `1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9`, update the `RATIOS` list in `scripts/get_aspect_ratio.py` and the corresponding tests.

- [ ] **Step 6: Start the Telegram gateway and test**

```bash
hermes gateway
```

Send a test image to the bot on Telegram. Watch the Hermes logs for the skill invocation and browser automation steps. Verify:
- Confirmation message received on Telegram
- Browser navigates to Higgsfield correctly
- Image is uploaded
- Settings are applied
- Pre-gen checklist passes
- Generation starts
- Links are sent back after the wait period

- [ ] **Step 7: Commit any fixes from the dry run**

```bash
git add -A
git commit -m "fix: adjustments from integration dry run"
```

---

### Task 5: Final Commit and Cleanup

**Files:**
- Verify: all files committed and no stray changes

- [ ] **Step 1: Run all tests**

```bash
cd "/mnt/c/Users/Jamaal/Documents/Phantom Systems Inc/HiggsfieldAgent"
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Verify repo structure**

```bash
find . -not -path './.git/*' -not -path './.git' | sort
```

Expected output should match the file structure defined at the top of this plan.

- [ ] **Step 3: Final commit if needed**

```bash
git status
# If any uncommitted changes:
git add -A
git commit -m "chore: final cleanup"
```
