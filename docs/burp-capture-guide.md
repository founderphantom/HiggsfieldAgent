# Burp Suite Pro — Higgsfield API Capture Guide

Follow these steps to capture Higgsfield's HTTP traffic for Phase 1 of the API rewrite plan.
The output of this session is shared with Copilot to build `scripts/higgsfield_api.py`.

---

## Step 1 — Launch Burp and create a project

1. Open **Burp Suite Professional**
2. Select **New project on disk** → name it `higgsfield` → choose a save location → **Next**
3. Select **Use Burp defaults** → **Start Burp**

---

## Step 2 — Confirm the proxy listener

1. Go to **Proxy** tab → **Proxy settings** (top right)
2. Under **Proxy listeners**, confirm `127.0.0.1:8080` is listed and **Running**
3. If not running, check the checkbox to enable it

---

## Step 2.5 — Install burp-awesome-tls (required for Higgsfield)

Higgsfield uses Cloudflare Bot Management and DataDome, both of which detect Burp's Java TLS
fingerprint and return 429/403 errors. This extension replaces Burp's TLS stack with a real
browser fingerprint.

1. Download the latest `*-fat.jar` from the releases page of **sleeyax/burp-awesome-tls** on GitHub
2. In Burp → **Extensions** → **Add**
3. Set extension type to **Java** → select the downloaded `.jar` → **Next**
4. A new **"Awesome TLS"** tab appears in Burp
5. In that tab, set the fingerprint to **`firefox_147`**
6. Leave all other settings at their defaults

---

## Step 3 — Install Burp's CA certificate into Firefox

Required to see HTTPS traffic. Do this once.

1. Open Firefox (no proxy configured yet)
2. Navigate to `http://127.0.0.1:8080` while Burp is running
3. Click **CA Certificate** (top right) → saves `cacert.der`
4. In Firefox → **Settings** → **Privacy & Security** → scroll down to Certificates → **View Certificates**
5. Click the **Authorities** tab → **Import**
6. Select the downloaded `cacert.der`
7. Check ✅ **Trust this certificate to identify websites** → OK
8. Restart Firefox completely (close all windows, reopen)

---

## Step 4 — Configure Firefox to use the Burp proxy

Firefox has built-in proxy settings — no command-line launch needed.

1. In Firefox → **Settings** → search **"proxy"** → click **Settings…** under Network Settings
2. Select **Manual proxy configuration**
3. HTTP Proxy: `127.0.0.1` Port: `8080`
4. Check ✅ **Also use this proxy for HTTPS**
5. Click **OK**

All Firefox traffic now routes through Burp.

---

## Step 5 — Verify the proxy is working

1. In Burp → **Proxy → HTTP history**
2. In Firefox, navigate to `https://example.com`
3. You should see full request/response entries (not just CONNECT tunnels)

If you only see CONNECT entries: the CA cert was not installed correctly — redo Step 3.

---

## Step 6 — Turn Intercept OFF

1. Burp → **Proxy → Intercept** sub-tab
2. If the button says **"Intercept is on"** → click it → should now read **"Intercept is off"**

If intercept is left ON, every request will pause and wait for manual forwarding — the session will be unusable.

---

## Step 7 — Log in to Higgsfield

Higgsfield uses Clerk for authentication with a two-stage login flow.

1. In the proxied Firefox, go to `https://higgsfield.ai`
2. Enter your **email** and **password** → submit
3. Clerk will send a **verification code** to your email — check your inbox
4. Enter the verification code in the browser when prompted
5. Confirm you are logged in and on the Higgsfield dashboard
6. Confirm both the sign-in request and the verification code request appear in Burp's HTTP history

---

## Step 8 — Do the full manual generation

Do each step deliberately to ensure every API call is captured:

1. Navigate to `https://higgsfield.ai/mobile/image/soul-v2`
2. Click the **Image Reference** tab
3. Click the **character selector** → wait for the grid to load → click **Soul 2.0** → select **Fufu**
4. Upload an image
5. Select an **aspect ratio**
6. Set **Batch Size: 4**
7. Set **Quality: 2K**
8. Click **Generate**
9. Wait the full ~8 minutes for generation to complete — do not navigate away
10. Navigate to `https://higgsfield.ai/asset/image`
11. Open the share menu on each of the 4 generated images → click **Copy link**

---

## Step 9 — Export captured traffic

1. Burp → **Proxy → HTTP history**
2. In the Filter bar, type `higgsfield` to narrow results to Higgsfield requests only
3. Click any row → Ctrl+A to select all
4. Right-click → **Save selected items** → save as `higgsfield-capture.xml`

---

## Step 10 — Copy key requests as cURL (optional but helpful)

For the ~8 most important requests (login, verification code, upload, generate, poll, assets, share link):

1. Click the request in HTTP history
2. In the Request panel → right-click → **Copy as curl command**
3. Paste into a text file

---

## Step 11 — Redact secrets before sharing

Open the XML or cURL output and replace the following before sending to anyone:

| Field | Replace value with |
|---|---|
| `Authorization: Bearer eyJ...` | `Authorization: Bearer <REDACTED_JWT>` |
| `Cookie: session=...` | `Cookie: <REDACTED_COOKIES>` |
| Your email address | `user@example.com` |
| S3 signature params | `X-Amz-Signature=<REDACTED>` |

After redacting, **log out of Higgsfield and log back in** to invalidate the captured session.

---

## Step 12 — Share with Copilot

Paste the redacted cURL commands (or the XML) into the Copilot chat.
Copilot will produce the endpoint map (Task 2) and write `scripts/higgsfield_api.py`.

---

## Burp Pro tips

- Use **Logger** tab for richer per-request detail including timing
- Use **Ctrl+F** in HTTP history to search request bodies for keywords like `generate` or `upload`
- Use **Target → Scope** to filter HTTP history to `https://higgsfield.ai` only and reduce noise
