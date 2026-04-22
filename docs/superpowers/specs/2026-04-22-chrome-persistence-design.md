# Chrome Persistence Design — Higgsfield Agent

**Date:** 2026-04-22  
**Status:** Approved

## Problem

`generate_fufu.py` uses `Browser.from_system_chrome()` which resolves to
`~/.config/google-chrome/Default` in WSL — a profile that has never logged into
Higgsfield. Every run starts with no session cookies, causing the agent to hit the
login screen and fail. Additionally, the repo lives on the Windows filesystem
(`/mnt/c/...`), which adds path complexity and I/O overhead for a Python process
running in WSL.

## Approach: CDP Auto-Start with Dedicated Profile

On each generation run, `generate_fufu.py` checks whether Chrome is already
listening on port 9222. If it is, it attaches. If not, it launches Chrome against
a dedicated profile dir (`~/.higgsfield-chrome`) with remote debugging enabled,
waits up to 10 seconds for it to be ready, then attaches. Chrome is never killed
at the end of a run — it stays alive so subsequent Telegram calls attach instantly.

The Google sign-in is done once, manually, in a headful Chrome window using that
same profile dir. The agent never touches the Google sign-in form.

## One-Time Manual Setup (on hosting machine)

```bash
# Clone to WSL-native filesystem
cd ~
git clone https://github.com/founderphantom/HiggsfieldAgent

# Python venv
cd ~/HiggsfieldAgent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Copy or recreate .env with GOOGLE_API_KEY
cp /mnt/c/Users/Mallika/Documents/HiggsfieldAgent/.env ~/HiggsfieldAgent/.env

# Install Google Chrome (deb, not snap)
cd /tmp && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb

# Create profile dir and log in once manually
mkdir -p ~/.higgsfield-chrome
google-chrome --user-data-dir="$HOME/.higgsfield-chrome" --no-first-run https://higgsfield.ai
# Sign in with Google, confirm logged into Higgsfield, close Chrome cleanly
```

When Google session expires: repeat only the last step.

## Files Changed

### `scripts/generate_fufu.py`

**New helper — `ensure_chrome_ready(cdp_url: str)`:**
- HTTP GET `{cdp_url}/json/version` using `httpx`
- If 200 → Chrome is running, return immediately
- If connection refused → launch subprocess:
  ```
  google-chrome
    --user-data-dir=~/.higgsfield-chrome
    --remote-debugging-port=9222
    --no-first-run --no-default-browser-check
    --disable-blink-features=AutomationControlled
  ```
- Poll `/json/version` every 1s for up to 10s
- Raise `RuntimeError("Chrome did not start in time")` if never responds

**`run_generation()` changes:**
- Signature: replace `chrome_profile: str | None` → `cdp_url: str = "http://localhost:9222"`
- Call `ensure_chrome_ready(cdp_url)` at the top of the function
- Replace `Browser.from_system_chrome(...)` → `Browser(cdp_url=cdp_url)`
- `finally` block: call `await browser.close()` to detach — **do not kill the Chrome process**

**`main()` args:**
- Remove `--chrome-profile`
- Add `--cdp-url` (default `http://localhost:9222`)

### `requirements.txt`

- Add `langchain-google-genai` (required by `ChatGoogle`)
- Add `httpx` (CDP health check)
- Remove `langchain-openai` (unused)

### `skills/higgsfield-generate/SKILL.md`

- Update bash command: `--chrome-profile "Default"` → `--cdp-url http://localhost:9222`
- Update hardcoded path: `/mnt/c/Users/Mallika/Documents/HiggsfieldAgent/` → `~/HiggsfieldAgent/`
- Remove "Chrome must be fully closed" pitfall
- Update "Session expired" recovery: run manual login command, retry
- Add "Chrome not starting" pitfall: verify `~/.higgsfield-chrome` exists and `google-chrome` is on PATH

### `config/hermes-config-snippet.yaml`

- `external_dirs`: `/mnt/c/Users/Mallika/Documents/HiggsfieldAgent/skills` → `/home/mallika/HiggsfieldAgent/skills`
- Remove `chrome_profile` key under `skills.config.higgsfield-generate`

### `.hermes.md`

- Update key path reference from Windows path to WSL-native path

## Architecture Invariants

- Chrome process is shared across all Telegram-triggered runs — one instance, always on
- The `~/.higgsfield-chrome` dir is for the agent only — never open regular Chrome against it
- Google sign-in is always done manually — the agent never handles the Google OAuth flow
- `generate_fufu.py` is the sole owner of browser lifecycle; SKILL.md just invokes it
