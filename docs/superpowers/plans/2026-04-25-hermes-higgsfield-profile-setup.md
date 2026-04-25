# Hermes Higgsfield Profile — Second Computer Setup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up a `higgsfield` Hermes profile on a second computer that listens on Telegram. When the user sends one or more photos, the agent runs `scripts/higgsfield_api.py` on each image (one at a time), and sends all 4 generated PNG variations back to the user on Telegram before moving on to the next photo. Gmail is used to auto-fetch the Higgsfield OTP on first login — no manual code entry needed.

**Architecture:** Single Hermes profile (`higgsfield`) with a custom skill (`higgsfield-fufu`) and the bundled Google Workspace skill for Gmail access. On the very first run, `HIGGSFIELD_AUTO_OTP=1` tells `higgsfield_api.py` to poll Gmail via `$GAPI` for the verification code instead of blocking on stdin. After the session is cached, OTP is never needed again.

**Tech Stack:** Hermes Agent (v2026.4.16), Python 3.11+, `scripts/higgsfield_api.py` (this repo), Telegram gateway, Google Workspace skill (`$GAPI`)

**Reference:** `scripts/higgsfield_api.py`, `tests/test_higgsfield_api.py`

---

## Prerequisites (done on main computer)

- `scripts/higgsfield_api.py` is complete and end-to-end tested ✅
- Output contract: `{"status": "success", "links": [...], "local_paths": [...]}` ✅
- `HIGGSFIELD_AUTO_OTP=1` env var support added to `login_full()` — polls Gmail via `$GAPI` subprocess ✅

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
│                                   # + HIGGSFIELD_EMAIL + HIGGSFIELD_PASSWORD
│                                   # + HIGGSFIELD_AUTO_OTP=1
├── config.yaml                     # profile config
└── skills/
    └── higgsfield-fufu/
        └── SKILL.md                # the skill (written in Task 6)
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
# OR copy from main computer via scp:
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

- [ ] **Step 3: Add Higgsfield credentials, auto-OTP flag, and both user IDs to profile .env**

```bash
cat >> ~/.hermes/profiles/higgsfield/.env << 'EOF'
HIGGSFIELD_EMAIL=founder@phantomsys.dev
HIGGSFIELD_PASSWORD=<password>
HIGGSFIELD_AUTO_OTP=1
# Both users who will send photos in the group chat (comma-separated)
TELEGRAM_ALLOWED_USERS=5938713749,1004169493
EOF
```

  Group chat ID: `-5151614924` (already set in `config/hermes-config-snippet.yaml`).

---

## Task 4: Set up Google Workspace (Gmail OAuth)

This enables `$GAPI` — the Hermes CLI that reads your Gmail inbox. Required for auto-fetching the Higgsfield OTP on first login.

