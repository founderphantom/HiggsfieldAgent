# Higgsfield API Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the browser-use/LLM/Chrome automation pipeline with a direct HTTP API client that drives Higgsfield's REST API using email/password auth, reducing generation overhead from ~10 minutes to ~30 seconds.

**Architecture:** Two phases. Phase 1 (Tasks 1–2) is reconnaissance: capture Higgsfield's API traffic with Burp Suite and produce an endpoint map. Phase 2 (Tasks 3–9) is implementation: build `scripts/higgsfield_api.py` as a drop-in replacement for `scripts/generate_fufu.py` with the same CLI interface and JSON output contract. Browser-use, Chrome, and the Gemini LLM are removed entirely.

**Tech Stack:** Python 3.11+, httpx, python-dotenv, Pillow (already installed)

**Burp capture reference:** `docs/Full_gen.xml` — full session from login through generation and share link extraction.

---

## Phase 1: Reconnaissance ✅ COMPLETE

### Task 1: Burp Suite capture session ✅ DONE

**Notes from actual capture:**
- Used **Firefox** (not Chrome) with proxy configured via Firefox Settings → Network Settings → Manual proxy → `127.0.0.1:8080`
- Required **burp-awesome-tls** extension (`sleeyax/burp-awesome-tls`, `*-fat.jar`) with fingerprint set to `firefox_147` — Higgsfield uses Cloudflare Bot Management (`__cf_bm`) and DataDome which detect Burp's Java TLS fingerprint without this extension
- burp-awesome-tls internal listener runs on `127.0.0.1:8887`; Firefox still points to `127.0.0.1:8080` (Burp's listener)
- Login requires **email verification code (OTP)** sent to inbox after password entry — this is Clerk's mandatory second factor
- Raw capture saved at `docs/Full_gen.xml`

---

### Task 2: Endpoint map ✅ DONE

**All endpoints confirmed from `docs/Full_gen.xml` and supplementary captures.**

#### Hosts

| Host | Purpose |
|---|---|
| `clerk.higgsfield.ai` | Authentication (Clerk) |
| `fnf.higgsfield.ai` | All API operations (upload, generate, poll, share) |
| `d276s3zg8h21b2.cloudfront.net` | S3-backed presigned upload destination |
| `d2ol7oe51mr4n9.cloudfront.net` | Permanent CDN for uploaded user media |

#### Auth — 4-step Clerk flow

```
POST https://clerk.higgsfield.ai/v1/client/sign_ins?__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10
  Content-Type: application/x-www-form-urlencoded
  Body: locale=en-US&identifier={email}&password={password}
  → 200 {"response": {"id": "sia_{id}", "status": "needs_second_factor",
                       "supported_second_factors": [{"strategy": "email_code",
                                                     "email_address_id": "idn_{id}"}]}}

POST https://clerk.higgsfield.ai/v1/client/sign_ins/{sia_id}/prepare_second_factor?...
  Content-Type: application/x-www-form-urlencoded
  Body: strategy=email_code&email_address_id={idn_id}
  → 200  (triggers OTP email to user)

POST https://clerk.higgsfield.ai/v1/client/sign_ins/{sia_id}/attempt_second_factor?...
  Content-Type: application/x-www-form-urlencoded
  Body: strategy=email_code&code={6_digit_otp}
  → 200 {"response": {"status": "complete", "created_session_id": "sess_{id}"}}

POST https://clerk.higgsfield.ai/v1/client/sessions/{session_id}/tokens?__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10
  Content-Type: application/x-www-form-urlencoded
  Body: organization_id=
  → 200 {"jwt": "{token}"}   ← short-lived (~60s), contains workspace_id and user_id in payload
```

**Session caching:** The underlying Clerk session (`sess_...`) is long-lived (days/weeks). The script must cache the `session_id` on disk so that on subsequent runs it only calls the `/tokens` endpoint to get a fresh JWT — skipping the full login and OTP flow. Only re-runs the full login when the cached session is expired or invalid.

#### Image upload — 3-step presigned S3 flow

```
POST https://fnf.higgsfield.ai/media/batch
  Authorization: Bearer {jwt}
  Content-Type: application/json
  Body: {"mimetypes": ["image/jpeg"], "source": "user_upload", "force_ip_check": false}
  → 200 [{"id": "{media_id}",
           "url": "https://d2ol7oe51mr4n9.cloudfront.net/{user_id}/{media_id}.jpg",
           "upload_url": "https://d276s3zg8h21b2.cloudfront.net/...?X-Amz-Signature=...",
           "content_type": "image/jpeg"}]

PUT {upload_url}
  Content-Type: image/jpeg
  Body: <raw image bytes>
  → 200  (direct to S3 — no Authorization header needed, URL is pre-signed)

POST https://fnf.higgsfield.ai/media/{media_id}/upload
  Authorization: Bearer {jwt}
  Content-Type: application/json
  Body: {"filename": "{original_filename}", "force_nsfw_check": true, "force_ip_check": false}
  → 200 {"id": "{media_id}", "status": "uploaded", "ip_check_finished": null}
```

After step 3, use `media_id` and `url` (the permanent CDN URL) in the generation request.

#### Generation trigger

```
POST https://fnf.higgsfield.ai/jobs/v2/text2image_soul_v2
  Authorization: Bearer {jwt}
  Content-Type: application/json
  Body:
  {
    "params": {
      "is_custom": false,
      "model": "soul_v2",
      "prompt": "",
      "style_id": "3db34ab5-3439-4317-9e03-08dc30852e69",
      "style_strength": 1,
      "custom_reference_id": "9122abde-1e28-46b5-b3c5-712e003a80d7",
      "custom_reference_strength": 1,
      "aspect_ratio": "{aspect_ratio}",
      "quality": "{quality}",
      "enhance_prompt": false,
      "width": {width},
      "height": {height},
      "batch_size": 4,
      "medias": [{"role": "image", "data": {"id": "{media_id}", "type": "media_input", "url": "{media_cdn_url}"}}],
      "seed": {random_int},
      "use_unlim": false,
      "use_green": true,
      "use_refiner": false,
      "negative_prompt": "",
      "lora": null,
      "chain_enhancer": null,
      "model_version": "fast"
    },
    "use_unlim": false
  }
  → 200 {"id": "{workspace_id}", "job_sets": [{"id": "{job_set_id}",
          "jobs": [{"id": "{job_id_1}"}, {"id": "{job_id_2}"},
                   {"id": "{job_id_3}"}, {"id": "{job_id_4}"}]}]}
```

Extract job IDs from: `response["job_sets"][0]["jobs"][i]["id"]` — returns all 4 immediately.

**Quality / dimension mapping** (captured values at `quality: "1080p"`, `aspect_ratio: "3:4"` → `width: 1536, height: 2048`). For "2K" the quality string is likely `"2K"` with correspondingly larger dimensions — verify if needed, otherwise use `"1080p"` as the default.

#### Job status polling

```
GET https://fnf.higgsfield.ai/jobs/{job_id}/status
  Authorization: Bearer {jwt}
  → 200 {"id": "{job_id}", "status": "queued"|"in_progress"|"completed",
          "job_set_type": "text2image_soul_v2"}
```

Poll each of the 4 job IDs. All 4 typically complete within the same window. Status sequence: `queued` → `in_progress` → `completed`.

#### Share link extraction

```
PATCH https://fnf.higgsfield.ai/sharing-configs?asset_id={job_id}
  Authorization: Bearer {jwt}
  Content-Type: application/json
  Body: {"link_access_level": "edit",
         "redirect_url": "https://higgsfield.ai/share/{job_id}?utm_source=copylink&utm_medium=share&utm_campaign=asset_share&utm_content=image"}
  → 200 {"share_url": "https://higg.ai/{code}", "share_code": "{code}", ...}
```

Note: `asset_id` in the query string equals the `job_id`. The share URL domain is `higg.ai` (short link), not `higgsfield.ai`.

#### Fixed constants (this account)

| Constant | Value |
|---|---|
| Fufu character ID | `9122abde-1e28-46b5-b3c5-712e003a80d7` |
| General style ID | `3db34ab5-3439-4317-9e03-08dc30852e69` |
| Workspace ID | `fc112abd-dc15-4aff-983d-9ec585ea4e40` (also in JWT payload as `workspace_id`) |
| User ID | `user_37qkAfgwz3GdqEzgaYrhldNnp0T` |

Fufu's ID can also be resolved dynamically: `GET /custom-references/v2?size=30&type=soul_2` returns `{"items": [{"id": "...", "name": "Fufu"}]}`.

#### DataDome header note

Requests to `fnf.higgsfield.ai` in the browser included `X-Datadome-Clientid`. In `httpx` (no browser JS), this header will be absent. The script should initially omit it and attempt requests — DataDome bot detection may or may not block non-browser clients on these endpoints. If `httpx` requests return 403, add `curl_cffi` with browser impersonation as a fallback (see Task 9 note).

---

## Phase 2: Implementation

> **Prerequisite:** Phase 1 is complete. All `[FILL FROM BURP]` markers below are already resolved — do not replace constants with placeholders.

---

### Task 3: Scaffold new script and constants

**Files:**
- Create: `scripts/higgsfield_api.py`
- Create: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Create the new script with constants block**

  Create `scripts/higgsfield_api.py`:

  ```python
  #!/usr/bin/env python3
  """Higgsfield FUFU generation via direct HTTP API.

  Usage:
      python higgsfield_api.py <image_path>

  Output (stdout JSON):
      {"status": "success", "links": ["url1", "url2", "url3", "url4"]}
      {"status": "error", "message": "..."}

  Requires env vars:
      HIGGSFIELD_EMAIL    — account email
      HIGGSFIELD_PASSWORD — account password

  Session cache:
      ~/.higgsfield_session  — stores Clerk session_id to skip OTP on repeat runs
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
  API_BASE   = "https://fnf.higgsfield.ai"
  CLERK_PARAMS = "__clerk_api_version=2025-11-10&_clerk_js_version=5.125.10"

  # ---------------------------------------------------------------------------
  # Generation constants
  # ---------------------------------------------------------------------------
  FUFU_CHARACTER_ID = "9122abde-1e28-46b5-b3c5-712e003a80d7"
  GENERAL_STYLE_ID  = "3db34ab5-3439-4317-9e03-08dc30852e69"
  SOUL_V2_QUALITY   = "1080p"   # captured value; use "2K" if higher quality needed
  SOUL_V2_BATCH     = 4

  # Quality → (width, height) for 3:4 aspect ratio
  QUALITY_DIMS = {
      "1080p": (1536, 2048),
      "2K":    (2048, 2732),
  }

  # ---------------------------------------------------------------------------
  # Polling
  # ---------------------------------------------------------------------------
  POLL_INTERVAL = 15   # seconds between status checks
  POLL_TIMEOUT  = 900  # 15 minutes max

  # ---------------------------------------------------------------------------
  # Session cache path
  # ---------------------------------------------------------------------------
  SESSION_CACHE = Path.home() / ".higgsfield_session"

  # ---------------------------------------------------------------------------
  # Common headers for fnf.higgsfield.ai
  # ---------------------------------------------------------------------------
  def _api_headers(jwt: str) -> dict:
      return {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
          "Accept": "*/*",
          "Accept-Language": "en-US,en;q=0.9",
          "Authorization": f"Bearer {jwt}",
          "Origin": "https://higgsfield.ai",
      }
  ```

- [ ] **Step 2: Create empty test file**

  Create `tests/test_higgsfield_api.py`:

  ```python
  """Tests for higgsfield_api.py"""
  import os
  import sys
  from unittest.mock import MagicMock, patch

  import pytest

  sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
  ```

- [ ] **Step 3: Commit scaffold**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: scaffold higgsfield_api.py with confirmed API constants"
  ```

---

### Task 4: Login module

**The login flow is a 4-step Clerk process. Sessions are cached to avoid repeated OTP prompts.**

**Files:**
- Modify: `scripts/higgsfield_api.py`
- Modify: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Write failing tests for login functions**

  Add to `tests/test_higgsfield_api.py`:

  ```python
  def test_get_jwt_from_cached_session():
      mock_resp = MagicMock()
      mock_resp.status_code = 200
      mock_resp.json.return_value = {"jwt": "test.jwt.token"}
      with patch("httpx.Client.post", return_value=mock_resp):
          from higgsfield_api import _get_jwt_for_session
          token = _get_jwt_for_session("sess_abc123")
      assert token == "test.jwt.token"


  def test_login_full_flow_raises_without_otp_input():
      sign_in_resp = MagicMock(status_code=200)
      sign_in_resp.json.return_value = {
          "response": {
              "id": "sia_test",
              "status": "needs_second_factor",
              "supported_second_factors": [
                  {"strategy": "email_code", "email_address_id": "idn_test"}
              ],
          }
      }
      with patch("httpx.Client.post", return_value=sign_in_resp):
          with patch("builtins.input", return_value="123456"):
              attempt_resp = MagicMock(status_code=200)
              attempt_resp.json.return_value = {
                  "response": {"status": "complete", "created_session_id": "sess_new"}
              }
              jwt_resp = MagicMock(status_code=200)
              jwt_resp.json.return_value = {"jwt": "new.jwt.token"}
              with patch("httpx.Client.post", side_effect=[
                  sign_in_resp,
                  MagicMock(status_code=200),  # prepare_second_factor
                  attempt_resp,
                  jwt_resp,
              ]):
                  from higgsfield_api import login_full
                  token = login_full("user@example.com", "password123")
      assert token == "new.jwt.token"
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  pytest tests/test_higgsfield_api.py::test_get_jwt_from_cached_session tests/test_higgsfield_api.py::test_login_full_flow_raises_without_otp_input -v
  ```

- [ ] **Step 3: Implement login functions**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def _get_jwt_for_session(session_id: str) -> str:
      """Exchange a live Clerk session ID for a fresh short-lived JWT."""
      url = f"{CLERK_BASE}/v1/client/sessions/{session_id}/tokens?{CLERK_PARAMS}"
      with httpx.Client() as client:
          resp = client.post(url, data={"organization_id": ""})
      if resp.status_code != 200:
          raise RuntimeError(f"Token refresh failed ({resp.status_code})")
      return resp.json()["jwt"]


  def login_full(email: str, password: str) -> str:
      """Full Clerk login: password + OTP → session → JWT.

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
              raise RuntimeError(f"OTP verification failed ({r2.status_code}): {r2.text[:200]}")
          session_id = r2.json()["response"]["created_session_id"]

      # Cache session for future runs
      SESSION_CACHE.write_text(session_id)

      return _get_jwt_for_session(session_id)


  def get_jwt(email: str, password: str) -> str:
      """Return a fresh JWT. Uses cached session if available, otherwise full login."""
      if SESSION_CACHE.exists():
          session_id = SESSION_CACHE.read_text().strip()
          try:
              return _get_jwt_for_session(session_id)
          except RuntimeError:
              SESSION_CACHE.unlink(missing_ok=True)
      return login_full(email, password)
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  pytest tests/test_higgsfield_api.py::test_get_jwt_from_cached_session -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: add Clerk login — password + OTP + session cache"
  ```

---

### Task 5: Image upload module

**Three-step presigned S3 flow: create slot → PUT to S3 → confirm.**

**Files:**
- Modify: `scripts/higgsfield_api.py`
- Modify: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Write failing test for upload_image()**

  Add to `tests/test_higgsfield_api.py`:

  ```python
  def test_upload_image_returns_media_id_and_url(tmp_path):
      img_path = tmp_path / "test.jpg"
      from PIL import Image as PILImage
      PILImage.new("RGB", (10, 10), color="red").save(img_path)

      batch_resp = MagicMock(status_code=200)
      batch_resp.json.return_value = [{
          "id": "media-abc123",
          "url": "https://d2ol7oe51mr4n9.cloudfront.net/user_x/media-abc123.jpg",
          "upload_url": "https://d276s3zg8h21b2.cloudfront.net/user_x/media-abc123.jpg?X-Amz-Signature=xyz",
          "content_type": "image/jpeg",
      }]
      put_resp = MagicMock(status_code=200)
      confirm_resp = MagicMock(status_code=200)
      confirm_resp.json.return_value = {"id": "media-abc123", "status": "uploaded"}

      with patch("httpx.Client.post", side_effect=[batch_resp, confirm_resp]):
          with patch("httpx.Client.put", return_value=put_resp):
              from higgsfield_api import upload_image
              media_id, cdn_url = upload_image("test.jwt", str(img_path))

      assert media_id == "media-abc123"
      assert "cloudfront" in cdn_url
  ```

- [ ] **Step 2: Run test to confirm it fails**

  ```bash
  pytest tests/test_higgsfield_api.py::test_upload_image_returns_media_id_and_url -v
  ```

- [ ] **Step 3: Implement upload_image()**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def upload_image(jwt: str, image_path: str) -> tuple[str, str]:
      """Upload image to Higgsfield. Returns (media_id, cdn_url).

      Flow:
        1. POST /media/batch → get media_id, cdn_url, presigned upload_url
        2. PUT image bytes to presigned S3 upload_url
        3. POST /media/{media_id}/upload to confirm
      """
      headers = _api_headers(jwt)
      img_path = Path(image_path)

      with httpx.Client(headers=headers) as client:
          # Step 1: reserve upload slot
          r = client.post(
              f"{API_BASE}/media/batch",
              json={"mimetypes": ["image/jpeg"], "source": "user_upload", "force_ip_check": False},
          )
          if r.status_code != 200:
              raise RuntimeError(f"Media batch failed ({r.status_code}): {r.text[:200]}")
          slot = r.json()[0]
          media_id  = slot["id"]
          cdn_url   = slot["url"]
          upload_url = slot["upload_url"]

          # Step 2: PUT raw bytes to presigned S3 URL (no auth header)
          with open(img_path, "rb") as f:
              image_bytes = f.read()
          put_resp = client.put(upload_url, content=image_bytes, headers={"Content-Type": "image/jpeg"})
          if put_resp.status_code not in (200, 204):
              raise RuntimeError(f"S3 upload failed ({put_resp.status_code})")

          # Step 3: confirm upload
          r2 = client.post(
              f"{API_BASE}/media/{media_id}/upload",
              json={"filename": img_path.name, "force_nsfw_check": True, "force_ip_check": False},
          )
          if r2.status_code != 200:
              raise RuntimeError(f"Upload confirm failed ({r2.status_code}): {r2.text[:200]}")

      return media_id, cdn_url
  ```

- [ ] **Step 4: Run test to confirm it passes**

  ```bash
  pytest tests/test_higgsfield_api.py::test_upload_image_returns_media_id_and_url -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: add upload_image() — 3-step presigned S3 flow"
  ```

---

### Task 6: Generation trigger module

**Returns a list of 4 job IDs immediately.**

**Files:**
- Modify: `scripts/higgsfield_api.py`
- Modify: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Write failing test for start_generation()**

  Add to `tests/test_higgsfield_api.py`:

  ```python
  def test_start_generation_returns_four_job_ids():
      mock_resp = MagicMock(status_code=200)
      mock_resp.json.return_value = {
          "id": "workspace-id",
          "job_sets": [{"id": "set-id", "jobs": [
              {"id": "job-1"}, {"id": "job-2"}, {"id": "job-3"}, {"id": "job-4"},
          ]}],
      }
      with patch("httpx.Client.post", return_value=mock_resp):
          from higgsfield_api import start_generation
          job_ids = start_generation("test.jwt", "media-abc", "https://cdn.example.com/media-abc.jpg", "3:4")
      assert job_ids == ["job-1", "job-2", "job-3", "job-4"]
  ```

- [ ] **Step 2: Run test to confirm it fails**

  ```bash
  pytest tests/test_higgsfield_api.py::test_start_generation_returns_four_job_ids -v
  ```

- [ ] **Step 3: Implement start_generation()**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def start_generation(jwt: str, media_id: str, media_url: str, aspect_ratio: str) -> list[str]:
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
              "medias": [{"role": "image", "data": {
                  "id": media_id,
                  "type": "media_input",
                  "url": media_url,
              }}],
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
  ```

- [ ] **Step 4: Run test to confirm it passes**

  ```bash
  pytest tests/test_higgsfield_api.py::test_start_generation_returns_four_job_ids -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: add start_generation() — Soul V2 FUFU, returns 4 job IDs"
  ```

---

### Task 7: Polling + share links module

**Polls all 4 job IDs in parallel. Share links use PATCH on sharing-configs (not GET).**

**Files:**
- Modify: `scripts/higgsfield_api.py`
- Modify: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Write failing tests for poll_jobs() and get_share_links()**

  Add to `tests/test_higgsfield_api.py`:

  ```python
  def test_poll_jobs_returns_when_all_complete():
      in_progress = MagicMock(status_code=200)
      in_progress.json.return_value = {"status": "in_progress"}
      completed = MagicMock(status_code=200)
      completed.json.return_value = {"status": "completed"}

      # First poll: all in_progress. Second poll: all completed.
      with patch("httpx.Client.get", side_effect=[
          in_progress, in_progress, in_progress, in_progress,
          completed,    completed,    completed,    completed,
      ]):
          with patch("time.sleep"):
              from higgsfield_api import poll_jobs
              poll_jobs("test.jwt", ["j1", "j2", "j3", "j4"])


  def test_poll_jobs_raises_on_timeout():
      always_running = MagicMock(status_code=200)
      always_running.json.return_value = {"status": "in_progress"}
      with patch("httpx.Client.get", return_value=always_running):
          with patch("time.sleep"):
              from higgsfield_api import poll_jobs
              with pytest.raises(RuntimeError, match="timed out"):
                  poll_jobs("test.jwt", ["j1"], timeout=-1)


  def test_get_share_links_returns_four_higg_ai_urls():
      mock_resp = MagicMock(status_code=200)
      mock_resp.json.return_value = {"share_url": "https://higg.ai/AbCdEfGhIjK"}
      with patch("httpx.Client.patch", return_value=mock_resp):
          from higgsfield_api import get_share_links
          links = get_share_links("test.jwt", ["j1", "j2", "j3", "j4"])
      assert links == ["https://higg.ai/AbCdEfGhIjK"] * 4
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  pytest tests/test_higgsfield_api.py::test_poll_jobs_returns_when_all_complete tests/test_higgsfield_api.py::test_poll_jobs_raises_on_timeout tests/test_higgsfield_api.py::test_get_share_links_returns_four_higg_ai_urls -v
  ```

- [ ] **Step 3: Implement poll_jobs() and get_share_links()**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def poll_jobs(jwt: str, job_ids: list[str], timeout: int = POLL_TIMEOUT) -> None:
      """Poll all job IDs until every one reaches 'completed'. Raises on timeout."""
      headers = _api_headers(jwt)
      deadline = time.time() + timeout
      pending = set(job_ids)

      while pending:
          if time.time() > deadline:
              raise RuntimeError(f"Generation timed out after {timeout}s ({len(pending)} jobs still pending)")
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
      """PATCH sharing-configs for each job to enable sharing. Returns list of higg.ai URLs."""
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
                  raise RuntimeError(f"Share link failed for {job_id} ({resp.status_code})")
              links.append(resp.json()["share_url"])
      return links
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  pytest tests/test_higgsfield_api.py::test_poll_jobs_returns_when_all_complete tests/test_higgsfield_api.py::test_poll_jobs_raises_on_timeout tests/test_higgsfield_api.py::test_get_share_links_returns_four_higg_ai_urls -v
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: add poll_jobs() and get_share_links() — PATCH sharing-configs"
  ```

---

### Task 8: Integration — run_generation() and CLI

**Files:**
- Modify: `scripts/higgsfield_api.py`
- Modify: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Write failing tests for run_generation()**

  Add to `tests/test_higgsfield_api.py`:

  ```python
  def test_run_generation_returns_success(tmp_path):
      img_path = tmp_path / "test.jpg"
      from PIL import Image as PILImage
      PILImage.new("RGB", (1080, 1440)).save(img_path)

      with patch("higgsfield_api.get_jwt", return_value="jwt_tok"), \
           patch("higgsfield_api.upload_image", return_value=("media-id", "https://cdn.example.com/m.jpg")), \
           patch("higgsfield_api.start_generation", return_value=["j1", "j2", "j3", "j4"]), \
           patch("higgsfield_api.poll_jobs"), \
           patch("higgsfield_api.get_share_links", return_value=["u1", "u2", "u3", "u4"]), \
           patch.dict("os.environ", {"HIGGSFIELD_EMAIL": "user@example.com", "HIGGSFIELD_PASSWORD": "pw"}):
          from higgsfield_api import run_generation
          result = run_generation(str(img_path))

      assert result == {"status": "success", "links": ["u1", "u2", "u3", "u4"]}


  def test_run_generation_returns_error_on_exception(tmp_path):
      img_path = tmp_path / "test.jpg"
      from PIL import Image as PILImage
      PILImage.new("RGB", (100, 100)).save(img_path)

      with patch("higgsfield_api.get_jwt", side_effect=RuntimeError("Login failed (401)")), \
           patch.dict("os.environ", {"HIGGSFIELD_EMAIL": "u@e.com", "HIGGSFIELD_PASSWORD": "pw"}):
          from higgsfield_api import run_generation
          result = run_generation(str(img_path))

      assert result["status"] == "error"
      assert "Login failed" in result["message"]


  def test_run_generation_errors_without_credentials(tmp_path):
      img_path = tmp_path / "test.jpg"
      from PIL import Image as PILImage
      PILImage.new("RGB", (100, 100)).save(img_path)

      with patch.dict("os.environ", {}, clear=True):
          from higgsfield_api import run_generation
          result = run_generation(str(img_path))

      assert result["status"] == "error"
      assert "HIGGSFIELD_EMAIL" in result["message"]
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  pytest tests/test_higgsfield_api.py::test_run_generation_returns_success tests/test_higgsfield_api.py::test_run_generation_returns_error_on_exception tests/test_higgsfield_api.py::test_run_generation_errors_without_credentials -v
  ```

- [ ] **Step 3: Implement run_generation() and main()**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def run_generation(image_path: str) -> dict:
      """Full pipeline: auth → upload → generate → poll → share links."""
      load_dotenv()
      email    = os.environ.get("HIGGSFIELD_EMAIL", "")
      password = os.environ.get("HIGGSFIELD_PASSWORD", "")
      if not email or not password:
          return {"status": "error", "message": "HIGGSFIELD_EMAIL and HIGGSFIELD_PASSWORD must be set in .env"}
      try:
          from get_aspect_ratio import closest_ratio
          with Image.open(image_path) as img:
              aspect_ratio = closest_ratio(*img.size)

          jwt                  = get_jwt(email, password)
          media_id, media_url  = upload_image(jwt, image_path)
          job_ids              = start_generation(jwt, media_id, media_url, aspect_ratio)
          poll_jobs(jwt, job_ids)
          links                = get_share_links(jwt, job_ids)
          return {"status": "success", "links": links}
      except Exception as e:
          return {"status": "error", "message": str(e)}


  def main():
      parser = argparse.ArgumentParser(description="Generate FUFU variations on Higgsfield via API")
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
  ```

- [ ] **Step 4: Run full test suite**

  ```bash
  pytest tests/test_higgsfield_api.py -v
  ```
  Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: add run_generation() integration and CLI entrypoint"
  ```

---

### Task 9: Update SKILL.md, requirements.txt, .env.example — retire old script

**Files:**
- Modify: `skills/higgsfield-generate/SKILL.md`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Delete: `scripts/generate_fufu.py`
- Delete: `tests/test_generate_fufu.py`

> **DataDome note:** If any `fnf.higgsfield.ai` endpoint returns 403 after implementation (DataDome blocking non-browser clients), add `curl_cffi>=0.7.0` to requirements and replace `httpx.Client` with `curl_cffi.requests.Session(impersonate="firefox120")` in `_api_headers` callers.

- [ ] **Step 1: Update requirements.txt**

  Replace the entire contents of `requirements.txt` with:
  ```
  httpx>=0.27.0
  python-dotenv==1.2.1
  Pillow==12.1.1
  pytest>=8.0.0
  ```

- [ ] **Step 2: Install updated requirements**

  ```bash
  pip install -r requirements.txt
  ```

- [ ] **Step 3: Update .env.example**

  Replace `.env.example` with:
  ```env
  # Higgsfield account credentials
  HIGGSFIELD_EMAIL=your@email.com
  HIGGSFIELD_PASSWORD=your-password

  # Telegram (configured via Hermes gateway)
  TELEGRAM_BOT_TOKEN=<from BotFather>
  TELEGRAM_ALLOWED_USERS=5938713749,1004169493
  ```

- [ ] **Step 4: Update SKILL.md Phase 2 section**

  In `skills/higgsfield-generate/SKILL.md`, replace the Phase 2 "Run Generation" section:

  ```markdown
  ### Phase 2: Run Generation

  3. Run the API generation script:
     ```bash
     ~/HiggsfieldAgent/.venv/bin/python \
       ~/HiggsfieldAgent/scripts/higgsfield_api.py \
       "IMAGE_PATH"
     ```

     The script outputs JSON to stdout:
     - Success: `{"status": "success", "links": ["url1", "url2", "url3", "url4"]}`
     - Error: `{"status": "error", "message": "..."}`

     **This takes approximately 8–10 minutes** (Higgsfield server generation time — not automation overhead).
     The script handles login, image upload, generation trigger, polling, and share link extraction automatically.

     On first run (or after session expiry), the script will prompt:
     ```
     Enter the verification code sent to your email:
     ```
     Enter the 6-digit code from the account email. Subsequent runs reuse the cached session.
  ```

- [ ] **Step 5: Update SKILL.md Environment Setup section**

  Replace the Environment Setup section with:

  ```markdown
  ## Environment Setup

  - **Python venv** at `.venv/` in the repo root:
    ```bash
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    ```

  - **`HIGGSFIELD_EMAIL`** and **`HIGGSFIELD_PASSWORD`** set in `.env` at repo root

  - No Chrome, browser, or LLM required

  - Session cached at `~/.higgsfield_session` — delete this file to force re-login
  ```

- [ ] **Step 6: Update SKILL.md Pitfalls section**

  Replace the "Session expired" and "Chrome not starting" pitfalls with:
  ```markdown
  - **Auth failure / OTP prompt on every run**: If the script keeps asking for a verification code,
    the cached session at `~/.higgsfield_session` is expiring. This is normal; enter the code from
    email. If credentials are wrong, verify `HIGGSFIELD_EMAIL` and `HIGGSFIELD_PASSWORD` in `.env`.
  - **403 from fnf.higgsfield.ai**: DataDome may be blocking the httpx client. Add `curl_cffi` to
    requirements and switch to `curl_cffi.requests.Session(impersonate="firefox120")`.
  ```

- [ ] **Step 7: Run full test suite before deleting old files**

  ```bash
  pytest tests/ -v
  ```
  Expected: all tests in `test_higgsfield_api.py` and `test_get_aspect_ratio.py` pass.

- [ ] **Step 8: Delete old script and tests**

  ```bash
  git rm scripts/generate_fufu.py tests/test_generate_fufu.py
  ```

- [ ] **Step 9: Run tests again — confirm clean**

  ```bash
  pytest tests/ -v
  ```

- [ ] **Step 10: Final commit**

  ```bash
  git add -A
  git commit -m "feat: replace browser-use with direct Higgsfield HTTP API client

  - Add scripts/higgsfield_api.py: Clerk login + OTP + session cache + S3 upload + generate + poll + share links
  - Remove scripts/generate_fufu.py and browser-use/LLM dependency
  - Remove GOOGLE_API_KEY; add HIGGSFIELD_EMAIL / HIGGSFIELD_PASSWORD
  - Update SKILL.md: no Chrome needed, session cached at ~/.higgsfield_session
  - Update requirements.txt: drop browser-use, langchain-google-genai"
  ```
