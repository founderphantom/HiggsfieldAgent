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
import re
import subprocess
import sys
import time
from pathlib import Path

from curl_cffi import requests as curl_requests
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
FUFU_CHARACTER_ID = "f457e2ec-a3d9-4699-97dd-0cbc4d9fe1a4"
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
IMPERSONATE = "firefox133"


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
def _log(msg: str) -> None:
    print(f"[higgsfield] {msg}", file=sys.stderr)


def _save_session(session_id: str, client_cookie: str) -> None:
    SESSION_CACHE.write_text(json.dumps({
        "session_id": session_id,
        "client_cookie": client_cookie,
    }))


def _load_session() -> tuple[str, str] | None:
    """Returns (session_id, client_cookie) or None if cache is missing/corrupt."""
    if not SESSION_CACHE.exists():
        return None
    try:
        data = json.loads(SESSION_CACHE.read_text().strip())
        return data["session_id"], data["client_cookie"]
    except Exception:
        return None


def _get_jwt_for_session(session_id: str, session: object = None) -> str:
    """Exchange a live Clerk session ID for a fresh short-lived JWT.

    Pass `session` to reuse an existing curl_cffi session with its cookies
    intact (required right after fresh login). Without it, the saved
    __client cookie is injected so Clerk can locate the session owner.
    """
    url = f"{CLERK_BASE}/v1/client/sessions/{session_id}/tokens?debug=skip_cache&{CLERK_PARAMS}"

    def _fetch(s):
        resp = s.post(url, data={"organization_id": ""})
        if resp.status_code != 200:
            raise RuntimeError(f"Token refresh failed ({resp.status_code})")
        return resp.json()["jwt"]

    if session is not None:
        return _fetch(session)

    # Inject the saved __client cookie so Clerk recognises the session owner
    cached = _load_session()
    with curl_requests.Session(impersonate=IMPERSONATE) as s:
        s.get(f"{CLERK_BASE}/v1/environment?{CLERK_PARAMS}")
        if cached:
            _, client_cookie = cached
            s.cookies.set("__client", client_cookie, domain=".higgsfield.ai")
        else:
            s.get(f"{CLERK_BASE}/v1/client?{CLERK_PARAMS}")
        return _fetch(s)


def _fetch_otp_from_gmail(poll_interval: int = 10, max_attempts: int = 12) -> str:
    """Poll Gmail for the Higgsfield OTP email and return the 6-digit code.

    Requires $GAPI (Hermes Google Workspace CLI) to be available.
    Polls every poll_interval seconds for up to max_attempts tries (~2 minutes).
    Set HIGGSFIELD_AUTO_OTP=1 to activate this path instead of stdin input.
    """
    # $GAPI may be a multi-word string like "python3 /path/to/gapi.py" — split it
    gapi = os.environ.get("GAPI", "gapi").split()
    _log(f"Auto-OTP: polling Gmail every {poll_interval}s (up to {max_attempts} attempts)...")
    for attempt in range(1, max_attempts + 1):
        time.sleep(poll_interval)
        _log(f"  Checking Gmail (attempt {attempt}/{max_attempts})...")
        try:
            search_out = subprocess.check_output(
                gapi + ["gmail", "search",
                        "from:higgsfield newer_than:5m subject:verification",
                        "--max", "1"],
                text=True,
            )
            messages = json.loads(search_out)
            if not messages:
                continue
            msg_out = subprocess.check_output(
                gapi + ["gmail", "get", messages[0]["id"]],
                text=True,
            )
            body = json.loads(msg_out).get("body", "")
            match = re.search(r'\b(\d{6})\b', body)
            if match:
                code = match.group(1)
                _log(f"  OTP found: {code}")
                return code
        except Exception as exc:
            _log(f"  Gmail check failed: {exc}")
    raise RuntimeError("Auto-OTP: no verification email found in Gmail after 2 minutes")


