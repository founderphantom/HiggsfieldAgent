#!/usr/bin/env python3
"""Higgsfield FUFU generation via direct HTTP API.

Usage:
    python higgsfield_api.py <image_path>

Output (stdout JSON):
    {"status": "success", "links": ["url1", "url2", "url3", "url4"]}
    {"status": "error", "message": "..."}

Requires env vars:
    HIGGSFIELD_EMAIL    - account email
    HIGGSFIELD_PASSWORD - account password

Session cache:
    ~/.higgsfield_session  - stores Clerk session_id to skip OTP on repeat runs
"""
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from PIL import Image

# ---------------------------------------------------------------------------
# Hosts
# ---------------------------------------------------------------------------
CLERK_BASE = "https://clerk.higgsfield.ai"
API_BASE = "https://fnf.higgsfield.ai"
CLERK_PARAMS = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10"

# ---------------------------------------------------------------------------
# Generation constants
# ---------------------------------------------------------------------------
FUFU_CHARACTER_ID = "9122abde-1e28-46b5-b3c5-712e003a80d7"
GENERAL_STYLE_ID = "3db34ab5-3439-4317-9e03-08dc30852e69"
SOUL_V2_QUALITY = "1080p"   # captured value; use "2K" if higher quality needed
SOUL_V2_BATCH = 4

# Quality -> (width, height) for 3:4 aspect ratio (captured baseline).
QUALITY_DIMS = {
    "1080p": (1536, 2048),
    "2K": (2048, 2732),
}

# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------
POLL_INTERVAL = 15   # seconds between status checks
POLL_TIMEOUT = 900   # 15 minutes max

# ---------------------------------------------------------------------------
# Session cache path
# ---------------------------------------------------------------------------
SESSION_CACHE = Path.home() / ".higgsfield_session"


# ---------------------------------------------------------------------------
# Common headers for fnf.higgsfield.ai
# ---------------------------------------------------------------------------
def _api_headers(jwt: str) -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
            "Gecko/20100101 Firefox/150.0"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Authorization": f"Bearer {jwt}",
        "Origin": "https://higgsfield.ai",
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _get_jwt_for_session(session_id: str) -> str:
    """Exchange a live Clerk session ID for a fresh short-lived JWT."""
    url = f"{CLERK_BASE}/v1/client/sessions/{session_id}/tokens?{CLERK_PARAMS}"
    with httpx.Client() as client:
        resp = client.post(url, data={"organization_id": ""})
    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed ({resp.status_code})")
    return resp.json()["jwt"]


def login_full(email: str, password: str) -> str:
    """Full Clerk login: password + OTP -> session -> JWT.

    Prompts stdin for the 6-digit OTP code sent to the account email.
    Caches the new session ID to SESSION_CACHE for future runs.
    """
    base_url = f"{CLERK_BASE}/v1/client/sign_ins?{CLERK_PARAMS}"

    with httpx.Client() as client:
        # Step 1: password
        r = client.post(base_url, data={
            "locale": "en-US",
            "identifier": email,
            "password": password,
        })
        if r.status_code != 200:
            raise RuntimeError(f"Login failed ({r.status_code}): {r.text[:200]}")
        resp_data = r.json()["response"]
        sia_id = resp_data["id"]
        idn_id = resp_data["supported_second_factors"][0]["email_address_id"]

        # Step 2: trigger OTP email
        client.post(
            f"{CLERK_BASE}/v1/client/sign_ins/{sia_id}/prepare_second_factor?{CLERK_PARAMS}",
            data={"strategy": "email_code", "email_address_id": idn_id},
        )

        # Step 3: submit OTP (prompts user)
        code = input("Enter the verification code sent to your email: ").strip()
        r2 = client.post(
            f"{CLERK_BASE}/v1/client/sign_ins/{sia_id}/attempt_second_factor?{CLERK_PARAMS}",
            data={"strategy": "email_code", "code": code},
        )
        if r2.status_code != 200 or r2.json()["response"]["status"] != "complete":
            raise RuntimeError(
                f"OTP verification failed ({r2.status_code}): {r2.text[:200]}"
            )
        session_id = r2.json()["response"]["created_session_id"]

    # Cache session for future runs
    SESSION_CACHE.write_text(session_id)

    return _get_jwt_for_session(session_id)


def get_jwt(email: str, password: str) -> str:
    """Return a fresh JWT. Uses cached session if available, else full login."""
    if SESSION_CACHE.exists():
        session_id = SESSION_CACHE.read_text().strip()
        try:
            return _get_jwt_for_session(session_id)
        except RuntimeError:
            SESSION_CACHE.unlink(missing_ok=True)
    return login_full(email, password)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
