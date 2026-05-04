# Higgsfield Cloudflare Web App - Ruflo Setup Prompt

```text
Set up the initial SaaS repo for `mirai-clone`, a web-first app branded as Mirai, based on the existing `scripts/higgsfield_api.py` flow. The product should let users create and manage multiple clone profiles, where each clone has its own identity, reference assets, and generation history. Users should be able to generate clone-style images using Higgsfield as the temporary backend.

The app should include a discovery page powered by the ScrapeCreator API that shows trending images users can browse and choose as inspiration for a selected clone. Users should also be able to upload their own inspiration images. The core MVP should cover auth, clone management, discovery, generation submission, job status/history, and account/billing flows.

Use a Cloudflare-native stack: Workers for app/API, Queues for async job throttling, D1 for app data, and R2 for media storage; only add Workflows if durable multi-step orchestration is clearly needed. Use Better Auth for login/signup and Polar.sh for payments.

Architect the system so Mirai is the app brand and clone profiles are the primary user-owned entity. Design the generation layer so Higgsfield can later be replaced by an in-house Soul-v2-style image/video system, and leave room for a future short-video pipeline similar to the image flow.

Research the repo and current docs, then create the initial repo structure, core app scaffold, config/bindings, data model, discovery-feed ingestion/caching strategy, auth/payment integration points, queue/job pipeline shape, provider abstraction, key page/route structure, and an MVP implementation plan.
```
