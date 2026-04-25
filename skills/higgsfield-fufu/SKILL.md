---
name: higgsfield-fufu
description: When the user sends one or more photos on Telegram, generate 4 Higgsfield FUFU Soul v2 variations for each image and send the results back.
version: 3.0.0
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
    category: creative
---

# Higgsfield FUFU Generator

Generates 4 Soul v2 FUFU character variations from an inspiration photo using the
Higgsfield direct HTTP API. No browser or Chrome required.

## When to Use

Activate this skill whenever the user sends a photo or image file on Telegram —
including when they send multiple photos in one message or across successive messages
asking for generation.

If the user sends a text message with no image, reply:
"Send me an image and I'll generate FUFU variations on Higgsfield."

## Procedure

1. **Inform the user upfront** before running anything:
   - Single photo: "Got your image! Generating 4 variations — this takes about 8 minutes ⏳"
   - Multiple photos: "Got {N} images! Processing one at a time — about 8 minutes each ⏳"

2. **Check for first-time login.** If `~/.higgsfield_session` does not exist, the script
   will perform a full Clerk login including OTP verification. With `HIGGSFIELD_AUTO_OTP=1`
   set, the OTP is fetched automatically from Gmail via `$GAPI` — no manual input needed.

3. **Process each photo one at a time.** For every received photo path (in order):

   a. Run the generation script:
   ```bash
   HIGGSFIELD_AUTO_OTP=1 python3 ~/HiggsfieldAgent/scripts/higgsfield_api.py "<photo_path>"
   ```

   b. Parse the JSON result from stdout:
   - `"status": "error"` → reply with the error message, continue to next photo.
   - `"status": "success"` → extract `local_paths` (4 PNG files) and `links` (4 share URLs).

   c. Send each of the 4 files in `local_paths` to the user as Telegram **photos**
   (not as documents). Caption the first image:
   ```
   Generated 4 variations ✅
   1. <links[0]>
   2. <links[1]>
   3. <links[2]>
   4. <links[3]>
   ```

   d. When processing multiple photos, announce progress before each one:
   > "Processing photo 2 of 3…"

## Environment Setup

Requires on the host machine:

- **Repo cloned** at `~/HiggsfieldAgent`
- **Python dependencies** installed:
  ```bash
  python3 -m pip install "curl_cffi>=0.7.0" python-dotenv Pillow --break-system-packages
  ```
- **`~/.hermes/profiles/higgsfield/.env`** containing:
  ```
  HIGGSFIELD_EMAIL=...
  HIGGSFIELD_PASSWORD=...
  HIGGSFIELD_AUTO_OTP=1
  ```
- **Gmail OAuth** set up via the Google Workspace skill (`$GAPI`) for auto-OTP fetching.
  See `docs/superpowers/plans/2026-04-25-hermes-higgsfield-profile-setup.md` Task 4.

## Pitfalls

- **Auto-OTP Gmail polling:** The script polls Gmail every 10 seconds for up to 2 minutes
  after the OTP email is sent. If the email is delayed, the run fails with
  "no verification email found". Retry once — the email usually arrives within 30 seconds.
- **OTP only needed once.** After `~/.higgsfield_session` is created, the Clerk session
  is reused on every run. OTP is only triggered again if the cached session expires
  (~30 days).
- **Generation takes ~8 minutes.** Always notify the user before starting. Do not timeout.
- **Multiple photos:** Process sequentially. Parallel runs would exhaust Higgsfield credits
  and cause S3 upload collisions.
- **Downloaded images** are saved next to the input photo as `{stem}_out_1.png` …
  `{stem}_out_4.png`. Make sure the input path's directory is writable.

## Verification

- Script exits 0 and prints `{"status": "success", "links": [...], "local_paths": [...]}`.
- 4 PNG files exist at the `local_paths` returned.
- All 4 images are delivered to the user on Telegram with share link captions.
