# Higgsfield Cloudflare Web App - Codex Planning Prompt

```text
Plan a web-first app around the existing `scripts/higgsfield_api.py` flow. The product should let users generate clone-style images from inspiration images using Higgsfield as the temporary backend. Keep the stack Cloudflare-native: Workers for app/API, Queues for async job throttling, D1 for app data, and R2 for media; only use Workflows if you think durable multi-step orchestration is needed. Use Better Auth for login/signup and Polar.sh for payments. Design it so Higgsfield can later be swapped for an in-house Soul-v2-style image/video system, and leave room for a future short-video generation pipeline similar to the image flow. Research the repo and current docs, then produce an MVP architecture and build plan.
```
