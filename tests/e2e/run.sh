#!/usr/bin/env bash
# Deterministic browser E2E for the market lineup flow.
#
# The local server is real, including POST /predict. Only the three market
# endpoints are mocked with captured fixtures, so the test does not depend on
# upstream availability or on a particular match still being listed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACTS="$ROOT/tests/e2e/artifacts"
DATA_DIR="${DRAFTGAP_DATA_DIR:-$ROOT/data}"
SESSION="draftgap-e2e-$$"
SERVER_PID=""
BASE_URL=""
DOCS_DIR="${E2E_DOCS_DIR:-}"
if [[ "${E2E_DOCS:-0}" == "1" && -z "$DOCS_DIR" ]]; then
  DOCS_DIR="$ROOT/docs/images"
fi
if [[ -n "$DOCS_DIR" ]]; then
  mkdir -p "$DOCS_DIR"
fi

mkdir -p "$ARTIFACTS"

cleanup() {
  agent-browser --session "$SESSION" close >/dev/null 2>&1 || true
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

ab() {
  agent-browser --session "$SESSION" "$@"
}

step() {
  printf '\n== %s ==\n' "$1"
}

page_assert() {
  local name="$1"
  if ! ab eval --stdin >/dev/null; then
    echo "FAIL: $name" >&2
    exit 1
  fi
  echo "ok - $name"
}

wait_for_visuals() {
  # Champion icons use <img loading="lazy"> and the side cards use CSS
  # background splashes, so wait for both before taking a screenshot.
  ab eval --stdin >/dev/null <<'JS'
(() => {
  window.__visualsReady = false;
  (async () => {
    for (const img of document.images) {
      if (!img.complete) {
        img.loading = 'eager';
        const src = img.src;
        img.src = '';
        img.src = src;
      }
    }
    await document.fonts.ready;
    const urls = new Set();
    for (const el of document.querySelectorAll('*')) {
      const bg = getComputedStyle(el).backgroundImage;
      for (const match of bg.matchAll(/url\(["']?(.*?)["']?\)/g)) {
        if (match[1] && !match[1].startsWith('data:')) urls.add(match[1]);
      }
    }
    await Promise.all([...urls].map((url) => new Promise((resolve) => {
      const image = new Image();
      image.onload = resolve;
      image.onerror = resolve;
      image.src = url;
    })));
    await Promise.all([...document.images].map((img) => img.decode?.().catch(() => {})));
    window.__visualsReady = [...document.images].every((img) => img.complete);
  })();
  return true;
})()
JS
  ab wait --fn 'window.__visualsReady === true && document.fonts.status === "loaded"' --timeout 30000 >/dev/null
  ab wait 300 >/dev/null
}

if grep -RIn -i 'polymarket' "$ROOT/web" >/dev/null 2>&1; then
  echo "The page must use only 'market' wording." >&2
  grep -RIn -i 'polymarket' "$ROOT/web" >&2
  exit 1
fi
if ! command -v agent-browser >/dev/null 2>&1; then
  echo "agent-browser is required. Run: npm install && npx agent-browser install" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi
for required in current-patch.json 30-days.json; do
  if [[ ! -f "$DATA_DIR/$required" ]]; then
    echo "Missing $DATA_DIR/$required." >&2
    echo "Run: python3 draftgap_model.py --download" >&2
    exit 1
  fi
done

PORT="$(
  python3 -I - <<'PY'
import socket

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(sock.getsockname()[1])
sock.close()
PY
)"
BASE_URL="http://127.0.0.1:$PORT"
SERVER_LOG="$ARTIFACTS/server.log"

step "Start local DraftGap server on $BASE_URL"
python3 -I "$ROOT/draftgap_model.py" \
  --serve \
  --port "$PORT" \
  --data-dir "$DATA_DIR" \
  --no-auto-refresh >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

ready=0
for _ in $(seq 1 120); do
  if curl -fsS --noproxy '*' "$BASE_URL/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    echo "Server exited before becoming ready:" >&2
    cat "$SERVER_LOG" >&2
    exit 1
  fi
  sleep 0.25
done
if [[ "$ready" != "1" ]]; then
  echo "Server did not become ready:" >&2
  cat "$SERVER_LOG" >&2
  exit 1
fi

step "Launch browser and mock market endpoints"
ab close >/dev/null 2>&1 || true
ab open >/dev/null
ab set viewport 1440 1000 >/dev/null
ab network route '**/api/market/matches*' --body "$(cat "$ROOT/tests/e2e/fixtures/matches.json")" >/dev/null
ab network route '**/api/market/match?slug=*' --body "$(cat "$ROOT/tests/e2e/fixtures/match.json")" >/dev/null
ab network route '**/api/market/lineup?slug=*&game=3*' --body "$(cat "$ROOT/tests/e2e/fixtures/lineup-3.json")" >/dev/null
ab network route '**/api/market/lineup?slug=*&game=1*' --body "$(cat "$ROOT/tests/e2e/fixtures/lineup-1.json")" >/dev/null
ab navigate "$BASE_URL/" >/dev/null

step "Open the market dialog and inspect the match list"
ab wait '#market-open' --timeout 15000 >/dev/null
if [[ -n "$DOCS_DIR" ]]; then
  ab wait --fn 'document.querySelectorAll("#draft-table tr[data-champion-key]").length > 10' --timeout 20000 >/dev/null
  wait_for_visuals
  ab screenshot "$DOCS_DIR/01-draft-board.png" >/dev/null
fi
ab click '#market-open' >/dev/null
ab wait '#market-dialog[open]' --timeout 10000 >/dev/null
ab wait '[data-pm-match]' --timeout 15000 >/dev/null
page_assert "page markup uses only market wording" <<'JS'
(() => {
  const markup = document.documentElement.innerHTML.toLowerCase();
  if (markup.includes('polymarket')) throw new Error('page markup contains a forbidden source name');
  return 'wording-ok';
})()
JS
page_assert "match list shows Top Esports vs Bilibili Gaming" <<'JS'
(() => {
  const matches = [...document.querySelectorAll('[data-pm-match]')];
  if (matches.length !== 1) throw new Error(`expected 1 match, got ${matches.length}`);
  if (!matches[0].innerText.includes('Top Esports vs Bilibili Gaming')) {
    throw new Error(`unexpected match: ${matches[0].innerText}`);
  }
  return matches.length;
})()
JS

step "Inspect the game list"
ab wait '[data-pm-game]' --timeout 15000 >/dev/null
page_assert "three played games are listed" <<'JS'
(() => {
  const games = [...document.querySelectorAll('[data-pm-game]')];
  if (games.length !== 3) throw new Error(`expected 3 games, got ${games.length}`);
  const labels = games.map((game) => game.innerText);
  if (!labels[2].includes('Game 3')) throw new Error(`unexpected last game: ${labels[2]}`);
  return labels.length;
})()
JS

step "Inspect the default Game 3 lineup"
ab wait '#pm-lineup .pm-pick-name' --timeout 15000 >/dev/null
page_assert "Game 3 lineup, source, and picks" <<'JS'
(() => {
  const selected = document.querySelector('[data-pm-game][aria-pressed="true"]');
  if (!selected?.innerText.includes('Game 3')) throw new Error('Game 3 was not selected');
  const picks = [...document.querySelectorAll('#pm-lineup .pm-pick-name')].map((el) => el.innerText.trim());
  const expected = ['Renekton', 'Pantheon', 'Syndra', 'Tristana', 'Lulu', 'Ambessa', 'Maokai', 'Yone', 'Kalista', 'Renata Glasc'];
  if (picks.length !== expected.length) throw new Error(`expected 10 picks, got ${picks.length}`);
  for (let i = 0; i < expected.length; i += 1) {
    if (picks[i] !== expected[i]) throw new Error(`pick ${i}: expected ${expected[i]}, got ${picks[i]}`);
  }
  const source = document.querySelector('#pm-lineup .pm-source')?.innerText || '';
  if (!source.includes('LEAGUEPEDIA')) throw new Error(`unexpected source: ${source}`);
  return picks.length;
})()
JS
if [[ -n "$DOCS_DIR" ]]; then
  wait_for_visuals
  page_assert "all visible champion images are loaded" <<'JS'
(() => {
  const broken = [...document.images]
    .filter((img) => {
      const rect = img.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < window.innerHeight;
    })
    .filter((img) => !img.complete || img.naturalWidth === 0)
    .map((img) => img.src);
  if (broken.length) throw new Error(`unloaded images: ${broken.join(', ')}`);
  return document.images.length;
})()
JS
  ab screenshot '#market-dialog' "$DOCS_DIR/02-market-lineup.png" >/dev/null
fi

step "Switch to Game 1"
ab click '[data-pm-game="1"]' >/dev/null
ab wait '[data-pm-game="1"][aria-pressed="true"]' --timeout 5000 >/dev/null
ab wait --text 'Jayce' --timeout 15000 >/dev/null
page_assert "Game 1 lineup replaces Game 3" <<'JS'
(() => {
  const picks = [...document.querySelectorAll('#pm-lineup .pm-pick-name')].map((el) => el.innerText.trim());
  if (picks[0] !== 'Jayce') throw new Error(`unexpected first pick: ${picks[0]}`);
  if (!picks.includes('Gnar') || !picks.includes('Nautilus')) {
    throw new Error(`missing expected Game 1 picks: ${picks.join(', ')}`);
  }
  return picks.length;
})()
JS

step "Return to Game 3 and load the winning Top Esports lineup"
ab click '[data-pm-game="3"]' >/dev/null
ab wait '[data-pm-game="3"][aria-pressed="true"]' --timeout 5000 >/dev/null
ab wait --text 'Renekton' --timeout 15000 >/dev/null
ab click '[data-pm-ally="home"]' >/dev/null
ab click '#pm-load' >/dev/null
ab wait '#market-dialog:not([open])' --timeout 20000 >/dev/null
ab wait '#tab-analysis:not([hidden])' --timeout 20000 >/dev/null
ab wait --text 'DRAFT ANALYSIS' --timeout 20000 >/dev/null
page_assert "analysis matches the winning Game 3 lineup" <<'JS'
(() => {
  const text = document.body.innerText;
  for (const expected of ['DRAFT ANALYSIS', 'RENEKTON', 'PANTHEON', 'SYNDRA', 'TRISTANA', 'LULU', 'AMBESSA', 'KALISTA']) {
    if (!text.includes(expected)) throw new Error(`missing analysis text: ${expected}`);
  }
  if (!/WINRATE\s+57\.79/.test(text)) throw new Error('expected the 57.79% winner-side winrate');
  return 'analysis-ok';
})()
JS
if [[ -n "$DOCS_DIR" ]]; then
  ab set viewport 1440 1500 >/dev/null
  wait_for_visuals
  page_assert "all visible champion images are loaded" <<'JS'
(() => {
  const broken = [...document.images]
    .filter((img) => {
      const rect = img.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < window.innerHeight;
    })
    .filter((img) => !img.complete || img.naturalWidth === 0)
    .map((img) => img.src);
  if (broken.length) throw new Error(`unloaded images: ${broken.join(', ')}`);
  return document.images.length;
})()
JS
  ab screenshot "$DOCS_DIR/03-analysis.png" >/dev/null
fi

step "Check browser errors"
ERRORS="$(ab errors)"
if [[ -n "$ERRORS" ]]; then
  echo "Browser errors:" >&2
  echo "$ERRORS" >&2
  exit 1
fi
echo "ok - no page errors"

if [[ "${E2E_SCREENSHOT:-0}" == "1" ]]; then
  ab screenshot --full "$ARTIFACTS/final.png" >/dev/null
  echo "Screenshot: $ARTIFACTS/final.png"
fi

printf '\nE2E passed: market list -> games -> lineups -> DraftGap analysis\n'
