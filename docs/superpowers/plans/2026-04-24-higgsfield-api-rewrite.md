# Higgsfield API Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the browser-use/LLM/Chrome automation pipeline with a direct HTTP API client that drives Higgsfield's REST API using email/password auth, reducing generation overhead from ~10 minutes to ~30 seconds.

**Architecture:** Two phases. Phase 1 (Tasks 1–2) is reconnaissance: capture Higgsfield's API traffic with Burp Suite and produce an endpoint map. Phase 2 (Tasks 3–9) is implementation: build `scripts/higgsfield_api.py` as a drop-in replacement for `scripts/generate_fufu.py` with the same CLI interface and JSON output contract. Browser-use, Chrome, and the Gemini LLM are removed entirely.

**Tech Stack:** Python 3.11+, httpx, python-dotenv, Pillow (already installed)

---

## Phase 1: Reconnaissance

### Task 1: Burp Suite capture session

**Files:** None — user action only.

> ⚠️ This task must be completed before any Phase 2 tasks begin. Do not proceed to Task 2 until this capture is done.

- [ ] **Step 1: Install Burp Suite Community Edition**

  Download from https://portswigger.net/burp/communitydownload. Install and launch.

- [ ] **Step 2: Confirm proxy listener**

  In Burp: Proxy → Proxy settings → confirm listener is `127.0.0.1:8080`.

- [ ] **Step 3: Install Burp's CA certificate into Chrome**

  With Burp running, open Chrome → navigate to `http://burp` → Download CA Certificate → save as `burp-cert.der`.
  Chrome settings → Privacy and Security → Manage Certificates → Authorities tab → Import → select the `.der` file → trust for identifying websites.

- [ ] **Step 4: Launch Chrome through Burp proxy**

  Close all Chrome windows, then on Windows launch:
  ```
  "C:\Program Files\Google\Chrome\Application\chrome.exe" --proxy-server="http://127.0.0.1:8080" --ignore-certificate-errors
  ```

- [ ] **Step 5: Set Burp intercept OFF**

  In Burp: Proxy → Intercept → click "Intercept is on" to toggle it OFF. Traffic flows through while being logged.

- [ ] **Step 6: Log in to Higgsfield**

  Navigate to `https://higgsfield.ai` in the proxied Chrome. Log in with your email and password. Confirm you see `higgsfield.ai` entries appearing in Burp's HTTP history.

- [ ] **Step 7: Do one complete manual generation**

  Navigate to `https://higgsfield.ai/mobile/image/soul-v2`. Perform the full flow:
  - Upload an image
  - Select FUFU / Soul 2.0 character
  - Set aspect ratio, Batch 4, Quality 2K
  - Click Generate
  - Wait for the 4 images to complete (~8 min)
  - Open each image's share link

- [ ] **Step 8: Export HTTP history**

  Burp: Proxy → HTTP history → filter Host column to `higgsfield.ai` and related subdomains (e.g., `api.higgsfield.ai`). Select all filtered rows → right-click → Save items → save as `higgsfield-capture.xml`.

- [ ] **Step 9: Redact and share with Copilot**

  **Before sharing**, redact all secret values:
  - `Authorization: Bearer <REDACTED_JWT>`
  - `Cookie: <REDACTED_COOKIES>`
  - Any `x-api-key` / `x-auth-token` header values
  - S3 presigned URL params (`X-Amz-Signature=<REDACTED>`)
  - Your email address → `user@example.com`

  Then log out of Higgsfield and log back in to invalidate the captured session.

  Share the redacted XML (or ~8–12 key API calls as cURL commands) with Copilot in the chat.

---

### Task 2: Endpoint map (Copilot produces after Task 1)

**Files:** `docs/superpowers/plans/2026-04-24-higgsfield-api-rewrite-endpoints.md` (Copilot creates this)

