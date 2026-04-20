---
name: higgsfield-generate
description: Generate FUFU character variations on Higgsfield from a Telegram inspiration image.
version: 1.0.0
metadata:
  hermes:
    tags: [image-generation, higgsfield, telegram, browser-automation]
    category: creative
    requires_toolsets: [browser]
    config:
      - key: browser_profile
        description: "Path to persistent browser profile for Higgsfield login"
        default: "~/.hermes/browser-profiles/higgsfield"
        prompt: "Browser profile path for Higgsfield sessions"
---

# Higgsfield FUFU Generator

Generate 4 FUFU character variations from an inspiration image using Higgsfield's
Soul v2 web app, then send the share links back to the user on Telegram.

## When to Use

Use this skill when a user sends a photo/image in a Telegram chat. The image is the
inspiration reference for Higgsfield generation.

If the user sends a text message with no image, reply with:
"Send me an image and I'll generate FUFU variations on Higgsfield."

## Procedure

### Phase 1: Confirm and Prepare

1. Send a message to the user on Telegram:
   "Got your image! Starting Higgsfield generation — this takes about 8-10 minutes."

2. Determine the image aspect ratio by running:
   ```
   python scripts/get_aspect_ratio.py <image_path>
   ```
   The script prints one of: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `9:16`, `16:9`.
   Save the output as `ASPECT_RATIO`.

### Phase 2: Navigate and Configure Higgsfield

3. Navigate to the Higgsfield Soul v2 page:
   ```
   browser_navigate(url="https://higgsfield.ai/mobile/image/soul-v2")
   ```

4. Take a snapshot to verify the page loaded and identify elements:
   ```
   browser_snapshot()
   ```
   Confirm the page contains the Soul v2 generation interface. If the page shows a
   login screen instead, send this message to Telegram and stop:
   "Higgsfield session expired. Please log in manually and try again."

5. Click the **"Image Reference"** tab at the top of the page:
   ```
   browser_click(ref="<ref for Image Reference tab>")
   ```

6. Take a snapshot to see the Soul Character options:
   ```
   browser_snapshot()
   ```

7. Click the **"FUFU"** Soul Character:
   ```
   browser_click(ref="<ref for FUFU>")
   ```

8. Take a snapshot to find the image upload element:
   ```
   browser_snapshot()
   ```

9. Click the image upload area/button to trigger the file chooser, then provide
   the user's image file path. If the upload area is a file input element, click
   it and the browser will handle the file chooser with the provided path:
   ```
   browser_click(ref="<ref for upload area/input>")
   ```
   Provide the image file path from the Telegram message attachment.

10. Take a snapshot to verify the image uploaded successfully:
    ```
    browser_snapshot()
    ```
    Confirm the upload area now shows a preview of the image rather than an empty
    drop zone. If the preview is not visible, use `browser_vision` to visually
    verify:
    ```
    browser_vision(prompt="Is there an uploaded image preview visible in the upload area?")
    ```

11. Select the aspect ratio that matches `ASPECT_RATIO` (from step 2):
    ```
    browser_click(ref="<ref for ASPECT_RATIO button>")
    ```

12. Set **Batch Size** to **4**:
    ```
    browser_click(ref="<ref for batch size 4>")
    ```

13. Set **Quality** to **2K**:
    ```
    browser_click(ref="<ref for 2K quality>")
    ```

### Phase 3: Pre-Generation Checklist

14. Take a full snapshot to verify all settings:
    ```
    browser_snapshot(full=true)
    ```

15. Verify ALL of the following in the snapshot. Check each one:

    - [ ] **Image Reference tab** is the active/selected tab
    - [ ] **FUFU** is the selected Soul Character (highlighted/active)
    - [ ] **Image uploaded** — the upload area shows a preview, not an empty state
    - [ ] **Aspect ratio** — the button matching `ASPECT_RATIO` is selected/highlighted
    - [ ] **Batch Size = 4** — the "4" option is selected
    - [ ] **Quality = 2K** — the "2K" option is selected

    If the text snapshot is insufficient to confirm these visually, use:
    ```
    browser_vision(prompt="Verify: Is Image Reference tab active? Is FUFU selected? Is an image uploaded? What aspect ratio is selected? What batch size? What quality setting?")
    ```

16. If **any** check fails, send a message to Telegram specifying which check
    failed, and **DO NOT** proceed to generation:
    "Generation aborted — pre-check failed: [specific check that failed]. Please try again."
    Stop here.

### Phase 4: Generate

17. Click the **Generate** button:
    ```
    browser_click(ref="<ref for Generate button>")
    ```

18. Take a snapshot to confirm generation started:
    ```
    browser_snapshot()
    ```
    Look for a progress indicator, loading spinner, or confirmation that the job
    was submitted. If generation did not start (e.g., an error message appeared),
    send a failure message to Telegram and stop:
    "Generation failed to start: [error message from page]. Please try again."

### Phase 5: Wait and Collect Results

19. Wait **8 minutes** for the images to generate.