def login_full(email: str, password: str) -> str:
    """Full Clerk login: password + OTP -> session -> JWT.

    Prompts stdin for the 6-digit OTP code sent to the account email.
    If HIGGSFIELD_AUTO_OTP=1 is set, fetches the code from Gmail via $GAPI instead.
    Caches the new session ID to SESSION_CACHE for future runs.
    """
    base_url = f"{CLERK_BASE}/v1/client/sign_ins?{CLERK_PARAMS}"

    with curl_requests.Session(impersonate=IMPERSONATE) as s:
        # Warm up: establish __client cookie and Cloudflare cookies (matches browser flow)
        _log("Establishing client session...")
        s.get(f"{CLERK_BASE}/v1/environment?{CLERK_PARAMS}")
        s.get(f"{CLERK_BASE}/v1/client?{CLERK_PARAMS}")

        # Step 1: password
        _log("Submitting password...")
        r = s.post(base_url, data={
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
        _log("Requesting verification code email...")
        s.post(
            f"{CLERK_BASE}/v1/client/sign_ins/{sia_id}/prepare_second_factor?{CLERK_PARAMS}",
            data={"strategy": "email_code", "email_address_id": idn_id},
        )
        _log("Verification code sent — check your email.")

        # Step 3: submit OTP — auto-fetch from Gmail or prompt stdin
        if os.environ.get("HIGGSFIELD_AUTO_OTP"):
            code = _fetch_otp_from_gmail()
        else:
            code = input("Enter the verification code: ").strip()
        _log("Submitting verification code...")
        r2 = s.post(
            f"{CLERK_BASE}/v1/client/sign_ins/{sia_id}/attempt_second_factor?{CLERK_PARAMS}",
            data={"strategy": "email_code", "code": code},
        )
        if r2.status_code != 200 or r2.json()["response"]["status"] != "complete":
            raise RuntimeError(
                f"OTP verification failed ({r2.status_code}): {r2.text[:200]}"
            )
        session_id = r2.json()["response"]["created_session_id"]

        # Step 4: activate the session (browser always does this after sign-in)
        _log("Activating session...")
        s.post(
            f"{CLERK_BASE}/v1/client/sessions/{session_id}/touch?{CLERK_PARAMS}",
            data={"active_organization_id": "", "intent": "select_session"},
        )

        # Step 5: get JWT while the session's cookies are still live
        _log("Fetching JWT...")
        jwt = _get_jwt_for_session(session_id, session=s)

        # Save session + __client cookie so future runs can refresh without OTP
        client_cookie = s.cookies.get("__client", "")

    _log("Login complete. Session cached.")
    _save_session(session_id, client_cookie)
    return jwt


def get_jwt(email: str, password: str) -> str:
    """Return a fresh JWT. Uses cached session if available, else full login."""
    cached = _load_session()
    if cached:
        session_id, _ = cached
        _log("Using cached session...")
        try:
            return _get_jwt_for_session(session_id)
        except RuntimeError:
            _log("Cached session expired, doing full login.")
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

    _log(f"Uploading image: {img_path.name}")
    with curl_requests.Session(impersonate=IMPERSONATE) as s:
        # Step 1: reserve upload slot
        r = s.post(
            f"{API_BASE}/media/batch",
            json={
                "mimetypes": ["image/jpeg"],
                "source": "user_upload",
                "force_ip_check": False,
            },
            headers=headers,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Media batch failed ({r.status_code}): {r.text[:200]}")
        slot = r.json()[0]
        media_id   = slot["id"]
        cdn_url    = slot["url"]
        upload_url = slot["upload_url"]

        _log(f"Upload slot reserved: {media_id}")
        # Step 2: PUT raw bytes — separate clean session (presigned URL, no auth header)
        _log("Uploading to S3...")
        with open(img_path, "rb") as f:
            image_bytes = f.read()
        with curl_requests.Session(impersonate=IMPERSONATE) as s3:
            put_resp = s3.put(upload_url, data=image_bytes, headers={"Content-Type": "image/jpeg"})
        if put_resp.status_code not in (200, 204):
            raise RuntimeError(f"S3 upload failed ({put_resp.status_code})")
        _log("S3 upload done. Confirming with Higgsfield...")

        # Step 3: confirm upload
        r2 = s.post(
            f"{API_BASE}/media/{media_id}/upload",
            json={
                "filename": img_path.name,
                "force_nsfw_check": True,
                "force_ip_check": False,
            },
            headers=headers,
        )
        if r2.status_code != 200:
            raise RuntimeError(f"Upload confirm failed ({r2.status_code}): {r2.text[:200]}")
        _log("Image upload confirmed.")

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
    _log(f"Triggering generation (aspect_ratio={aspect_ratio}, quality={SOUL_V2_QUALITY}, batch={SOUL_V2_BATCH})...")
    with curl_requests.Session(impersonate=IMPERSONATE) as s:
        resp = s.post(f"{API_BASE}/jobs/v2/text2image_soul_v2", json=payload, headers=_api_headers(jwt))
    if resp.status_code != 200:
        raise RuntimeError(f"Generation failed ({resp.status_code}): {resp.text[:200]}")
    jobs = resp.json()["job_sets"][0]["jobs"]
    job_ids = [j["id"] for j in jobs]
    _log(f"Generation started. Job IDs: {job_ids}")
    return job_ids


# ---------------------------------------------------------------------------
# Poll + share
# ---------------------------------------------------------------------------
def poll_jobs(jwt: str, job_ids: list[str], timeout: int = POLL_TIMEOUT) -> str:
    """Poll all job IDs until every one reaches 'completed'. Raises on timeout.

    Returns the JWT in use at completion — may be refreshed if it expired mid-poll.
    """
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
        with curl_requests.Session(impersonate=IMPERSONATE) as s:
            for job_id in pending:
                resp = s.get(f"{API_BASE}/jobs/{job_id}/status", headers=headers)
                if resp.status_code == 401:
                    # JWT expired mid-poll — refresh and retry once
                    _log("JWT expired during polling, refreshing...")
                    cached = _load_session()
                    jwt = _get_jwt_for_session(cached[0] if cached else "")
                    headers = _api_headers(jwt)
                    resp = s.get(f"{API_BASE}/jobs/{job_id}/status", headers=headers)
                if resp.status_code != 200:
                    raise RuntimeError(f"Poll failed for {job_id} ({resp.status_code})")
                status = resp.json().get("status", "")
                if status == "completed":
                    _log(f"  {job_id[:8]}... completed")
                    continue
                if status in ("failed", "error"):
                    raise RuntimeError(f"Job {job_id} failed: {resp.json()}")
                still_pending.add(job_id)
        pending = still_pending
        if pending:
            _log(f"Waiting — {len(pending)} job(s) still pending...")
            time.sleep(POLL_INTERVAL)
    return jwt


def get_share_links(jwt: str, job_ids: list[str]) -> list[str]:
    """GET then PATCH sharing-configs for each job to enable sharing.

    The GET creates the initial config record (no_access); the PATCH sets it
    to edit-access. Skipping the GET causes PATCH to 404.
    Returns list of higg.ai short URLs, one per job_id.
    """
    headers = _api_headers(jwt)
    links = []
    with curl_requests.Session(impersonate=IMPERSONATE) as s:
        for job_id in job_ids:
            # GET first — creates the sharing config record if it doesn't exist
            s.get(f"{API_BASE}/sharing-configs?asset_id={job_id}", headers=headers)

            resp = s.patch(
                f"{API_BASE}/sharing-configs?asset_id={job_id}",
                json={
                    "link_access_level": "edit",
                    "redirect_url": (
                        f"https://higgsfield.ai/share/{job_id}"
                        "?utm_source=copylink&utm_medium=share"
                        "&utm_campaign=asset_share&utm_content=image"
                    ),
                },
                headers=headers,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Share link failed for {job_id} ({resp.status_code})"
                )
            links.append(resp.json()["share_url"])
    return links


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def get_raw_urls(jwt: str, job_ids: list[str]) -> dict[str, str]:
    """Return {job_id: raw_cdn_url} for every job_id in the list."""
    headers = _api_headers(jwt)
    with curl_requests.Session(impersonate=IMPERSONATE) as s:
        resp = s.get(f"{API_BASE}/assets?size=1001&category=image", headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Assets fetch failed ({resp.status_code}): {resp.text[:200]}")
    target = set(job_ids)
    return {
        item["id"]: item["raw_url"]
        for item in resp.json().get("items", [])
        if item["id"] in target and item.get("raw_url")
    }


def download_images(jwt: str, job_ids: list[str], image_path: str) -> list[str]:
    """Download generated images next to the input image.

    Files are saved as {stem}_out_1.png … {stem}_out_N.png in the same
    directory as image_path. Returns the list of saved absolute paths.
    """
    raw_urls = get_raw_urls(jwt, job_ids)
    img_path = Path(image_path)
    output_dir = img_path.parent
    stem = img_path.stem
    saved = []
    for n, job_id in enumerate(job_ids, 1):
        url = raw_urls.get(job_id)
        if not url:
            _log(f"  No raw_url for {job_id[:8]}... skipping")
            continue
        ext = Path(url.split("?")[0]).suffix or ".png"
        out_path = output_dir / f"{stem}_out_{n}{ext}"
        _log(f"  Downloading image {n}/{len(job_ids)}: {out_path.name}")
        # Fresh session per image — avoids CDN dropping a reused connection mid-transfer
        for attempt in range(3):
            try:
                with curl_requests.Session(impersonate=IMPERSONATE) as s:
                    resp = s.get(url)
                if resp.status_code != 200:
                    raise RuntimeError(f"Image download failed for {job_id} ({resp.status_code})")
                out_path.write_bytes(resp.content)
                saved.append(str(out_path))
                break
            except Exception as exc:
                if attempt == 2:
                    raise RuntimeError(f"Image download failed for {job_id} after 3 attempts: {exc}") from exc
                _log(f"  Retrying image {n} (attempt {attempt + 2}/3)...")
                time.sleep(2)
    return saved


# ---------------------------------------------------------------------------
# Pipeline + CLI
# ---------------------------------------------------------------------------
def run_generation(image_path: str) -> dict:
    """Full pipeline: auth -> upload -> generate -> poll -> share links -> download."""
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
        _log(f"Image aspect ratio: {aspect_ratio}")

        jwt = get_jwt(email, password)
        media_id, media_url = upload_image(jwt, image_path)
        job_ids = start_generation(jwt, media_id, media_url, aspect_ratio)
        _log("Polling for completion (this takes ~8 minutes)...")
        jwt = poll_jobs(jwt, job_ids)
        _log("All jobs complete. Fetching share links...")
        links = get_share_links(jwt, job_ids)
        _log("Downloading images...")
        local_paths = download_images(jwt, job_ids, image_path)
        _log("Done!")
        return {"status": "success", "links": links, "local_paths": local_paths}
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
