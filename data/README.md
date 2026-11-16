# Datasets

`current-patch.json` and `30-days.json` are the public DraftGap v5 datasets:

- <https://bucket.draftgap.com/datasets/v5/current-patch.json>
- <https://bucket.draftgap.com/datasets/v5/30-days.json>

They are downloaded automatically on first use (`--refresh` forces a fresh
copy) and are intentionally gitignored because of their size and because they
are generated data. The files present after the initial setup are the snapshots
observed on 2026-11-15 (dataset `16.22.1`, 173 champions).

`remote-meta.json` stores the ETag/Last-Modified values used by the server's
conditional refresh; it is generated and gitignored too. The service checks the
upstream metadata every 300 seconds by default and hot-swaps the model when a
dataset changes.

Downloaded data is treated as untrusted input: it is parsed as JSON only.
