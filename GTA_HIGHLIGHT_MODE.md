# GTA Highlight Mode

This adds an opt-in GTA gameplay selection path while leaving the standard OpenShorts selection path unchanged by default.

## How it works

1. The local detector ranks candidate windows using audio energy, motion, scene changes and sudden audio peaks.
2. Gemini reviews a low-resolution montage of those candidate windows and identifies visible GTA-specific moments (police chases, crashes, explosions, stunts, funny fails, NPC reactions, etc.).
3. Weak or overlapping moments are rejected. The mode returns up to two clips and may return zero when no candidate meets the quality threshold.

The detector only proposes candidates; Gemini is the semantic verifier. Activity alone is not treated as proof of a highlight.

## Files added

- `gta_highlight.py`
- `gta_highlight_gemini.py`
- `tests/test_gta_highlight.py`
- `tests/test_gta_highlight_gemini.py`

## Enable carefully

The current switch is a **backend-wide environment variable**, not a per-upload UI setting. When `GTA_HIGHLIGHT_MODE=1`, every job processed by that backend instance will use GTA selection. Do not leave it enabled while processing ordinary talking-head, podcast, or other non-GTA videos.

Set these variables in the backend container environment only for a GTA-only test window:

- `GTA_HIGHLIGHT_MODE=1`
- `GTA_CANDIDATE_TOP_K=8`
- `GTA_CANDIDATE_THRESHOLD=0.28`
- `GTA_MIN_REVIEW_SCORE=72`
- `GTA_MAX_CLIPS=2`

Remove or set `GTA_HIGHLIGHT_MODE=0` before returning to normal videos. Recreate/restart the backend after changing container environment variables. The app's existing Gemini-key forwarding should continue to populate `GEMINI_API_KEY` for the worker process; do not put API keys in this file or commit them.

## Tests

Run inside the existing backend container:

```powershell
docker exec openshorts-backend python -m pytest -q tests/test_gta_highlight.py tests/test_gta_highlight_gemini.py
```

Then process one GTA sample and manually inspect the selected moments before relying on the output. A high activity score can still be a false positive; the visual review threshold is intentionally strict.

## Follow-up improvement

A per-job GTA toggle in the dashboard/API would be safer than a backend-wide environment variable. This branch intentionally keeps the first integration small and does not turn GTA mode on by default.
