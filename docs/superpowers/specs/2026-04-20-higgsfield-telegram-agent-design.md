# Higgsfield Telegram Agent — Design Spec

**Date**: 2026-04-20
**Repo**: `C:\Users\Jamaal\Documents\Phantom Systems Inc\HiggsfieldAgent`
**Status**: Draft

---

## Overview

A Hermes agent skill that lets a Telegram user send an inspiration image and receive 4 AI-generated FUFU character variations from Higgsfield's Soul v2 web app. The agent uses Hermes native browser automation tools to drive the Higgsfield UI and the Hermes native Telegram gateway for messaging.

**Key constraint**: This uses the Higgsfield **subscription web app** (not the Higgsfield API). The browser drives the UI at `https://higgsfield.ai/mobile/image/soul-v2` directly.

---

## Architecture

```
Telegram User
    | (sends image)
    v
Hermes Telegram Gateway
    | (downloads image, extracts chat_id)
    v
higgsfield-generate skill
    |
    +-- 1. Send confirmation to Telegram
    +-- 2. Detect image aspect ratio (scripts/get_aspect_ratio.py)
    +-- 3. Browser: navigate to Higgsfield Soul v2
    +-- 4. Browser: select "Image Reference" tab
    +-- 5. Browser: select "FUFU" Soul Character
    +-- 6. Browser: upload the user's image
    +-- 7. Browser: set aspect ratio (closest match to image)
    +-- 8. Browser: set Batch Size = 4, Quality = 2K
    +-- 9. Pre-generation checklist validation
    +-- 10. Browser: click Generate
    +-- 11. Wait 8 minutes, check results
    +-- 12. If not ready, wait 7 more minutes, check again
    +-- 13. If still not ready, report failure to Telegram
    +-- 14. Browser: navigate to assets page, extract 4 share links
    +-- 15. Send 4 links to Telegram user
```

---

## Telegram Gateway Integration

### Configuration

Hermes native Telegram gateway. Env vars in `~/.hermes/.env`:

```bash
TELEGRAM_BOT_TOKEN=<from BotFather>
TELEGRAM_ALLOWED_USERS=          # empty for now; whitelist added later
```

### Incoming Messages

- When a user sends a photo, Hermes downloads it and provides the local file path to the skill along with the chat ID.
- If a message contains no image (text only), the skill replies with a usage hint: "Send me an image and I'll generate FUFU variations on Higgsfield."

### Outgoing Messages

| Event | Message |
|-------|---------|
| Image received | "Got your image! Starting Higgsfield generation — this takes about 8-10 minutes." |
| Success | All 4 share links in a numbered list |
| Pre-gen check failed | Which specific check failed and that generation was not started |
| Timeout (15 min) | "Generation didn't complete after 15 minutes. Please try again or check Higgsfield manually." |

### Queueing

Jobs are processed one at a time. If a new image arrives while a job is in progress, Hermes's native skill invocation queue holds it until the current job completes. No custom queue code.

---

## Browser Automation Workflow

### Persistent Login

One-time manual setup: log into Higgsfield in the Hermes browser profile. Cookies persist across sessions via `HIGGSFIELD_BROWSER_PROFILE_PATH`. The agent never needs to handle login.

### Per-Job Steps

All steps use Hermes native browser tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_scroll`).

#### Page Setup

1. `browser_navigate` to `https://higgsfield.ai/mobile/image/soul-v2`
2. `browser_snapshot` — verify page loaded
3. `browser_click` the **"Image Reference"** tab
4. `browser_snapshot` — find Soul Character options
5. `browser_click` **"FUFU"** character
6. `browser_snapshot` — find image upload element
7. Upload the user's image via the file input
8. `browser_snapshot` — verify image uploaded (preview visible)

#### Aspect Ratio Selection

- Run `scripts/get_aspect_ratio.py <image_path>` to get the closest Higgsfield aspect ratio
- The script reads image dimensions with Pillow and maps to the closest option available in the Higgsfield UI. The exact aspect ratio options must be confirmed from the Higgsfield Soul v2 page during implementation and hardcoded into the script.
- `browser_click` to select the matching aspect ratio button

#### Settings

- `browser_click` Batch Size → select **4**
- `browser_click` Quality → select **2K**

#### Pre-Generation Checklist

`browser_snapshot` and verify all of the following:

