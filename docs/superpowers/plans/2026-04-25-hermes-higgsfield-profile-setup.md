# Hermes Higgsfield Profile — Second Computer Setup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up a `higgsfield` Hermes profile on a second computer that listens on Telegram. When the user sends one or more photos, the agent runs `scripts/higgsfield_api.py` on each image (one at a time), and sends all 4 generated PNG variations back to the user on Telegram before moving on to the next photo.

**Architecture:** Single Hermes profile (`higgsfield`) with a custom skill (`higgsfield-fufu`). No browser toolset needed — `higgsfield_api.py` handles the full pipeline directly. The Telegram gateway receives the photo, saves it locally, runs the script as a subprocess, reads `local_paths` from the JSON output, and sends each image file back via the native Telegram delivery.

**Tech Stack:** Hermes Agent (v2026.4.16), Python 3.11+, `scripts/higgsfield_api.py` (this repo), Telegram gateway

**Reference:** `scripts/higgsfield_api.py`, `tests/test_higgsfield_api.py`

---

## Prerequisites (done on main computer)

- `scripts/higgsfield_api.py` is complete and end-to-end tested ✅
- Output contract: `{"status": "success", "links": [...], "local_paths": [...]}` ✅
- Cached Higgsfield session at `~/.higgsfield_session` (JSON format with `session_id` + `client_cookie`) — the first run on the second computer will require one OTP login, after which the session is cached

---

## File Structure (on second computer)

```
~/HiggsfieldAgent/                  # cloned repo
├── scripts/
│   ├── higgsfield_api.py
│   └── get_aspect_ratio.py
├── .env                            # HIGGSFIELD_EMAIL + HIGGSFIELD_PASSWORD
└── ...

~/.hermes/profiles/higgsfield/
├── .env                            # TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USERS
├── config.yaml                     # profile config
└── skills/
    └── higgsfield-fufu/
        └── SKILL.md                # the skill (written in Task 5)
```

---

## Task 1: Install Hermes Agent

- [ ] **Step 1: Clone and install**

```bash
git clone https://github.com/NousResearch/hermes-agent.git ~/hermes-agent
cd ~/hermes-agent
./setup-hermes.sh
```

- [ ] **Step 2: Verify install**

```bash
hermes --version
```

---

## Task 2: Clone the HiggsfieldAgent repo

- [ ] **Step 1: Clone**

```bash
git clone <your-remote-url> ~/HiggsfieldAgent
# OR copy from main computer if no remote:
# scp -r /path/to/HiggsfieldAgent user@second-computer:~/HiggsfieldAgent
```

- [ ] **Step 2: Install Python dependencies**

```bash
cd ~/HiggsfieldAgent
python3 -m pip install "curl_cffi>=0.7.0" python-dotenv Pillow --break-system-packages
```

- [ ] **Step 3: Create .env**

```bash
cat > ~/HiggsfieldAgent/.env << 'EOF'
HIGGSFIELD_EMAIL=founder@phantomsys.dev
HIGGSFIELD_PASSWORD=<password>
EOF
```

- [ ] **Step 4: Smoke test the script (will prompt for OTP on first run)**

```bash
# Copy a test photo over, then:
python3 ~/HiggsfieldAgent/scripts/higgsfield_api.py ~/HiggsfieldAgent/tests/photo.jpg
```

  After entering the OTP once, `~/.higgsfield_session` is saved. Subsequent runs skip the OTP entirely.

---

## Task 3: Create the `higgsfield` Hermes profile

- [ ] **Step 1: Create the profile**

```bash
hermes profile create higgsfield
```

- [ ] **Step 2: Run the setup wizard for the profile**

```bash
hermes -p higgsfield setup
```

  During setup, configure:
  - Model: any capable model (Claude Sonnet or similar)
  - Gateway: Telegram
  - Paste the `TELEGRAM_BOT_TOKEN` from BotFather
  - Paste your `TELEGRAM_ALLOWED_USERS` (numeric user ID)

- [ ] **Step 3: Verify the profile .env was written**

```bash
cat ~/.hermes/profiles/higgsfield/.env
# Should contain TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS
```

---

## Task 4: Configure the profile

- [ ] **Step 1: Set `terminal.cwd` so the agent always operates from the repo**

Edit `~/.hermes/profiles/higgsfield/config.yaml`:

```yaml
terminal:
  cwd: ~/HiggsfieldAgent

telegram:
  reactions: true          # shows 👀 while processing, ✅ on success, ❌ on error
```

---

