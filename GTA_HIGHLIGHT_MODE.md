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

## Enable per upload

Open **Advanced options** in the dashboard and tick **GTA Highlight Mode** only for a GTA gameplay upload. The option is off by default and is sent with that individual process request.

The API forwards the choice to that job's pipeline subprocess. Other uploads explicitly receive `GTA_HIGHLIGHT_MODE=0`, even if the backend container has a different deployment-wide value. The selected mode is also written to the job's resume manifest, so an interrupted GTA job resumes with the same setting; older manifests default to normal mode.

The existing Gemini-key flow is unchanged: the dashboard sends the key in the request header, and the backend forwards it only to the processing subprocess. Do not put API keys in this file or commit them.

Optional tuning variables remain deployment-level settings:

- `GTA_CANDIDATE_TOP_K=8`
- `GTA_CANDIDATE_THRESHOLD=0.28`
- `GTA_MIN_REVIEW_SCORE=72`
- `GTA_MAX_CLIPS=2`

## Tests

Run inside the existing backend container:

```powershell
docker exec openshorts-backend python -m pytest -q tests/test_gta_highlight.py tests/test_gta_highlight_gemini.py
```

Then process one GTA sample and manually inspect the selected moments before relying on the output. A high activity score can still be a false positive; the visual review threshold is intentionally strict.

## Follow-up improvement

A per-job GTA toggle in the dashboard/API would be safer than a backend-wide environment variable. This branch intentionally keeps the first integration small and does not turn GTA mode on by default.