After receiving the Burp capture, Copilot produces an endpoint map containing:
- Base URL
- Auth endpoint (path, method, request body shape, JWT field in response)
- Upload endpoint(s) (path, method — multipart POST or presigned URL two-step flow)
- Generation endpoint (path, method, request body fields, job ID field in response)
- Polling endpoint (path, method, status field name, completion value, error values)
- Assets endpoint (path, response shape, asset ID/URL fields)
- Share link endpoint (or confirmation that asset URL = share URL)
- All required headers per request group
- JWT lifetime (if readable from token expiry)

> ⚠️ **Phase 2 tasks use `[FILL FROM BURP]` markers** where endpoint-specific details are needed. Before starting Task 3, update the constants block in `higgsfield_api.py` using the endpoint map from this task.

---

## Phase 2: Implementation

> **Prerequisite:** Task 2 endpoint map must be complete before starting any Phase 2 task. Update the `[FILL FROM BURP]` constants in Task 3 before implementing Tasks 4–9.

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
  """
  import argparse
  import json
  import os
  import sys
  import time
  from pathlib import Path

  import httpx
  from dotenv import load_dotenv
  from PIL import Image

  # ---------------------------------------------------------------------------
  # API constants — fill in from endpoint map (Task 2) before implementing
  # ---------------------------------------------------------------------------
  BASE_URL = "https://higgsfield.ai"           # [FILL FROM BURP]
  LOGIN_PATH = "/api/auth/login"               # [FILL FROM BURP]
  UPLOAD_PATH = "/api/upload"                  # [FILL FROM BURP]
  GENERATE_PATH = "/api/generate"              # [FILL FROM BURP]
  JOB_STATUS_PATH = "/api/jobs/{job_id}"       # [FILL FROM BURP]
  ASSETS_PATH = "/api/assets"                  # [FILL FROM BURP]
  SHARE_PATH = "/api/share/{asset_id}"         # [FILL FROM BURP] or None if asset URL = share URL

  FUFU_CHARACTER_ID = "fufu"                   # [FILL FROM BURP] — actual character ID value
  SOUL_V2_QUALITY = "2K"                       # [FILL FROM BURP] — actual quality param value
  SOUL_V2_BATCH = 4                            # [FILL FROM BURP] — actual batch size param value

  GENERATION_POLL_INTERVAL = 15               # seconds between status checks
  GENERATION_TIMEOUT = 900                    # 15 minutes max

  COMMON_HEADERS = {
      "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Accept": "application/json",
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
  git commit -m "feat: scaffold higgsfield_api.py with constants block"
  ```

---

### Task 4: Login module

> Fill in `LOGIN_PATH`, request body shape, and JWT response field from endpoint map before coding.

**Files:**
- Modify: `scripts/higgsfield_api.py`
- Modify: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Write failing tests for login()**

  Add to `tests/test_higgsfield_api.py`:

  ```python
  def test_login_returns_jwt_on_success():
      mock_resp = MagicMock()
      mock_resp.status_code = 200
      mock_resp.json.return_value = {"token": "test.jwt.token"}  # [adjust field name from endpoint map]
      with patch("httpx.Client.post", return_value=mock_resp):
          from higgsfield_api import login
          token = login("user@example.com", "password123")
      assert token == "test.jwt.token"


  def test_login_raises_on_bad_credentials():
      mock_resp = MagicMock()
      mock_resp.status_code = 401
      mock_resp.text = "Unauthorized"
      with patch("httpx.Client.post", return_value=mock_resp):
          from higgsfield_api import login
          with pytest.raises(RuntimeError, match="Login failed"):
              login("user@example.com", "wrongpassword")
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  pytest tests/test_higgsfield_api.py::test_login_returns_jwt_on_success tests/test_higgsfield_api.py::test_login_raises_on_bad_credentials -v
  ```
  Expected: `ImportError` or `FAILED`

- [ ] **Step 3: Implement login()**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def login(email: str, password: str) -> str:
      """POST credentials, return JWT. Raises RuntimeError on failure."""
      with httpx.Client(headers=COMMON_HEADERS) as client:
          resp = client.post(
              BASE_URL + LOGIN_PATH,
              json={"email": email, "password": password},  # [FILL FROM BURP — adjust field names]
          )
      if resp.status_code != 200:
          raise RuntimeError(f"Login failed ({resp.status_code}): {resp.text[:200]}")
      data = resp.json()
      return data["token"]  # [FILL FROM BURP — adjust JWT field name]
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  pytest tests/test_higgsfield_api.py::test_login_returns_jwt_on_success tests/test_higgsfield_api.py::test_login_raises_on_bad_credentials -v
  ```
  Expected: `PASSED`

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: add login() with email/password → JWT"
  ```

---

### Task 5: Image upload module

> Fill in upload endpoint details from endpoint map (single-step multipart POST, or two-step presigned S3 URL flow).

**Files:**
- Modify: `scripts/higgsfield_api.py`
- Modify: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Write failing test for upload_image()**

  Add to `tests/test_higgsfield_api.py`:

  ```python
  def test_upload_image_returns_asset_key(tmp_path):
      img_path = tmp_path / "test.png"
      from PIL import Image as PILImage
      PILImage.new("RGB", (10, 10), color="red").save(img_path)

      mock_resp = MagicMock()
      mock_resp.status_code = 200
      mock_resp.json.return_value = {"key": "uploads/abc123.png"}  # [adjust from endpoint map]

      with patch("httpx.Client.post", return_value=mock_resp):
          from higgsfield_api import upload_image
          key = upload_image("test.jwt.token", str(img_path))
      assert key == "uploads/abc123.png"
  ```

- [ ] **Step 2: Run test to confirm it fails**

  ```bash
  pytest tests/test_higgsfield_api.py::test_upload_image_returns_asset_key -v
  ```
  Expected: `FAILED`

- [ ] **Step 3: Implement upload_image()**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def upload_image(jwt: str, image_path: str) -> str:
      """Upload image file, return the asset key/ID for use in generation.

      [FILL FROM BURP]: If Higgsfield uses a presigned S3 URL, this will be two calls:
          1. POST to get presigned URL → 2. PUT file to S3 URL → return the key.
      """
      headers = {**COMMON_HEADERS, "Authorization": f"Bearer {jwt}"}
      with open(image_path, "rb") as f:
          with httpx.Client(headers=headers) as client:
              resp = client.post(
                  BASE_URL + UPLOAD_PATH,
                  files={"file": (Path(image_path).name, f, "image/jpeg")},  # [FILL FROM BURP — multipart field name]
              )
      if resp.status_code not in (200, 201):
          raise RuntimeError(f"Upload failed ({resp.status_code}): {resp.text[:200]}")
      return resp.json()["key"]  # [FILL FROM BURP — adjust field name]
  ```

- [ ] **Step 4: Run test to confirm it passes**

  ```bash
  pytest tests/test_higgsfield_api.py::test_upload_image_returns_asset_key -v
  ```
  Expected: `PASSED`

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: add upload_image() — multipart POST, returns asset key"
  ```

---

### Task 6: Generation trigger module

> Fill in generate endpoint path, request body field names, and job ID field from endpoint map.

**Files:**
- Modify: `scripts/higgsfield_api.py`
- Modify: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Write failing test for start_generation()**

  Add to `tests/test_higgsfield_api.py`:

  ```python
  def test_start_generation_returns_job_id():
      mock_resp = MagicMock()
      mock_resp.status_code = 200
      mock_resp.json.return_value = {"jobId": "job_xyz789"}  # [adjust from endpoint map]

      with patch("httpx.Client.post", return_value=mock_resp):
          from higgsfield_api import start_generation
          job_id = start_generation("test.jwt.token", "uploads/abc123.png", "16:9")
      assert job_id == "job_xyz789"
  ```

- [ ] **Step 2: Run test to confirm it fails**

  ```bash
  pytest tests/test_higgsfield_api.py::test_start_generation_returns_job_id -v
  ```
  Expected: `FAILED`

- [ ] **Step 3: Implement start_generation()**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def start_generation(jwt: str, asset_key: str, aspect_ratio: str) -> str:
      """Trigger FUFU generation job. Returns job ID string."""
      headers = {**COMMON_HEADERS, "Authorization": f"Bearer {jwt}"}
      payload = {
          "characterId": FUFU_CHARACTER_ID,   # [FILL FROM BURP — adjust field name]
          "imageKey": asset_key,              # [FILL FROM BURP — adjust field name]
          "aspectRatio": aspect_ratio,        # [FILL FROM BURP — adjust field name and value format]
          "batchSize": SOUL_V2_BATCH,         # [FILL FROM BURP — adjust field name]
          "quality": SOUL_V2_QUALITY,         # [FILL FROM BURP — adjust field name]
      }
      with httpx.Client(headers=headers) as client:
          resp = client.post(BASE_URL + GENERATE_PATH, json=payload)
      if resp.status_code not in (200, 201, 202):
          raise RuntimeError(f"Generation failed ({resp.status_code}): {resp.text[:200]}")
      return resp.json()["jobId"]  # [FILL FROM BURP — adjust field name]
  ```

- [ ] **Step 4: Run test to confirm it passes**

  ```bash
  pytest tests/test_higgsfield_api.py::test_start_generation_returns_job_id -v
  ```
  Expected: `PASSED`

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: add start_generation() — triggers FUFU Soul v2 job"
  ```

---

### Task 7: Polling + share links module

> Fill in job status endpoint, status field values, asset ID fields, and share link endpoint from endpoint map.

**Files:**
- Modify: `scripts/higgsfield_api.py`
- Modify: `tests/test_higgsfield_api.py`

- [ ] **Step 1: Write failing tests for poll_generation() and get_share_links()**

  Add to `tests/test_higgsfield_api.py`:

  ```python
  def test_poll_generation_returns_asset_ids_when_complete():
      responses = [
          MagicMock(status_code=200, json=lambda: {"status": "processing", "assets": []}),
          MagicMock(status_code=200, json=lambda: {"status": "complete", "assets": ["id1", "id2", "id3", "id4"]}),
      ]
      with patch("httpx.Client.get", side_effect=responses):
          with patch("time.sleep"):
              from higgsfield_api import poll_generation
              asset_ids = poll_generation("test.jwt.token", "job_xyz789")
      assert asset_ids == ["id1", "id2", "id3", "id4"]


  def test_poll_generation_raises_on_timeout():
      always_processing = MagicMock(
          status_code=200,
          json=lambda: {"status": "processing", "assets": []}
      )
      with patch("httpx.Client.get", return_value=always_processing):
          with patch("time.sleep"):
              from higgsfield_api import poll_generation
              with pytest.raises(RuntimeError, match="timed out"):
                  poll_generation("test.jwt.token", "job_xyz789", timeout=-1)


  def test_get_share_links_returns_four_urls():
      mock_resp = MagicMock()
      mock_resp.status_code = 200
      mock_resp.json.return_value = {"shareUrl": "https://higgsfield.ai/share/abc"}

      with patch("httpx.Client.get", return_value=mock_resp):
          from higgsfield_api import get_share_links
          links = get_share_links("test.jwt.token", ["id1", "id2", "id3", "id4"])

      assert len(links) == 4
      assert all(link.startswith("https://") for link in links)
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  pytest tests/test_higgsfield_api.py::test_poll_generation_returns_asset_ids_when_complete tests/test_higgsfield_api.py::test_poll_generation_raises_on_timeout tests/test_higgsfield_api.py::test_get_share_links_returns_four_urls -v
  ```
  Expected: `FAILED`

- [ ] **Step 3: Implement poll_generation() and get_share_links()**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def poll_generation(jwt: str, job_id: str, timeout: int = GENERATION_TIMEOUT) -> list[str]:
      """Poll job status until complete. Returns list of asset IDs. Raises RuntimeError on timeout."""
      headers = {**COMMON_HEADERS, "Authorization": f"Bearer {jwt}"}
      deadline = time.time() + timeout
      url = BASE_URL + JOB_STATUS_PATH.format(job_id=job_id)  # [FILL FROM BURP — adjust URL pattern]
      while time.time() < deadline:
          with httpx.Client(headers=headers) as client:
              resp = client.get(url)
          if resp.status_code != 200:
              raise RuntimeError(f"Poll failed ({resp.status_code}): {resp.text[:200]}")
          data = resp.json()
          status = data.get("status", "")       # [FILL FROM BURP — adjust status field name]
          if status == "complete":              # [FILL FROM BURP — adjust completion value]
              return data["assets"]             # [FILL FROM BURP — adjust asset IDs field]
          if status in ("failed", "error"):     # [FILL FROM BURP — adjust error status values]
              raise RuntimeError(f"Generation failed: {data}")
          time.sleep(GENERATION_POLL_INTERVAL)
      raise RuntimeError(f"Generation timed out after {timeout}s")


  def get_share_links(jwt: str, asset_ids: list[str]) -> list[str]:
      """Fetch share URL for each asset. Returns list of 4 share URLs.

      [FILL FROM BURP]: If the asset URL from poll response IS the share URL, return asset_ids directly.
      """
      headers = {**COMMON_HEADERS, "Authorization": f"Bearer {jwt}"}
      links = []
      for asset_id in asset_ids:
          url = BASE_URL + SHARE_PATH.format(asset_id=asset_id)  # [FILL FROM BURP]
          with httpx.Client(headers=headers) as client:
              resp = client.get(url)
          if resp.status_code != 200:
              raise RuntimeError(f"Share link failed for {asset_id} ({resp.status_code})")
          links.append(resp.json()["shareUrl"])  # [FILL FROM BURP — adjust field name]
      return links
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  pytest tests/test_higgsfield_api.py::test_poll_generation_returns_asset_ids_when_complete tests/test_higgsfield_api.py::test_poll_generation_raises_on_timeout tests/test_higgsfield_api.py::test_get_share_links_returns_four_urls -v
  ```
  Expected: `PASSED`

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/higgsfield_api.py tests/test_higgsfield_api.py
  git commit -m "feat: add poll_generation() and get_share_links()"
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
      img_path = tmp_path / "test.png"
      from PIL import Image as PILImage
      PILImage.new("RGB", (1920, 1080), color="blue").save(img_path)

      with patch("higgsfield_api.login", return_value="jwt_tok"), \
           patch("higgsfield_api.upload_image", return_value="uploads/x.png"), \
           patch("higgsfield_api.start_generation", return_value="job_123"), \
           patch("higgsfield_api.poll_generation", return_value=["a1", "a2", "a3", "a4"]), \
           patch("higgsfield_api.get_share_links", return_value=["u1", "u2", "u3", "u4"]), \
           patch.dict("os.environ", {"HIGGSFIELD_EMAIL": "user@example.com", "HIGGSFIELD_PASSWORD": "pw"}):
          from higgsfield_api import run_generation
          result = run_generation(str(img_path))

      assert result == {"status": "success", "links": ["u1", "u2", "u3", "u4"]}


  def test_run_generation_returns_error_on_exception(tmp_path):
      img_path = tmp_path / "test.png"
      from PIL import Image as PILImage
      PILImage.new("RGB", (100, 100)).save(img_path)

      with patch("higgsfield_api.login", side_effect=RuntimeError("Login failed (401): bad creds")), \
           patch.dict("os.environ", {"HIGGSFIELD_EMAIL": "u@e.com", "HIGGSFIELD_PASSWORD": "pw"}):
          from higgsfield_api import run_generation
          result = run_generation(str(img_path))

      assert result["status"] == "error"
      assert "Login failed" in result["message"]


  def test_run_generation_errors_without_credentials(tmp_path):
      img_path = tmp_path / "test.png"
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
  Expected: `FAILED`

- [ ] **Step 3: Implement get_aspect_ratio_for_image(), run_generation(), and main()**

  Add to `scripts/higgsfield_api.py`:

  ```python
  def get_aspect_ratio_for_image(image_path: str) -> str:
      with Image.open(image_path) as img:
          width, height = img.size
      from get_aspect_ratio import closest_ratio
      return closest_ratio(width, height)


  def run_generation(image_path: str) -> dict:
      """Full pipeline: login → upload → generate → poll → share links."""
      load_dotenv()
      email = os.environ.get("HIGGSFIELD_EMAIL", "")
      password = os.environ.get("HIGGSFIELD_PASSWORD", "")
      if not email or not password:
          return {"status": "error", "message": "HIGGSFIELD_EMAIL and HIGGSFIELD_PASSWORD must be set"}
      try:
          aspect_ratio = get_aspect_ratio_for_image(image_path)
          jwt = login(email, password)
          asset_key = upload_image(jwt, image_path)
          job_id = start_generation(jwt, asset_key, aspect_ratio)
          asset_ids = poll_generation(jwt, job_id)
          links = get_share_links(jwt, asset_ids)
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

- [ ] **Step 1: Update requirements.txt**

  Replace the entire contents of `requirements.txt` with:
  ```
  httpx>=0.27.0
  python-dotenv==1.2.1
  Pillow==12.1.1
  pytest>=8.0.0
  ```

  > If Higgsfield returns 403 on any endpoint (TLS fingerprinting), add `curl_cffi>=0.7.0` to requirements and swap `httpx.Client` for `curl_cffi.requests.Session(impersonate="chrome120")`.

- [ ] **Step 2: Install updated requirements**

  ```bash
  pip install -r requirements.txt
  ```
  Expected: httpx, python-dotenv, Pillow, pytest installed; browser-use and langchain removed.

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

     **This takes approximately 8-10 minutes** (Higgsfield generation time — the API wait, not automation overhead).
     The script handles: login, image upload, generation trigger, polling, and share link extraction automatically.
  ```

- [ ] **Step 5: Update SKILL.md Environment Setup section**

  Replace the Environment Setup section with:

  ```markdown
  ## Environment Setup

  - **Python venv** at `.venv/` in the repo root with dependencies installed:
    ```bash
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    ```

  - **HIGGSFIELD_EMAIL** and **HIGGSFIELD_PASSWORD** set in `.env` at repo root

  - No Chrome, browser, or LLM required
  ```

- [ ] **Step 6: Update SKILL.md Pitfalls section**

  Replace the "Session expired" pitfall with:
  ```markdown
  - **Auth failure**: If the script returns `"Login failed (401)"`, verify `HIGGSFIELD_EMAIL` and
    `HIGGSFIELD_PASSWORD` in `.env` are correct and the account is active.
  ```

  Remove the "Chrome not starting" pitfall entirely.

- [ ] **Step 7: Run full test suite before deleting old files**

  ```bash
  pytest tests/ -v
  ```
  Expected: `test_higgsfield_api.py` and `test_get_aspect_ratio.py` all pass.

- [ ] **Step 8: Delete old script and tests**

  ```bash
  git rm scripts/generate_fufu.py tests/test_generate_fufu.py
  ```

- [ ] **Step 9: Run tests again — confirm clean**

  ```bash
  pytest tests/ -v
  ```
  Expected: only `test_higgsfield_api.py` and `test_get_aspect_ratio.py` present, all passing.

- [ ] **Step 10: Final commit**

  ```bash
  git add -A
  git commit -m "feat: replace browser-use with direct Higgsfield HTTP API client

  - Add scripts/higgsfield_api.py: login + upload + generate + poll + share links
  - Remove scripts/generate_fufu.py and browser-use dependency
  - Remove GOOGLE_API_KEY; add HIGGSFIELD_EMAIL / HIGGSFIELD_PASSWORD
  - Update SKILL.md: no Chrome needed, automation overhead ~0s vs 10-15min
  - Update requirements.txt: drop browser-use, langchain-google-genai

  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
  ```
