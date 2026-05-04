# Higgsfield Cloudflare Web App - Ruflo Setup Prompt

```text
Set up the initial SaaS repo for a web-first app based on the existing `scripts/higgsfield_api.py` flow. The app should let users upload inspiration images and generate clone-style images using Higgsfield as a temporary backend. Use a Cloudflare-native stack: Workers for app/API, Queues for async job throttling, D1 for app data, R2 for media storage, and only add Workflows if durable multi-step orchestration is clearly needed. Use Better Auth for login/signup and Polar.sh for payments. Architect the generation layer so Higgsfield can later be replaced by an in-house Soul-v2-style image/video system, and leave room for a future short-video pipeline. Research the repo and current docs, then create the initial repo structure, core app scaffold, config/bindings, data model, job pipeline shape, and an MVP implementation plan.
```
