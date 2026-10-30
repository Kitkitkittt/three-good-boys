# Incident: competition compiler published in a public Git history

**Severity:** P1 — restricted material exposed in a public repository.
**Status:** partially remediated. Fork ref removed; GitHub-side purge still required.

## What happened

`services/grounding/compiler.py` and its test/smoke files were committed as `fc8a9ee` and pushed to the public fork `Kitkitkittt/three-good-boys`. The module mirrored the organizer's `zaic_tools.validate.schema_error` rules. `AGENTS.md:23`, `README.md:31` and `context/README.md:51` prohibit competition code in a public repository.

## Remediation so far

- All local history was rewritten (`git filter-branch --index-filter`, every local ref) to drop `services/grounding/` and `services/test_grounding.py` from every commit. The local object store no longer contains the exposed blobs.
- `main` and `origin/main` were not rewritten: `origin` does not contain the file, and the rewritten `main` object was reverted to the true remote commit `fcbe62b`.
- The rewritten feature branch was pushed to the fork. Cloud Run does not host the fork, so the fork's own refs are no longer a delivery path for them.
- The fork branch `feat/lifemate-implementation` was **deleted**, so no ref on the fork references the exposed commit.
- Unaffected local branches (`ticket/*`, `feat/lifemate-evaluation`) were audited: none contain the file.

## Still open (needs GitHub support / owner)

The public parent repository `huyxdang/three-good-boys` still returns the blob at the `fc8a9ee` path (verified in this session). Its `pushed_at` is unchanged, so the content is reachable through GitHub's retained object/cache layer rather than a visible branch. Deleting refs is not sufficient: GitHub keeps unreferenced objects reachable at known SHAs until storage and caches are purged.

1. Contact GitHub support with the repository, path and SHA `fc8a9ee`, requesting removal of the retained commit/blob and the raw/CDN cache entries for it.
2. Ask all collaborators to re-clone after the purge and to delete any local clones that still hold the old history.
3. Confirm with parties who may have copied the content that it has been discarded.
4. Until the purge is confirmed, ticket 24 must remain `blocked` and no claim of privacy may be made.

## Evidence

- Exposure commit: `fc8a9ee`
- Forward removal commit: `b2103c6` (never sufficient on its own)
- Rewritten local tip: `aa2333b` (same tree as `f8c3e17`, rewritten parent chain)
- Post-rewrite local check: `git cat-file -e fc8a9ee` → object gone; nothing references the old history
- Post-delete remote check: fork branch lookup 404; parent raw path still HTTP 200

No credential was involved; nothing to rotate.