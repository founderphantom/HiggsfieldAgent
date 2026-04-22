# Chrome Persistence — CDP Auto-Start Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `Browser.from_system_chrome()` with a CDP auto-start pattern so the agent reuses a persistent `~/.higgsfield-chrome` Chrome profile across all Telegram-triggered runs.

**Architecture:** `generate_fufu.py` gains an `ensure_chrome_ready()` helper that pings port 9222; if Chrome isn't running it launches it against `~/.higgsfield-chrome` and polls until ready. `run_generation()` attaches via `Browser(cdp_url=...)` and detaches without killing Chrome after each run. All hardcoded Windows paths in `SKILL.md` and config are updated to WSL-native paths.

**Tech Stack:** Python 3.11+, browser-use 0.12.6, httpx, pytest, Google Chrome (deb), WSL2 Ubuntu

---

### Task 1: Update requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Replace contents of requirements.txt**

```
browser-use==0.12.6
langchain-google-genai>=2.0.0
python-dotenv==1.2.1
Pillow==12.1.1
httpx>=0.27.0
pytest>=8.0.0
```

Removed: `langchain-openai` (unused — script uses `ChatGoogle`, not OpenAI)
Added: `langchain-google-genai` (backing package for `ChatGoogle`)
Added: `httpx` (CDP health-check in `ensure_chrome_ready`)
Added: `pytest` (pin test runner explicitly)

- [ ] **Step 2: Install and verify**

```bash
cd ~/HiggsfieldAgent
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import httpx; import langchain_google_genai; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: replace langchain-openai with langchain-google-genai, add httpx"
```

---

### Task 2: Discover browser-use 0.12.6 CDP API

**Files:**
- Read-only inspection — no files modified

The `Browser` constructor API changed between browser-use versions. Verify the correct form before writing code that depends on it.

- [ ] **Step 1: Inspect Browser constructor signature**

```bash
.venv/bin/python -c "
import inspect
from browser_use import Browser
print('=== Browser.__init__ ===')
print(inspect.signature(Browser.__init__))
"
```

- [ ] **Step 2: Check whether BrowserConfig exists**

```bash
.venv/bin/python -c "
try:
    from browser_use.browser.browser import BrowserConfig
    import inspect
    print('BrowserConfig found at browser_use.browser.browser')
    print(inspect.signature(BrowserConfig.__init__))
except ImportError:
    try:
        from browser_use import BrowserConfig
        import inspect
        print('BrowserConfig found at browser_use (top-level)')
        print(inspect.signature(BrowserConfig.__init__))
    except ImportError:
        print('No BrowserConfig — Browser takes direct kwargs')
"
```

- [ ] **Step 3: Check browser close/stop methods**

```bash
.venv/bin/python -c "
import inspect, asyncio
from browser_use import Browser
for name in ('close', 'stop'):
    if hasattr(Browser, name):
        m = getattr(Browser, name)
        print(f'{name}: {inspect.signature(m)}, is_coroutine={asyncio.iscoroutinefunction(m)}')
    else:
        print(f'{name}: NOT FOUND')
"
```

- [ ] **Step 4: Record findings before continuing**

You need two facts for Tasks 3 and 4:

**A) CDP constructor form** — one of:
- `Browser(cdp_url="http://localhost:9222")` — direct kwarg
- `Browser(config=BrowserConfig(cdp_url="http://localhost:9222"))` — config object

**B) Detach call** — one of:
- `await browser.close()` — if `close` exists and is a coroutine
- `await browser.stop()` — if only `stop` exists and is a coroutine
- `browser.close()` — if `close` exists and is synchronous

Use the exact forms found here in Tasks 3 and 4.

---

### Task 3: Add `ensure_chrome_ready()` with tests (TDD)

**Files:**
- Modify: `scripts/generate_fufu.py` (add function + imports only — do not touch `run_generation` yet)
- Create: `tests/test_generate_fufu.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_generate_fufu.py`:

```python
"""Tests for generate_fufu helper functions."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_fufu import ensure_chrome_ready


def test_already_running_does_not_launch_chrome():
    """If Chrome answers on the CDP port, return without launching a new process."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("httpx.get", return_value=mock_resp) as mock_get:
        with patch("subprocess.Popen") as mock_popen:
            ensure_chrome_ready("http://localhost:9222")
            mock_get.assert_called_once_with(
                "http://localhost:9222/json/version", timeout=2.0
            )
            mock_popen.assert_not_called()


def test_not_running_launches_chrome_with_correct_args():
    """If Chrome is not running, launch it with the required flags."""
    call_count = 0

    def fake_get(url, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection refused")
        resp = MagicMock()
        resp.status_code = 200
        return resp

    with patch("httpx.get", side_effect=fake_get):
        with patch("subprocess.Popen") as mock_popen:
            with patch("time.sleep"):
                ensure_chrome_ready("http://localhost:9222", timeout=5)

    mock_popen.assert_called_once()
    launched_args = mock_popen.call_args[0][0]
    assert launched_args[0] == "google-chrome"
    assert "--remote-debugging-port=9222" in launched_args
    assert any("--user-data-dir=" in a for a in launched_args)
    assert "--disable-blink-features=AutomationControlled" in launched_args


def test_timeout_raises_runtime_error():
    """Raise RuntimeError if Chrome never responds within the timeout window."""
    with patch("httpx.get", side_effect=httpx.ConnectError("connection refused")):
        with patch("subprocess.Popen"):
            with patch("time.sleep"):
                # timeout=-1 → deadline is already past → polling loop never runs
                with pytest.raises(RuntimeError, match="Chrome did not start in time"):
                    ensure_chrome_ready("http://localhost:9222", timeout=-1)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/HiggsfieldAgent
.venv/bin/pytest tests/test_generate_fufu.py -v
```

Expected: 3 failures with `ImportError: cannot import name 'ensure_chrome_ready'`

- [ ] **Step 3: Add imports and implement `ensure_chrome_ready()` in generate_fufu.py**

At the top of `scripts/generate_fufu.py`, add these imports after the existing ones:

```python
import subprocess
import time
from urllib.parse import urlparse

import httpx
```

Add this constant and function after the imports, before `get_aspect_ratio_for_image()`:

```python
_CHROME_PROFILE_DIR = str(Path.home() / ".higgsfield-chrome")


def ensure_chrome_ready(cdp_url: str = "http://localhost:9222", timeout: int = 10) -> None:
    """Ensure Chrome is listening on the CDP port, launching it if necessary.

    Attaches to an existing Chrome process if the port is already open.
    Launches Chrome against ~/.higgsfield-chrome otherwise and polls until ready.
    Never kills an existing Chrome process.

    Raises RuntimeError if Chrome does not respond within `timeout` seconds.
    """
    version_url = f"{cdp_url}/json/version"

    # Fast path: Chrome is already running.
    try:
        resp = httpx.get(version_url, timeout=2.0)
        if resp.status_code == 200:
            return
    except httpx.ConnectError:
        pass

    # Extract port from cdp_url so --remote-debugging-port matches.
    parsed = urlparse(cdp_url)
    port = parsed.port or 9222

    subprocess.Popen([
        "google-chrome",
        f"--user-data-dir={_CHROME_PROFILE_DIR}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ])

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(version_url, timeout=2.0)
            if resp.status_code == 200:
                return
        except httpx.ConnectError:
            pass
        time.sleep(1)

    raise RuntimeError(f"Chrome did not start in time (waited {timeout}s)")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_generate_fufu.py -v
```

Expected:

```
tests/test_generate_fufu.py::test_already_running_does_not_launch_chrome PASSED
tests/test_generate_fufu.py::test_not_running_launches_chrome_with_correct_args PASSED
tests/test_generate_fufu.py::test_timeout_raises_runtime_error PASSED

3 passed
```

- [ ] **Step 5: Run full test suite to check no regressions**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all pre-existing aspect-ratio tests still pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_fufu.py tests/test_generate_fufu.py
git commit -m "feat: add ensure_chrome_ready() with CDP auto-start and tests"
```

---

### Task 4: Refactor `run_generation()` and `main()`

**Files:**
- Modify: `scripts/generate_fufu.py`
- Modify: `tests/test_generate_fufu.py`

Use the CDP constructor form and detach method discovered in Task 2.

- [ ] **Step 1: Write a failing test for the refactored run_generation()**

Add to `tests/test_generate_fufu.py`:

```python
def test_run_generation_calls_ensure_chrome_ready():
    """run_generation() must call ensure_chrome_ready before attaching the browser."""
    with patch("generate_fufu.get_aspect_ratio_for_image", return_value="16:9"):
        with patch("generate_fufu.ensure_chrome_ready") as mock_ensure:
            with patch("generate_fufu.Browser") as mock_browser_cls:
                mock_browser = MagicMock()
                mock_browser.close = AsyncMock()
                mock_browser_cls.return_value = mock_browser

                with patch("generate_fufu.Agent") as mock_agent_cls:
                    mock_agent = MagicMock()
                    mock_agent_cls.return_value = mock_agent
                    mock_history = MagicMock()
                    mock_history.final_result.return_value = "FAILED: test"
                    mock_agent.run = AsyncMock(return_value=mock_history)

                    from generate_fufu import run_generation
                    asyncio.run(
                        run_generation("/fake/image.png", cdp_url="http://localhost:9222")
                    )

                    mock_ensure.assert_called_once_with("http://localhost:9222")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_generate_fufu.py::test_run_generation_calls_ensure_chrome_ready -v