- Image Reference tab is active
- FUFU character is selected
- User image is uploaded (preview visible, not empty upload area)
- Correct aspect ratio is selected
- Batch Size = 4
- Quality = 2K

If **any** check fails: send a failure message to Telegram specifying which check failed. Do **not** click Generate.

#### Generate

- `browser_click` the **Generate** button
- `browser_snapshot` — confirm generation started (progress indicator or confirmation element visible)

---

## Waiting & Results Collection

### Waiting Strategy

1. After clicking Generate, wait **8 minutes**
2. `browser_navigate` to `https://higgsfield.ai/asset/image`
3. `browser_snapshot` — check if the top 4 images in the grid are the newly generated ones (look for recent timestamps, completed status, no loading spinners)
4. If images are not ready:
   - Wait **7 more minutes** (15 minutes total from generation start)
   - `browser_navigate` to the assets page again
   - `browser_snapshot` — re-check
5. If still not ready after 15 minutes: send failure message to Telegram

### Link Extraction

For each of the 4 newest images in the grid:

1. `browser_click` the **3-dot menu** (top-right corner of the image card)
2. `browser_snapshot` — find the dropdown
3. Hover/click **"Share"** to expand the sub-menu
4. `browser_click` **"Copy link"**
5. `browser_snapshot` — capture the link from a toast notification, URL field in the share dialog, or other visible element (since Hermes browser tools use accessibility trees, not a real clipboard)
6. Repeat for all 4 images

### Delivery

Send a single Telegram message:

```
Your FUFU generations are ready!

1. <link_1>
2. <link_2>
3. <link_3>
4. <link_4>
```

---

## Repo Structure

```
HiggsfieldAgent/
├── .env.example
├── .hermes.md
├── README.md
├── config/
│   └── hermes-config-snippet.yaml
├── scripts/
│   └── get_aspect_ratio.py
├── skills/
│   └── higgsfield-generate/
│       └── SKILL.md
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-04-20-higgsfield-telegram-agent-design.md
```

### .env.example

```bash
# Telegram (configured via Hermes gateway)
TELEGRAM_BOT_TOKEN=<from BotFather>

# Higgsfield browser profile (persistent login)
HIGGSFIELD_BROWSER_PROFILE_PATH=~/.hermes/browser-profiles/higgsfield
```

### hermes-config-snippet.yaml

```yaml
skills:
  external_dirs:
    - ${HOME}/HiggsfieldAgent/skills

  config:
    higgsfield-generate:
      browser_profile: ${HIGGSFIELD_BROWSER_PROFILE_PATH}
```

### get_aspect_ratio.py

- Input: image file path (CLI argument)
- Reads dimensions with Pillow
- Maps width/height ratio to the closest Higgsfield UI option
- Prints the aspect ratio string to stdout (e.g. "9:16")
- Single dependency: `Pillow`

### .hermes.md

Context file for Hermes describing the repo purpose and the skill. Instructs Hermes not to modify or create skills (source-controlled via git, same pattern as Streamax).

---

## Setup Checklist

1. Install Python 3.11+ and Pillow (`pip install Pillow`)
2. Set env vars in `~/.hermes/.env` (`TELEGRAM_BOT_TOKEN`, `HIGGSFIELD_BROWSER_PROFILE_PATH`)
3. Configure the Hermes Telegram gateway (`hermes gateway setup` or manual env vars)
4. Merge `config/hermes-config-snippet.yaml` into `~/.hermes/config.yaml`
5. Manually log into Higgsfield in the Hermes browser profile (one-time)
6. Test by sending an image to the Telegram bot

---

## Known Limitations & Future Work

- **Single account**: Only one Higgsfield account, so jobs are sequential. Concurrent requests queue.
- **No authentication**: Any Telegram user can trigger the bot. A `TELEGRAM_ALLOWED_USERS` whitelist will be added later.
- **Clipboard limitation**: Hermes browser tools use accessibility trees, not a real clipboard. The "Copy link" step needs to extract the URL from visible page elements (toast, dialog, URL field) rather than the system clipboard.
- **Center-crop only on Higgsfield**: The aspect ratio selection is best-effort based on the image dimensions. Higgsfield may crop differently than expected.
- **Browser session fragility**: If Higgsfield changes their UI layout, element references in the skill may break. The pre-generation checklist mitigates this by catching mismatches before generating.
- **15-minute timeout**: If Higgsfield is slow or under load, the 15-minute window may not be enough. This is a conservative starting point.
