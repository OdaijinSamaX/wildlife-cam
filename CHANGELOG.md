# Changelog

## v0.0.2 - 2026-05-20

- Added Cloudflare Worker, R2, Supabase, and Vite + React based MVP architecture for cloud upload, listing, and playback.
- Added `public.traps` based armed control so the Raspberry Pi stays powered on and only detects, records, and uploads while armed.
- Added Worker endpoints for trap polling, trap listing, and trap armed updates, including disarmed upload rejection.
- Added Web UI trap control panel with admin-only armed toggle and Worker-backed trap state loading.
- Updated Pi runtime to poll trap arm state, skip motion detection while disarmed, and log when armed monitoring resumes.
- Documented production deployment flow, Pi operational caveats, Pages URL handling, and troubleshooting findings from end-to-end testing.