```

Expected: FAIL — `run_generation` still accepts `chrome_profile`, not `cdp_url`

- [ ] **Step 3: Replace `run_generation()` in generate_fufu.py**

Replace the entire `run_generation` function with:

```python
async def run_generation(image_path: str, cdp_url: str = "http://localhost:9222") -> dict:
    """Run the Higgsfield generation workflow using browser-use."""
    load_dotenv()

    aspect_ratio = get_aspect_ratio_for_image(image_path)
    task = build_task(image_path, aspect_ratio)

    llm = ChatGoogle(model="gemini-3.1-flash-lite-preview")

    ensure_chrome_ready(cdp_url)

    # Attach to the running Chrome via CDP.
    # Use the constructor form confirmed in Task 2:
    #   Direct kwarg:   Browser(cdp_url=cdp_url)
    #   Config object:  Browser(config=BrowserConfig(cdp_url=cdp_url))
    browser = Browser(cdp_url=cdp_url)

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        available_file_paths=[image_path],
        use_vision=True,
        max_failures=3,
    )

    try:
        history = await agent.run()
        return parse_result(history.final_result())
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        # Detach only — do not kill Chrome. The same process handles the next call.
        # Use the detach method confirmed in Task 2 (close or stop).
        await browser.close()
```

⚠️ If Task 2 showed `Browser` requires a `BrowserConfig` config object, replace
`Browser(cdp_url=cdp_url)` with `Browser(config=BrowserConfig(cdp_url=cdp_url))`.
If Task 2 showed `close()` is synchronous (not a coroutine), replace
`await browser.close()` with `browser.close()`. If only `stop()` exists, use that.

- [ ] **Step 4: Replace `main()` in generate_fufu.py**

Replace the entire `main()` function with:

```python
def main():
    parser = argparse.ArgumentParser(description="Generate FUFU variations on Higgsfield")
    parser.add_argument("image_path", help="Path to the inspiration image")
    parser.add_argument(
        "--cdp-url",
        default="http://localhost:9222",
        help="Chrome DevTools Protocol endpoint (default: http://localhost:9222)",
    )
    args = parser.parse_args()

    image_path = str(Path(args.image_path).resolve())
    if not Path(image_path).exists():
        print(json.dumps({"status": "error", "message": f"Image not found: {image_path}"}))
        sys.exit(1)

    result = asyncio.run(run_generation(image_path, cdp_url=args.cdp_url))
    print(json.dumps(result))

    if result["status"] != "success":
        sys.exit(1)
```

- [ ] **Step 5: Run all tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all 4 generate_fufu tests and all aspect-ratio tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_fufu.py tests/test_generate_fufu.py
git commit -m "feat: refactor run_generation to CDP auto-start, remove from_system_chrome"
```

---

### Task 5: Update SKILL.md

**Files:**
- Modify: `skills/higgsfield-generate/SKILL.md`

- [ ] **Step 1: Update the REPO_ROOT bash command in Phase 2**

Replace:
```bash
"$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/generate_fufu.py" "IMAGE_PATH" --chrome-profile "Default"
```
With:
```bash
"$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/generate_fufu.py" "IMAGE_PATH" --cdp-url http://localhost:9222
```

- [ ] **Step 2: Update the alternative hardcoded path block**

Replace:
```bash
/mnt/c/Users/Mallika/Documents/HiggsfieldAgent/.venv/bin/python \
  /mnt/c/Users/Mallika/Documents/HiggsfieldAgent/scripts/generate_fufu.py \
  "IMAGE_PATH" --chrome-profile "Default"
```
With:
```bash
~/HiggsfieldAgent/.venv/bin/python \
  ~/HiggsfieldAgent/scripts/generate_fufu.py \
  "IMAGE_PATH" --cdp-url http://localhost:9222
```

- [ ] **Step 3: Replace the Environment Setup Chrome bullet**

Replace:
```markdown
- **Google Chrome** installed with a profile that is logged into Higgsfield.
  The script uses your system Chrome with persistent cookies — log into
  Higgsfield once in Chrome and the session persists across runs.

- **Chrome must be fully closed** before running the script (browser-use
  launches Chrome with the specified profile, which conflicts if Chrome is
  already using that profile).
```
With:
```markdown
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
```

- [ ] **Step 4: Remove "Chrome must be closed" pitfall, update "Session expired", add "Chrome not starting"**

Remove this pitfall entirely:
```markdown
- **Chrome must be closed**: browser-use cannot connect to a Chrome profile
  that is already in use. Close all Chrome windows before generation starts.
```

