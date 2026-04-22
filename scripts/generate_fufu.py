#!/usr/bin/env python3
"""Generate FUFU character variations on Higgsfield using browser-use.

Usage:
    python generate_fufu.py <image_path> [--cdp-url <url>]

Output (stdout JSON):
    {"status": "success", "links": ["url1", "url2", "url3", "url4"]}
    {"status": "error", "message": "..."}

Requires env vars:
    GOOGLE_API_KEY  — for Gemini LLM driving browser-use
"""
import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from browser_use import Agent, Browser, ChatGoogle
from get_aspect_ratio import closest_ratio

from PIL import Image


_CHROME_PROFILE_DIR = str(Path.home() / ".higgsfield-chrome")


def _chrome_is_up(version_url: str) -> bool:
    """Return True if Chrome is answering on the CDP version endpoint."""
    try:
        return httpx.get(version_url, timeout=2.0).status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return False


def ensure_chrome_ready(cdp_url: str = "http://localhost:9222", timeout: int = 10) -> None:
    """Ensure Chrome is listening on the CDP port, launching it if necessary.

    Attaches to an existing Chrome process if the port is already open.
    Launches Chrome against ~/.higgsfield-chrome otherwise and polls until ready.
    Never kills an existing Chrome process.

    Raises RuntimeError if Chrome does not respond within `timeout` seconds.
    """
    version_url = f"{cdp_url}/json/version"

    if _chrome_is_up(version_url):
        return

    parsed = urlparse(cdp_url)
    port = parsed.port or 9222

    try:
        subprocess.Popen(
            [
                "google-chrome",
                f"--user-data-dir={_CHROME_PROFILE_DIR}",
                f"--remote-debugging-port={port}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "google-chrome not found on PATH. "
            "Install with: sudo apt install ./google-chrome-stable_current_amd64.deb"
        )

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _chrome_is_up(version_url):
            return
        time.sleep(1)

    raise RuntimeError(f"Chrome did not start in time (waited {timeout}s)")


def get_aspect_ratio_for_image(image_path: str) -> str:
    """Determine the closest Higgsfield aspect ratio for the given image."""
    with Image.open(image_path) as img:
        width, height = img.size
    return closest_ratio(width, height)


def build_task(image_path: str, aspect_ratio: str) -> str:
    """Build the browser-use agent task prompt."""
    return f"""You are automating Higgsfield Soul v2 image generation. Follow these steps EXACTLY:

1. Navigate to https://higgsfield.ai/mobile/image/soul-v2

2. BLANK PAGE CHECK: After the page loads, check if the UI is blank/empty (no tabs,
   no controls, just a blank or dark screen with no interactive elements). Higgsfield
   sometimes loads with a blank UI. If the page appears blank:
   - Refresh the page (navigate to the same URL again)
   - Wait for it to load
   - If still blank after 2 refreshes, respond with EXACTLY:
     FAILED: Page loaded blank after multiple refreshes

3. If a cookie consent dialog appears (with "Accept all" / "Reject all" buttons), click "Accept all" first.

4. If the page shows a login screen instead of the generation interface, respond with EXACTLY:
   FAILED: Session expired - login required

5. Click the "Image Reference" tab at the top of the page.

6. Find and click the character selector (it may say "No Character" or show a character name).
   When the character dialog opens:
   - Wait 15 seconds for the character grid to load (it is slow)
   - If the grid area is blank/empty (no character cards visible), wait another 10 seconds
   - If STILL blank after 25 seconds total, close the dialog, refresh the page
     (navigate to the URL again), dismiss any cookie dialog, click Image Reference tab,
     and try opening the character selector again
   - Once characters are visible, click the "Soul 2.0" category tab
   - Find and click "Fufu" in the character grid. If not visible, scroll down to find it.

7. Upload the image file at: {image_path}
   Click the upload area or find the file input element and upload this file.

8. Select the aspect ratio "{aspect_ratio}" from the aspect ratio options.

9. Set Batch Size to "4" (click the 4 option).

10. Set Quality to "2K" (click the 2K option).

11. VERIFICATION CHECK - Before clicking Generate, verify ALL of these:
    - Image Reference tab is active/selected
    - Fufu character is selected
    - An image preview is visible in the upload area (not empty)
    - Aspect ratio {aspect_ratio} is selected
    - Batch Size 4 is selected
    - Quality 2K is selected

    If ANY check fails, respond with EXACTLY:
    FAILED: Pre-check failed - [which check failed]

12. Click the "Generate" button.

13. If generation fails to start (error message appears), respond with EXACTLY:
    FAILED: Generation error - [error message]

14. After clicking Generate, wait 8 minutes for the images to process.

15. Navigate to https://higgsfield.ai/asset/image

16. BLANK PAGE CHECK (again): If the assets page loads blank, refresh it. Same rule
    as step 2 — retry up to 2 times.

17. Check if the top 4 images in the grid are fully loaded (no spinners/progress bars).
    If not ready, wait 7 more minutes, then navigate to the assets page again and check.
    If still not ready after 15 minutes total, respond with EXACTLY:
    FAILED: Generation timed out after 15 minutes

18. For each of the 4 newest images in the grid, extract the share link:
    - Click the 3-dot menu (top-right corner of the image card)
    - Click "Share" in the dropdown
    - Click "Copy link"
    - Note the URL shown in the toast notification or dialog
    - Press Escape to close the menu

19. After collecting all 4 links, respond with EXACTLY this format (one URL per line):
    LINKS:
    [url1]
    [url2]
    [url3]
    [url4]
"""


def parse_result(result_text: str) -> dict:
    """Parse the agent's final output into a structured result."""
    if not result_text:
        return {"status": "error", "message": "Agent returned no output"}

    text = result_text.strip()

    if text.startswith("FAILED:"):
        return {"status": "error", "message": text[7:].strip()}

    if "LINKS:" in text:
        lines = text.split("LINKS:")[1].strip().splitlines()
        links = [line.strip() for line in lines if line.strip().startswith("http")]
        if links:
            return {"status": "success", "links": links}
        return {"status": "error", "message": "Could not parse share links from output"}

    return {"status": "error", "message": f"Unexpected output: {text[:200]}"}


async def run_generation(image_path: str, cdp_url: str = "http://localhost:9222") -> dict:
    """Run the Higgsfield generation workflow using browser-use."""
    load_dotenv()

    aspect_ratio = get_aspect_ratio_for_image(image_path)
    task = build_task(image_path, aspect_ratio)

    llm = ChatGoogle(model="gemini-2.0-flash")

    ensure_chrome_ready(cdp_url)

    # Attach to the running Chrome via CDP — no new process launched.
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
        await browser.stop()


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


if __name__ == "__main__":
    main()
