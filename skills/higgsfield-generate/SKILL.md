---
name: higgsfield-generate
description: Generate FUFU character variations on Higgsfield from a Telegram inspiration image.
version: 2.0.0
metadata:
  hermes:
    tags: [image-generation, higgsfield, telegram, browser-automation]
    category: creative
    config:
      - key: chrome_profile
        description: "Chrome profile directory name for Higgsfield login persistence"
        default: "Default"
        prompt: "Chrome profile name (e.g. Default, Profile 1)"
---

# Higgsfield FUFU Generator

Generate 4 FUFU character variations from an inspiration image using Higgsfield's
Soul v2 web app via browser-use, then send the share links back to the user on Telegram.

## When to Use

Use this skill when a user sends a photo/image in a Telegram chat. The image is the
inspiration reference for Higgsfield generation.

If the user sends a text message with no image, reply with:
"Send me an image and I'll generate FUFU variations on Higgsfield."

## Procedure

### Phase 1: Confirm and Prepare

1. Send a message to the user on Telegram:
   "Got your image! Starting Higgsfield FUFU generation — this takes about 10-15 minutes."

2. Save the image attachment from the Telegram message to a local file path. Note
   this path as `IMAGE_PATH`.

### Phase 2: Run Generation

3. Determine the repo root path. The skill directory is located at
   `<REPO_ROOT>/skills/higgsfield-generate/`. The repo root is two levels up
   from this SKILL.md file. Run the browser-use generation script:
   ```bash
   REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
   "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/generate_fufu.py" "IMAGE_PATH" --cdp-url http://localhost:9222
   ```
   
   Alternatively, if the repo is at a known path, use it directly:
   ```bash
   ~/HiggsfieldAgent/.venv/bin/python \
     ~/HiggsfieldAgent/scripts/generate_fufu.py \
     "IMAGE_PATH" --cdp-url http://localhost:9222
   ```

   The script outputs JSON to stdout:
   - Success: `{"status": "success", "links": ["url1", "url2", "url3", "url4"]}`
   - Error: `{"status": "error", "message": "..."}`

   The script handles the entire browser workflow:
   - Navigates to Higgsfield Soul v2
   - Selects Image Reference tab and FUFU character (Soul 2.0 category)
   - Uploads the user's image
   - Selects the closest aspect ratio to the image dimensions
   - Sets Batch Size = 4, Quality = 2K
   - Validates all settings before generation
   - Clicks Generate and waits for results
   - Extracts share links from the 4 generated images

   **This takes 10-15 minutes.** Do not interrupt or timeout early.

### Phase 3: Handle Result

4. Parse the JSON output from the script.

5. **If status is "success"**: Send the links to the user on Telegram:
   ```
   Your FUFU generations are ready!

   1. {links[0]}
   2. {links[1]}
   3. {links[2]}
   4. {links[3]}
   ```

6. **If status is "error"**: Send the error to the user on Telegram:
   ```
   Generation failed: {message}
   ```

## Environment Setup

The generation script requires:

- **Python venv** at `.venv/` in the repo root with dependencies installed:
  ```bash
  python3 -m venv .venv
  pip install -r requirements.txt
  ```

- **GOOGLE_API_KEY** environment variable (set in `.env` at repo root)

- **Google Chrome** installed (deb package, not snap) at `/usr/bin/google-chrome`.
  A dedicated profile at `~/.higgsfield-chrome` must exist and be logged into
  Higgsfield. The script auto-starts Chrome if it is not already running and
  reuses it across Telegram calls — Chrome stays alive between messages.

  One-time login setup:
  ```bash
  mkdir -p ~/.higgsfield-chrome
  google-chrome --user-data-dir="$HOME/.higgsfield-chrome" --no-first-run https://higgsfield.ai
  # Sign in with Google, confirm logged into Higgsfield, close Chrome cleanly
  ```

## Pitfalls

- **Blank page on load**: Higgsfield sometimes loads with a completely blank
  UI (no tabs, no controls). The script handles this by refreshing up to 2
  times automatically. If it still fails, the error message will say
  "Page loaded blank after multiple refreshes" — just retry the generation.


- **Session expired**: If Higgsfield login has expired, re-login manually:
  ```bash
  google-chrome --user-data-dir="$HOME/.higgsfield-chrome" --no-first-run https://higgsfield.ai
  ```
  Sign in with Google, confirm you're on Higgsfield's logged-in page, close Chrome, then retry.

- **Chrome not starting**: If the script raises "Chrome did not start in time",
  verify `~/.higgsfield-chrome` exists and `google-chrome` is on your PATH
  (`which google-chrome`). Install Chrome with:
  ```bash
  cd /tmp && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  sudo apt install -y ./google-chrome-stable_current_amd64.deb
  ```

- **Long generation time**: Higgsfield takes 8-10 minutes to generate 4
  images at 2K quality. The script waits up to 15 minutes total.

- **Rate limits**: Higgsfield may throttle generation requests. If the
  script returns a rate limit error, wait and try again later.

## Verification

After sending the 4 links to Telegram, the skill is complete. The user can
click each link to verify the generated images on Higgsfield.