def upload_image(jwt: str, image_path: str) -> tuple[str, str]:
    """Upload image to Higgsfield. Returns (media_id, cdn_url).

    Flow:
      1. POST /media/batch -> get media_id, cdn_url, presigned upload_url
      2. PUT image bytes to presigned S3 upload_url
      3. POST /media/{media_id}/upload to confirm
    """
    headers = _api_headers(jwt)
    img_path = Path(image_path)

    with httpx.Client(headers=headers) as client:
        # Step 1: reserve upload slot
        r = client.post(
            f"{API_BASE}/media/batch",
            json={
                "mimetypes": ["image/jpeg"],
                "source": "user_upload",
                "force_ip_check": False,
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"Media batch failed ({r.status_code}): {r.text[:200]}")
        slot = r.json()[0]
        media_id = slot["id"]
        cdn_url = slot["url"]
        upload_url = slot["upload_url"]

        # Step 2: PUT raw bytes to presigned S3 URL (no auth header needed)
        with open(img_path, "rb") as f:
            image_bytes = f.read()
        put_resp = client.put(
            upload_url,
            content=image_bytes,
            headers={"Content-Type": "image/jpeg"},
        )
        if put_resp.status_code not in (200, 204):
            raise RuntimeError(f"S3 upload failed ({put_resp.status_code})")

        # Step 3: confirm upload
        r2 = client.post(
            f"{API_BASE}/media/{media_id}/upload",
            json={
                "filename": img_path.name,
                "force_nsfw_check": True,
                "force_ip_check": False,
            },
        )
        if r2.status_code != 200:
            raise RuntimeError(f"Upload confirm failed ({r2.status_code}): {r2.text[:200]}")

    return media_id, cdn_url


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
def start_generation(
    jwt: str, media_id: str, media_url: str, aspect_ratio: str
) -> list[str]:
    """Trigger Soul V2 FUFU generation. Returns list of 4 job IDs."""
    width, height = QUALITY_DIMS.get(SOUL_V2_QUALITY, (1536, 2048))
    payload = {
        "params": {
            "is_custom": False,
            "model": "soul_v2",
            "prompt": "",
            "style_id": GENERAL_STYLE_ID,
            "style_strength": 1,
            "custom_reference_id": FUFU_CHARACTER_ID,
            "custom_reference_strength": 1,
            "aspect_ratio": aspect_ratio,
            "quality": SOUL_V2_QUALITY,
            "enhance_prompt": False,
            "width": width,
            "height": height,
            "batch_size": SOUL_V2_BATCH,
            "medias": [{
                "role": "image",
                "data": {
                    "id": media_id,
                    "type": "media_input",
                    "url": media_url,
                },
            }],
            "seed": random.randint(1, 999999),
            "use_unlim": False,
            "use_green": True,
            "use_refiner": False,
            "negative_prompt": "",
            "lora": None,
            "chain_enhancer": None,
            "model_version": "fast",
        },
        "use_unlim": False,
    }
    with httpx.Client(headers=_api_headers(jwt)) as client:
        resp = client.post(f"{API_BASE}/jobs/v2/text2image_soul_v2", json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Generation failed ({resp.status_code}): {resp.text[:200]}")
    jobs = resp.json()["job_sets"][0]["jobs"]
    return [j["id"] for j in jobs]


# ---------------------------------------------------------------------------
# Poll + share
# ---------------------------------------------------------------------------
def poll_jobs(jwt: str, job_ids: list[str], timeout: int = POLL_TIMEOUT) -> None:
    """Poll all job IDs until every one reaches 'completed'. Raises on timeout."""
    headers = _api_headers(jwt)
    deadline = time.time() + timeout
    pending = set(job_ids)

    while pending:
        if time.time() > deadline:
            raise RuntimeError(
                f"Generation timed out after {timeout}s "
                f"({len(pending)} jobs still pending)"
            )
        still_pending = set()
        with httpx.Client(headers=headers) as client:
            for job_id in pending:
                resp = client.get(f"{API_BASE}/jobs/{job_id}/status")
                if resp.status_code != 200:
                    raise RuntimeError(f"Poll failed for {job_id} ({resp.status_code})")
                status = resp.json().get("status", "")
                if status == "completed":
                    continue
                if status in ("failed", "error"):
                    raise RuntimeError(f"Job {job_id} failed: {resp.json()}")
                still_pending.add(job_id)
        pending = still_pending
        if pending:
            time.sleep(POLL_INTERVAL)


def get_share_links(jwt: str, job_ids: list[str]) -> list[str]:
    """PATCH sharing-configs for each job to enable sharing.

    Returns list of higg.ai short URLs, one per job_id.
    """
    headers = _api_headers(jwt)
    links = []
    with httpx.Client(headers=headers) as client:
        for job_id in job_ids:
            resp = client.patch(
                f"{API_BASE}/sharing-configs?asset_id={job_id}",
                json={
                    "link_access_level": "edit",
                    "redirect_url": (
                        f"https://higgsfield.ai/share/{job_id}"
                        "?utm_source=copylink&utm_medium=share"
                        "&utm_campaign=asset_share&utm_content=image"
                    ),
                },
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Share link failed for {job_id} ({resp.status_code})"
                )
            links.append(resp.json()["share_url"])
    return links


# ---------------------------------------------------------------------------
# Pipeline + CLI
# ---------------------------------------------------------------------------
def run_generation(image_path: str) -> dict:
    """Full pipeline: auth -> upload -> generate -> poll -> share links."""
    load_dotenv()
    email = os.environ.get("HIGGSFIELD_EMAIL", "")
    password = os.environ.get("HIGGSFIELD_PASSWORD", "")
    if not email or not password:
        return {
            "status": "error",
            "message": "HIGGSFIELD_EMAIL and HIGGSFIELD_PASSWORD must be set in .env",
        }
    try:
        # Local import so tests can patch get_aspect_ratio without import-time errors.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from get_aspect_ratio import closest_ratio

        with Image.open(image_path) as img:
            aspect_ratio = closest_ratio(*img.size)

        jwt = get_jwt(email, password)
        media_id, media_url = upload_image(jwt, image_path)
        job_ids = start_generation(jwt, media_id, media_url, aspect_ratio)
        poll_jobs(jwt, job_ids)
        links = get_share_links(jwt, job_ids)
        return {"status": "success", "links": links}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate FUFU variations on Higgsfield via API"
    )
    parser.add_argument("image_path", help="Path to the inspiration image")
    args = parser.parse_args()

    image_path = str(Path(args.image_path).resolve())
    if not Path(image_path).exists():
        print(json.dumps({"status": "error", "message": f"Image not found: {image_path}"}))
        sys.exit(1)

    result = run_generation(image_path)
    print(json.dumps(result))
    if result["status"] != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