Replace the Session expired pitfall with:
```markdown
- **Session expired**: If Higgsfield login has expired, re-login manually:
  ```bash
  google-chrome --user-data-dir="$HOME/.higgsfield-chrome" --no-first-run https://higgsfield.ai
  ```
  Sign in with Google, confirm you're on Higgsfield's logged-in page, close Chrome, then retry.
```

Add after the session expired pitfall:
```markdown
- **Chrome not starting**: If the script raises "Chrome did not start in time",
  verify `~/.higgsfield-chrome` exists and `google-chrome` is on your PATH
  (`which google-chrome`). Install Chrome with:
  ```bash
  cd /tmp && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  sudo apt install -y ./google-chrome-stable_current_amd64.deb
  ```
```

- [ ] **Step 5: Commit**

```bash
git add skills/higgsfield-generate/SKILL.md
git commit -m "docs: update SKILL.md for CDP auto-start and WSL-native paths"
```

---

### Task 6: Update config/hermes-config-snippet.yaml and .hermes.md

**Files:**
- Modify: `config/hermes-config-snippet.yaml`
- Modify: `.hermes.md`

- [ ] **Step 1: Update hermes-config-snippet.yaml**

Replace:
```yaml
skills:
  external_dirs:
    - /mnt/c/Users/Mallika/Documents/HiggsfieldAgent/skills

  config:
    higgsfield-generate:
      chrome_profile: Default
```
With:
```yaml
skills:
  external_dirs:
    - /home/mallika/HiggsfieldAgent/skills
```

(The `chrome_profile` config key is removed — CDP URL is hardcoded in SKILL.md with a default.)

- [ ] **Step 2: Update .hermes.md key paths section**

Replace:
```markdown
## Key Paths

- `skills/higgsfield-generate/` — Hermes skill for the full generation workflow
- `scripts/get_aspect_ratio.py` — helper to detect image aspect ratio
- `config/hermes-config-snippet.yaml` — merge into ~/.hermes/config.yaml
```
With:
```markdown
## Key Paths

- `skills/higgsfield-generate/` — Hermes skill for the full generation workflow
- `scripts/generate_fufu.py` — browser-use automation script (CDP auto-start)
- `scripts/get_aspect_ratio.py` — helper to detect image aspect ratio
- `config/hermes-config-snippet.yaml` — merge into ~/.hermes/config.yaml

## Repo Location

This repo lives at `~/HiggsfieldAgent` in WSL Ubuntu. All skill paths and
script paths are relative to that WSL-native location.
```

- [ ] **Step 3: Commit**

```bash
git add config/hermes-config-snippet.yaml .hermes.md
git commit -m "chore: update paths from Windows mount to WSL-native ~/HiggsfieldAgent"
```

---

### Task 7: Push and Verify

- [ ] **Step 1: Push all commits**

```bash
git push origin main
```

- [ ] **Step 2: Run full test suite one final time**

```bash
.venv/bin/pytest tests/ -v
```

Expected (all passing):
```
tests/test_generate_fufu.py::test_already_running_does_not_launch_chrome PASSED
tests/test_generate_fufu.py::test_not_running_launches_chrome_with_correct_args PASSED
tests/test_generate_fufu.py::test_timeout_raises_runtime_error PASSED
tests/test_generate_fufu.py::test_run_generation_calls_ensure_chrome_ready PASSED
tests/test_get_aspect_ratio.py::test_square_image PASSED
tests/test_get_aspect_ratio.py::test_portrait_9_16 PASSED
tests/test_get_aspect_ratio.py::test_landscape_16_9 PASSED
tests/test_get_aspect_ratio.py::test_portrait_3_4 PASSED
tests/test_get_aspect_ratio.py::test_landscape_4_3 PASSED
tests/test_get_aspect_ratio.py::test_portrait_2_3 PASSED
tests/test_get_aspect_ratio.py::test_landscape_3_2 PASSED
tests/test_get_aspect_ratio.py::test_near_square_rounds_to_1_1 PASSED
tests/test_get_aspect_ratio.py::test_iphone_photo_maps_to_3_4 PASSED
tests/test_get_aspect_ratio.py::test_ultrawide_maps_to_16_9 PASSED
tests/test_get_aspect_ratio.py::test_missing_file_exits_nonzero PASSED
```

- [ ] **Step 3: Smoke test on hosting machine after git pull**

After cloning/pulling on the WSL hosting machine:
```bash
cd ~/HiggsfieldAgent
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/generate_fufu.py --help
```

Expected: usage printed with `--cdp-url` argument visible, no `--chrome-profile`.

```bash
# With a real image (Chrome will auto-start via WSLg on first run):
.venv/bin/python scripts/generate_fufu.py /path/to/test-image.jpg
```

Expected: Chrome window opens in WSLg, navigates to Higgsfield already logged in,
runs the full generation workflow, prints JSON result to stdout.