- [ ] **Step 1: Create a Google Cloud project and OAuth credentials**

  1. Go to [console.cloud.google.com](https://console.cloud.google.com)
  2. Create a new project (e.g. `hermes-higgsfield`)
  3. Enable the **Gmail API**: APIs & Services → Library → search "Gmail API" → Enable
  4. Go to APIs & Services → **Credentials** → Create Credentials → **OAuth 2.0 Client ID**
  5. Application type: **Desktop app** → name it anything → Create
  6. Download the generated JSON file (e.g. `client_secret_xxxx.json`)

- [ ] **Step 2: Add yourself as a test user (required while app is in testing)**

  1. APIs & Services → **OAuth consent screen** → **Test users** → Add Users
  2. Add: `founder@phantomsys.dev`

- [ ] **Step 3: Register the client secret with the higgsfield profile**

```bash
hermes -p higgsfield chat -q "$GSETUP --client-secret ~/Downloads/client_secret_xxxx.json"
```

- [ ] **Step 4: Authorize Gmail access**

```bash
hermes -p higgsfield chat -q "$GSETUP --auth-url --services email --format json"
```

  The command returns a `auth_url`. Open it in a browser, sign in as `founder@phantomsys.dev`, and grant access. The browser will redirect to `http://localhost:1` and show an error — that's expected. Copy the full redirect URL from the address bar and paste it back into the chat.

- [ ] **Step 5: Verify Gmail access works**

```bash
hermes -p higgsfield chat -q '$GAPI gmail search "is:unread" --max 3'
```

  Should return a JSON array of recent emails.

---

## Task 5: Configure the profile

- [ ] **Step 1: Set `terminal.cwd` and enable Telegram reactions**

Edit `~/.hermes/profiles/higgsfield/config.yaml`:

```yaml
terminal:
  cwd: ~/HiggsfieldAgent

telegram:
  reactions: true          # shows 👀 while processing, ✅ on success, ❌ on error
```

---

## Task 6: Write the `higgsfield-fufu` skill

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

2. **Inform the user upfront** before starting any generation:
   > "Generating 4 variations — this takes about 8 minutes ⏳"
   
   If multiple photos: "Processing N photos — about 8 minutes each ⏳"

3. **Check if this is a first-time login.** If `~/.higgsfield_session` does not exist, the script will perform a full login and auto-fetch the OTP from Gmail (`HIGGSFIELD_AUTO_OTP=1` is already set in the profile `.env`). No action needed — it's fully automatic.

4. **Process each photo one at a time.** For every photo path (in order):

   a. Run the generation script:
   ```bash
   HIGGSFIELD_AUTO_OTP=1 python3 ~/HiggsfieldAgent/scripts/higgsfield_api.py "<photo_path>"
   ```

   b. Parse the JSON result from stdout:
   - On `"status": "error"` — reply with the error message and continue to the next photo.
   - On `"status": "success"` — extract `local_paths` (list of 4 PNG file paths) and `links` (4 share URLs).

   c. Send each of the 4 files in `local_paths` back to the user as Telegram **photos** (not documents). Caption the first image:
   ```
   Generated 4 variations ✅
   1. <links[0]>
   2. <links[1]>
   3. <links[2]>
   4. <links[3]>
   ```

   d. When processing multiple photos, announce progress before each one:
   > "Processing photo 2 of 3…"

## Pitfalls

- **Auto-OTP Gmail polling:** The script polls Gmail every 10 seconds for up to 2 minutes after sending the OTP email. If the email doesn't arrive in time, the script will raise a `RuntimeError`. Retry once — it usually arrives within 30 seconds.
- **Generation takes ~8 minutes.** Always set user expectations before running. Don't wait in silence.
- **Multiple photos in one message.** Process sequentially — running them in parallel would exhaust Higgsfield credits and cause upload collisions.
- **Script not found.** Confirm `~/HiggsfieldAgent/scripts/higgsfield_api.py` exists and the repo is cloned.
- **`$GAPI` not found.** Ensure the Google Workspace skill OAuth setup (Task 4) was completed and `$GAPI` resolves correctly in the profile shell environment.

## Verification

- The script exits 0 and prints `{"status": "success", ...}` to stdout.
- 4 PNG files appear in the same directory as the input photo (`photo_out_1.png` … `photo_out_4.png`).
- All 4 images are delivered to the user on Telegram with share link captions.
```

---

## Task 7: Start the gateway and test

- [ ] **Step 1: Start the Hermes gateway for the higgsfield profile**

```bash
hermes -p higgsfield gateway start
```

  Or as a background daemon:

```bash
hermes -p higgsfield gateway start --daemon
```

- [ ] **Step 2: Send a test photo from Telegram**

  - Open Telegram, message your bot
  - Send a photo
  - Expected: bot replies "Generating 4 variations — this takes about 8 minutes ⏳"
  - On first run: script auto-fetches OTP from Gmail (no terminal input needed)
  - After ~8 minutes: 4 PNG images delivered + share links in caption

- [ ] **Step 3: Test multi-photo batch**

  - Send 2 photos in the same message
  - Confirm the bot processes them one at a time, delivering 4 images per photo (8 total)

---

## Task 8: (Optional) Run gateway as a system service

To keep the gateway running after SSH disconnect or reboot:

```bash
# Using systemd (Linux/WSL)
hermes -p higgsfield gateway install-service
systemctl --user enable hermes-higgsfield
systemctl --user start hermes-higgsfield
```

Or using tmux:

```bash
tmux new-session -d -s higgsfield 'hermes -p higgsfield gateway start'
```