20. Navigate to the assets page:
    ```
    browser_navigate(url="https://higgsfield.ai/asset/image")
    ```

21. Take a snapshot to check if the images are ready:
    ```
    browser_snapshot()
    ```
    Look at the top 4 images in the grid. Check for:
    - Completed status (no loading spinners or progress bars)
    - Recent timestamps matching this generation job

    If images are still loading or not yet visible, use `browser_vision` to
    visually check:
    ```
    browser_vision(prompt="Are the top 4 images in the grid fully loaded and complete, or are any still showing loading/progress indicators?")
    ```

22. If images are **NOT ready**:
    - Wait **7 more minutes** (15 minutes total from generation start).
    - Navigate to the assets page again:
      ```
      browser_navigate(url="https://higgsfield.ai/asset/image")
      ```
    - Take another snapshot and re-check:
      ```
      browser_snapshot()
      ```

23. If images are **STILL NOT ready** after 15 minutes total, send a failure
    message to Telegram and stop:
    "Generation didn't complete after 15 minutes. Please try again or check Higgsfield manually."

### Phase 6: Extract Share Links

24. For each of the **4 newest images** in the grid (starting from the top-left),
    repeat steps 25-29:

25. Click the **3-dot menu** icon in the top-right corner of the image card:
    ```
    browser_click(ref="<ref for 3-dot menu>")
    ```

26. Take a snapshot to see the dropdown menu:
    ```
    browser_snapshot()
    ```

27. Hover over or click **"Share"** to expand the share sub-menu:
    ```
    browser_click(ref="<ref for Share option>")
    ```

28. Take a snapshot to see the share options:
    ```
    browser_snapshot()
    ```

29. Click **"Copy link"**:
    ```
    browser_click(ref="<ref for Copy link>")
    ```
    After clicking, take a snapshot to capture the link:
    ```
    browser_snapshot()
    ```
    Look for the link in a toast notification, a URL displayed in the share
    dialog, or any visible text containing a Higgsfield URL. Save this as
    `LINK_N` (where N is 1-4).

    If the link is not visible in the text snapshot, use:
    ```
    browser_vision(prompt="What URL or link was just copied or displayed after clicking Copy link?")
    ```

    Close the menu by clicking elsewhere on the page or pressing Escape:
    ```
    browser_press(key="Escape")
    ```

30. After collecting all 4 links, send a single message to Telegram:

    ```
    Your FUFU generations are ready!

    1. {LINK_1}
    2. {LINK_2}
    3. {LINK_3}
    4. {LINK_4}
    ```

## Pitfalls

- **Session expired / Login blocking**: If navigating to the Soul v2 page
  redirects to a login screen at step 4, the browser profile cookies have expired.
  Navigate to `https://higgsfield.ai` to verify: clicking the "Login" link opens
  a modal dialog (not a page redirect).

  **Login button requires two clicks**: On the homepage, the first click on
  "Login" redirects to `/ai/video` instead of opening a login modal. A second
  click on "Login" from that page opens the OAuth modal (Google/Apple/Microsoft
  buttons). If the Login button doesn't seem to work on the first attempt,
  click it again. The Google/Apple/Microsoft OAuth buttons
  do NOT work in the headless browser session — the browser cannot open OAuth
  popups or redirect flows. Additionally, repeated login attempts trigger
  the "Too many requests. Please try again in a bit." rate limit due to bot
  detection (the browser runs without residential proxies).

  **Cookie injection is not possible**: (a) JavaScript `document.cookie` is
  blocked for both read and write (`SecurityError`) on the higgsfield.ai domain,
  and (b) the browser tools don't expose Playwright's native cookie API. The
  `__session` JWT has a ~60-second expiry and requires Clerk's refresh mechanism.
  Session-bound cookies (`__cf_bm`, `datadome`, `clerk_active_context`) are tied
  to the specific browser instance and cannot be transferred.

  If the session is expired and login is blocked, ask the user to log in manually
  on their own browser first, and the browser session must have been started with
  a pre-authenticated browser profile (not a clean session). Without valid cookies
  already in the browser profile, generation cannot proceed. Send a message to
  Telegram and stop.
- **File upload**: The file chooser interaction depends on the browser profile
  having the correct permissions. If the upload fails, try using `browser_vision`
  to see what the upload area looks like and adjust the interaction accordingly.
- **Clipboard vs. visible link**: Hermes browser tools use accessibility trees,
  not the system clipboard. "Copy link" puts the URL in the clipboard, but we
  need to read it from visible page elements (toast, dialog, URL field). If
  nothing is visible, try `browser_console()` to check if the URL was logged.
- **Rate limits**: Higgsfield may throttle generation requests. If the Generate
  button produces an error about rate limits or credits, report to the user.
- **3-dot menu positioning**: The 3-dot menu is in the top-right corner of each
  image card. If the grid layout changes, the ref IDs will be different. Always
  use `browser_snapshot()` to find the correct ref before clicking.

## Verification

After sending the 4 links to Telegram, the skill is complete. The user can click
each link to verify the generated images on Higgsfield.