## Task 5: Write the `higgsfield-fufu` skill

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p ~/.hermes/profiles/higgsfield/skills/higgsfield-fufu
```

- [ ] **Step 2: Write the SKILL.md**

Create `~/.hermes/profiles/higgsfield/skills/higgsfield-fufu/SKILL.md`:

```markdown
---
name: higgsfield-fufu
description: When the user sends one or more photos on Telegram, generate 4 Higgsfield FUFU Soul v2 variations for each image and send the results back.
version: 1.0.0
platforms: [linux, macos, windows]
required_environment_variables:
  - name: HIGGSFIELD_EMAIL
    prompt: Higgsfield account email
    required_for: image generation
  - name: HIGGSFIELD_PASSWORD
    prompt: Higgsfield account password
    required_for: image generation
metadata:
  hermes:
    tags: [Image Generation, Higgsfield, Telegram, FUFU]
---

# Higgsfield FUFU Generator

Generates 4 Soul v2 FUFU character variations from an inspiration photo using the Higgsfield API.

## When to Use

Activate this skill whenever the user sends a photo or image file on Telegram — including when they send multiple photos in one message or across successive messages asking for generation.

## Procedure

1. **Receive photos.** The user's sent photo(s) are available as local file paths from the Telegram gateway. Each attached image is already saved to a temp path.

2. **Process each photo one at a time.** For every photo path (in order):

   a. Run the generation script:
   ```bash
   python3 ~/HiggsfieldAgent/scripts/higgsfield_api.py "<photo_path>"
   ```

   b. The script writes a JSON result to stdout. Parse it:
   - On `"status": "error"` — reply to the user with the error message and continue to the next photo.
   - On `"status": "success"` — extract `local_paths` (list of 4 PNG file paths).

   c. Send each of the 4 files in `local_paths` back to the user as Telegram photos (not as documents). Use the share links from `links` as the caption for the first image, e.g.:
   ```
   Generated 4 variations ✅
   1. <links[0]>
   2. <links[1]>
   3. <links[2]>
   4. <links[3]>
   ```

   d. Inform the user of progress when processing multiple photos:
   > "Processing photo 2 of 3…"

3. **First-run note.** On the very first run after install the script will prompt for an email OTP. This only happens once — the session is cached in `~/.higgsfield_session`. If you see an EOF error, tell the user to run the script manually once in the terminal to complete the one-time login.

## Pitfalls

- **EOF / OTP prompt on first run:** The session cache doesn't exist yet. Run `python3 ~/HiggsfieldAgent/scripts/higgsfield_api.py tests/photo.jpg` once in a real terminal and enter the OTP code. After that, all Hermes-triggered runs will skip OTP.
- **Generation takes ~8 minutes.** Set user expectations upfront: reply with "Generating 4 variations — this takes about 8 minutes ⏳" before starting the script.
- **Multiple photos in one message.** Process sequentially — do not attempt to run them in parallel (each run uses Higgsfield credits and a separate upload slot).
- **Script not found.** Confirm `~/HiggsfieldAgent/scripts/higgsfield_api.py` exists. The repo must be cloned on this machine.

## Verification

- The script exits 0 and prints `{"status": "success", ...}` to stdout.
- 4 PNG files appear in the same directory as the input photo (`photo_out_1.png` … `photo_out_4.png`).
- All 4 images are delivered to the user on Telegram.
```

---

## Task 6: Start the gateway and test

- [ ] **Step 1: Start the Hermes gateway for the higgsfield profile**

```bash
hermes -p higgsfield gateway start
```

  Or to run as a background service:

```bash
hermes -p higgsfield gateway start --daemon
```

- [ ] **Step 2: Send a test photo from Telegram**

  - Open Telegram, message your bot
  - Send a photo
  - Expected bot response: "Generating 4 variations — this takes about 8 minutes ⏳"
  - After ~8 minutes: 4 PNG images delivered + share links in caption

- [ ] **Step 3: Test multi-photo batch**

  - Send 2 photos in the same message
  - Confirm the bot processes them sequentially and delivers 4 images per photo (8 total)

---

## Task 7: (Optional) Run gateway as a system service

To keep the gateway running after SSH disconnect or reboot:

```bash
# Using systemd (Linux)
hermes -p higgsfield gateway install-service
systemctl --user enable hermes-higgsfield
systemctl --user start hermes-higgsfield
```

Or using a simple tmux session:

```bash
tmux new-session -d -s higgsfield 'hermes -p higgsfield gateway start'
```
