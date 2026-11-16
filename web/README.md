# Web assets

This directory contains the local 1:1 DraftGap page.

- `assets/app.css` is the compiled stylesheet served by draftgap.com on
  2026-11-16, kept byte-for-byte so spacing, colors, responsive rules, and
  focus states match the original.
- `assets/ui.css` is an additive layer for local UI work: native `<dialog>`
  styling, focus-visible rings, forced-colors fallbacks, and the Quick JSON
  result cards, bars, and tables. `app.css` stays byte-for-byte identical.
- `assets/app.js` is an independent vanilla-JS implementation written for this
  project. It consumes `/api/bootstrap`, `POST /predict`, and the read-only
  `/api/market/*` endpoints; it does not contain DraftGap's application bundle.
- `fonts/` and `assets/favicon.ico` are the original site assets required by
  the stylesheet.
- `index.html` reconstructs the original desktop shell and adds the Quick JSON
  and Market dialogs as explicit local extensions. Neither button is part of
  the upstream page.

The Quick JSON dialog and settings use native modal `<dialog>` semantics:
`Esc`, backdrop light dismiss, focus return, and page scroll containment come
from the platform. The dialog validates drafts before calling `/predict`,
announces errors and results through polite live regions, remembers the last
input locally, and supports `⌘`/`Ctrl` + `Enter` to predict. Results show four
winrate components per team with deviation bars and per-champion contribution
tables, and can be copied as JSON or loaded into the board.

The Market dialog lists LoL matches from the local service, expands the games
that were actually played, renders both lineups with source and coverage
labels, and POSTs the selected side to `/predict` before switching to Draft
Analysis. The page shows no upstream brand name or external source links.

The page talks only to the local Python service. Champion portraits are loaded
from DDragon; no DraftGap API, account, or private endpoint is used.

Upstream data refreshes daily. `POST /predict` is the source of truth for the
suggested-pick table: it mirrors DraftGap's `minGames` filter and returns the
team winrate after each candidate pick, so the page does not recompute model
math in JavaScript.
