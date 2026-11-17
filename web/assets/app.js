/* DraftGap-compatible draft board, backed by the local Python model. */
'use strict';

const ROLES = [0, 1, 2, 3, 4];
const ROLE_NAMES = ['Top', 'Jungle', 'Middle', 'Bottom', 'Support'];
const ROLE_NAMES_ZH = ['上单', '打野', '中单', '下路', '辅助'];
const ROLE_ALIASES = {
  '0': 0, top: 0, toplane: 0, 'top lane': 0, '上单': 0, '上路': 0,
  '1': 1, jungle: 1, jg: 1, jungler: 1, '打野': 1,
  '2': 2, middle: 2, mid: 2, midlane: 2, 'mid lane': 2, '中单': 2, '中路': 2,
  '3': 3, bottom: 3, bot: 3, adc: 3, 'bot lane': 3, '下路': 3, '射手': 3,
  '4': 4, support: 4, sup: 4, utility: 4, '辅助': 4, '辅助位': 4,
};

const ROLE_SVG = {
  0: '<g fill="currentColor" fill-rule="evenodd" transform="rotate(-180 13.25 13.25)"><polygon points="22.063 3 22.063 21.969 3 21.969 7.053 17.936 18.063 17.969 17.999 7.044"></polygon><polygon fill-opacity=".3" points="0 0 14.593 0 19.109 0 15.089 4.011 4.002 4 4.002 15.076 0 19.07 0 14.491"></polygon><rect width="6" height="6" x="8" y="8" fill-opacity=".3"></rect></g>',
  1: '<g fill="currentColor" fill-rule="evenodd" transform="translate(4 3)"><path d="M11.5565033 25.2593129L3.71050008 17.007843C3.53174845 13.6218567 2.29491509 10.7161679 0 8.29077657 3.7954305 10.8023461 6.10286289 13.0322181 6.92229716 14.9803925 6.50825161 8.81697083 5.33232795 3.82350667 3.39452616 0 8.87327915 7.71470812 11.7037862 13.5908949 11.8860474 17.6285604 12.0683085 21.6662259 11.9584605 24.20981 11.5565033 25.2593129zM14.653773 21.2846629C14.9109039 14.93976 17.4729716 10.187166 22.339976 7.0268809 19.9557631 10.6189931 18.8951467 14.045261 19.1581268 17.3056844L14.653773 21.2846629zM13.429067 14.4254201L12.0960337 8.97735596C13.4903276 6.05259874 15.7644196 3.11883375 18.9183095.176060994 16.7638533 4.16490512 15.401769 7.34258185 14.8320567 9.70909119 14.2623444 12.0756005 13.7946811 13.6477102 13.429067 14.4254201z"></path></g>',
  2: '<g fill="currentColor" fill-rule="evenodd" transform="translate(4.5 4.5)"><polygon fill-opacity=".3" points="0 0 14.519 0 10.484 4 3.997 4 3.997 10.523 0 14.491"></polygon><polygon fill-opacity=".3" points="7.5 7.5 22.019 7.5 17.984 11.5 11.497 11.5 11.497 18.023 7.5 21.991" transform="rotate(-180 14.76 14.746)"></polygon><polygon points="18 0 22 0 22 4 4 22 0 22 0 18"></polygon></g>',
  3: '<g fill="currentColor" fill-rule="evenodd" transform="translate(4.5 4.5)"><polygon points="22.063 3 22.063 21.969 3 21.969 7.053 17.936 18.063 17.969 17.999 7.044"></polygon><polygon fill-opacity=".3" points="0 0 14.593 0 19.109 0 15.089 4.011 4.002 4 4.002 15.076 0 19.07 0 14.491"></polygon><rect width="6" height="6" x="8" y="8" fill-opacity=".3"></rect></g>',
  4: '<g fill="currentColor" fill-rule="evenodd" transform="translate(1.5 4)"><polygon points="14.089 22.953 18.041 19.779 14.089 9.976 10.121 19.779"></polygon><polygon points="8.841 13.988 11.786 8.453 9.102 6 0 6 7.895 9.466 5.868 11.388"></polygon><polygon points="25.341 13.988 28.286 8.453 25.602 6 16.5 6 24.395 9.466 22.368 11.388" transform="matrix(-1 0 0 1 44.786 0)"></polygon><polygon points="13.992 7.007 18.044 2.955 16.04 .951 12.009 .951 10.025 2.934"></polygon></g>',
};

const STAR_SVG = '<path fill-rule="evenodd" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" clip-rule="evenodd"></path>';
const INFO_SVG = '<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd"></path>';
const DOTS_SVG = '<path stroke-linecap="round" stroke-linejoin="round" d="M12 6.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 12.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 18.75a.75.75 0 110-1.5.75.75 0 010 1.5z"></path>';
const LOCK_PATH = '<path fill-rule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clip-rule="evenodd"></path>';
const WARN_PATH = '<path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"></path>';
const LEFT_ARROW = '<path fill-rule="evenodd" d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z" clip-rule="evenodd"></path>';
const RIGHT_ARROW = '<path fill-rule="evenodd" d="M3 10a.75.75 0 01.75-.75h10.638L10.23 5.29a.75.75 0 111.04-1.08l5.5 5.25a.75.75 0 010 1.08l-5.5 5.25a.75.75 0 11-1.04-1.08l4.158-3.96H3.75A.75.75 0 013 10z" clip-rule="evenodd"></path>';

const CARD_ICONS = {
  champions: '<path fill-rule="evenodd" d="M7.5 6a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM3.751 20.105a8.25 8.25 0 0116.498 0 .75.75 0 01-.437.695A18.683 18.683 0 0112 22.5c-2.786 0-5.433-.608-7.812-1.7a.75.75 0 01-.437-.695z" clip-rule="evenodd"></path>',
  matchups: '<path fill-rule="evenodd" d="M15.97 2.47a.75.75 0 011.06 0l4.5 4.5a.75.75 0 010 1.06l-4.5 4.5a.75.75 0 11-1.06-1.06l3.22-3.22H7.5a.75.75 0 010-1.5h11.69l-3.22-3.22a.75.75 0 010-1.06zm-7.94 9a.75.75 0 010 1.06l-3.22 3.22H16.5a.75.75 0 010 1.5H4.81l3.22 3.22a.75.75 0 11-1.06 1.06l-4.5-4.5a.75.75 0 010-1.06l4.5-4.5a.75.75 0 011.06 0z" clip-rule="evenodd"></path>',
  duos: '<path d="M4.5 6.375a4.125 4.125 0 118.25 0 4.125 4.125 0 01-8.25 0zM14.25 8.625a3.375 3.375 0 116.75 0 3.375 3.375 0 01-6.75 0zM1.5 19.125a7.125 7.125 0 0114.25 0v.003l-.001.119a.75.75 0 01-.363.63 13.067 13.067 0 01-6.761 1.873c-2.472 0-4.786-.684-6.76-1.873a.75.75 0 01-.364-.63l-.001-.122zM17.25 19.128l-.001.144a2.25 2.25 0 01-.233.96 10.088 10.088 0 005.06-1.01.75.75 0 00.42-.643 4.875 4.875 0 00-6.957-4.611 8.586 8.586 0 011.71 5.157v.003z"></path>',
  winrate: '<path fill-rule="evenodd" d="M2.25 2.25a.75.75 0 000 1.5H3v10.5a3 3 0 003 3h1.21l-1.172 3.513a.75.75 0 001.424.474l.329-.987h8.418l.33.987a.75.75 0 001.422-.474l-1.17-3.513H18a3 3 0 003-3V3.75h.75a.75.75 0 000-1.5H2.25zm6.54 15h6.42l.5 1.5H8.29l.5-1.5zm8.085-8.995a.75.75 0 10-.75-1.299 12.81 12.81 0 00-3.558 3.05L11.03 8.47a.75.75 0 00-1.06 0l-3 3a.75.75 0 101.06 1.06l2.47-2.47 1.617 1.618a.75.75 0 001.146-.102 11.312 11.312 0 013.612-3.321z" clip-rule="evenodd"></path>',
};

const SAMPLE = {
  allies: [
    { champion: 'Maokai', role: 'top' },
    { champion: 'Viego', role: 'jungle' },
    { champion: 'Karthus', role: 'middle' },
    { champion: 'Kalista', role: 'bottom' },
    { champion: 'Thresh', role: 'support' },
  ],
  opponents: [
    { champion: 'Camille', role: 'top' },
    { champion: 'Lee Sin', role: 'jungle' },
    { champion: 'Seraphine', role: 'middle' },
    { champion: "Kai'Sa", role: 'bottom' },
    { champion: 'Soraka', role: 'support' },
  ],
};

const state = {
  bootstrap: null,
  byKey: new Map(),
  aliases: new Map(),
  allies: [null, null, null, null, null],
  opponents: [null, null, null, null, null],
  activeSide: 'allies',
  activePick: 0,
  activePickBySide: { allies: 0, opponents: 0 },
  sideToggle: 'allies',
  tab: 'draft',
  roleFilter: null,
  search: '',
  favorites: new Set(),
  favoritesOnly: false,
  config: {
    riskLevel: localStorage.getItem('draftgap.risk') || 'medium',
    ignoreChampionWinrates: localStorage.getItem('draftgap.ignoreBase') === '1',
    minGames: Number(localStorage.getItem('draftgap.minGames')) || 1000,
  },
  prediction: null,
  suggestions: { allies: [], opponents: [] },
  scoreShown: { allies: 0.5, opponents: 0.5 },
  scoreAnimation: { allies: null, opponents: null },
  matchupMode: 'sameRole',
  language: localStorage.getItem('draftgap.language') || 'en',
  requestId: 0,
  predictionTimer: null,
  datasetDate: null,
  thirtyDayDate: null,
  health: null,
  market: {
    loaded: false,
    loading: false,
    matches: [],
    notes: [],
    listError: null,
    page: 1,
    pageSize: 5,
    pendingPage: null,
    total: null,
    totalPages: null,
    hasPrevious: false,
    hasNext: false,
    pageCache: new Map(),
    selectedSlug: null,
    detail: null,
    detailLoading: false,
    detailError: null,
    selectedGame: null,
    lineup: null,
    lineupLoading: false,
    lineupError: null,
    allySide: 'home',
    actionError: null,
    loadingBoard: false,
    listSeq: 0,
    detailSeq: 0,
    lineupSeq: 0,
  },
};

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));

function roleIcon(role, cls = 'h-8') {
  return `<svg viewBox="0 0 31 31" class="${cls}"><g fill="currentColor" fill-rule="evenodd">${ROLE_SVG[role] || ''}</g></svg>`;
}

function championName(champion) {
  if (!champion) return '';
  if (state.language === 'zh' && champion.nameZh) return champion.nameZh;
  return champion.name;
}

function championIcon(champion, size = 36) {
  if (!champion) return '';
  const scale = size * 1.11;
  const offset = -((scale - size) / 2);
  const version = state.bootstrap?.dataset?.version || '16.22.1';
  return `<div class="relative overflow-hidden rounded-sm" style="width:${size}px;height:${size}px" aria-hidden="true"><img loading="lazy" decoding="async" draggable="false" width="${scale}" height="${scale}" src="https://ddragon.leagueoflegends.com/cdn/${esc(version)}/img/champion/${esc(champion.id)}.png" class="absolute" alt="" style="width:${scale}px;height:${scale}px;max-width:${scale}px;top:${offset}px;left:${offset}px"></div>`;
}

function winrateClass(winrate) {
  if (Number.isNaN(winrate)) return 'text-winrate-okay';
  if (winrate < 0.45) return 'text-winrate-shiggo';
  if (winrate < 0.485) return 'text-winrate-meh';
  if (winrate < 0.515) return 'text-winrate-okay';
  if (winrate < 0.53) return 'text-winrate-good';
  if (winrate < 0.55) return 'text-winrate-great';
  return 'text-winrate-volxd';
}

function scoreText(winrate) {
  return Number.isFinite(winrate) ? (winrate * 100).toFixed(2) : '50.00';
}

function percentText(text) {
  return text == null ? '—' : text;
}

function patchLabel(version) {
  if (!version) return 'PATCH —';
  const parts = String(version).split('.');
  // DraftGap displays Riot's season patch (26.x) from the DDragon major (16.x).
  const major = Number(parts[0]);
  const seasonMajor = Number.isFinite(major) ? major + 10 : parts[0];
  return `PATCH ${seasonMajor}${parts[1] ? `.${parts[1]}` : ''}`;
}

function relativeTime(iso) {
  if (!iso) return 'LAST UPDATED —';
  const then = Date.parse(iso);
  if (!Number.isFinite(then)) return 'LAST UPDATED —';
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 2) return 'LAST UPDATED JUST NOW';
  if (minutes < 60) return `LAST UPDATED ${minutes} MINUTES AGO`;
  const hours = Math.round(minutes / 60);
  if (hours < 36) return `LAST UPDATED ABOUT ${hours} HOUR${hours === 1 ? '' : 'S'} AGO`;
  const days = Math.round(hours / 24);
  return `LAST UPDATED ${days} DAYS AGO`;
}

function toast(message) {
  const node = $('toast');
  node.textContent = message;
  node.classList.remove('hidden');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => node.classList.add('hidden'), 4200);
}

function initToast() {
  const node = $('toast');
  const dismiss = () => {
    clearTimeout(toast._timer);
    node.classList.add('hidden');
  };
  const pause = () => clearTimeout(toast._timer);
  const resume = () => {
    if (node.classList.contains('hidden')) return;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(dismiss, 1800);
  };
  node.addEventListener('click', dismiss);
  node.addEventListener('pointerenter', pause);
  node.addEventListener('pointerleave', resume);
  node.addEventListener('focusin', pause);
  node.addEventListener('focusout', resume);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!response.ok) {
    const error = new Error(data?.error || `HTTP ${response.status}`);
    error.code = data?.code;
    error.hint = data?.hint;
    error.status = response.status;
    throw error;
  }
  return data;
}

function roleFromValue(value) {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 4) return value;
  const text = String(value).trim().toLowerCase();
  if (text in ROLE_ALIASES) return ROLE_ALIASES[text];
  return null;
}

async function loadBootstrap() {
  const data = await api('/api/bootstrap');
  state.bootstrap = data;
  state.datasetDate = data.dataset?.date || null;
  state.thirtyDayDate = data.dataset?.thirtyDayDate || null;
  state.byKey = new Map();
  state.aliases = new Map();
  for (const champion of data.champions || []) {
    champion.roleMap = new Map((champion.roles || []).map((entry) => [entry.role, entry]));
    state.byKey.set(champion.key, champion);
    state.aliases.set(String(champion.key).toLowerCase(), champion.key);
    state.aliases.set(String(champion.id).toLowerCase(), champion.key);
    state.aliases.set(String(champion.name).toLowerCase(), champion.key);
    if (champion.nameZh) state.aliases.set(String(champion.nameZh).toLowerCase(), champion.key);
  }
  renderHeader();
  await predict();
  renderAll();
}

function findChampionByName(value) {
  if (value === null || value === undefined) return null;
  if (state.byKey.has(String(value))) return state.byKey.get(String(value));
  return state.byKey.get(state.aliases.get(String(value).toLowerCase())) || null;
}

function pickedKeys() {
  const keys = new Set();
  for (const pick of [...state.allies, ...state.opponents]) {
    if (pick) keys.add(pick.key);
  }
  return keys;
}

function computeDamage(side) {
  const total = { physical: 0, magic: 0, true: 0 };
  for (const pick of state[side]) {
    if (!pick) continue;
    const champion = state.byKey.get(pick.key);
    const roleEntry = champion?.roleMap?.get(pick.role);
    if (roleEntry?.damage) {
      total.physical += roleEntry.damage.physical || 0;
      total.magic += roleEntry.damage.magic || 0;
      total.true += roleEntry.damage.true || 0;
    }
  }
  return total;
}

function renderHeader() {
  const dataset = state.bootstrap?.dataset;
  $('patch-label').textContent = patchLabel(dataset?.version);
  $('updated-label').textContent = relativeTime(dataset?.date);
  $('updated-label').title = dataset?.date || '';
}

function sidebarHTML(side) {
  const title = side === 'allies' ? 'ALLY' : 'OPPONENT';
  const prediction = state.prediction;
  const winrate = side === 'allies' ? prediction?.prediction?.allyWinrate : prediction?.prediction?.opponentWinrate;
  const shown = state.scoreShown[side] ?? (winrate == null ? 0.5 : winrate);
  const classForScore = winrateClass(shown);
  const picks = state[side];
  const damage = computeDamage(side);
  const damageTotal = damage.physical + damage.magic + damage.true;
  const phys = damageTotal > 0 ? (damage.physical / damageTotal * 100).toFixed(4) : '0';
  const magic = damageTotal > 0 ? (damage.magic / damageTotal * 100).toFixed(4) : '0';
  const trueDamage = damageTotal > 0 ? (damage.true / damageTotal * 100).toFixed(4) : '0';
  const activeSide = state.activeSide === side;
  return `
    <div class="flex h-1 absolute right-0 left-0 top-0 w-full">
      <div class="bg-red-500 transition-all duration-500" style="width:${phys}%"></div>
      <div class="bg-blue-500 transition-all duration-500" style="width:${magic}%"></div>
      <div class="bg-neutral-100 transition-all duration-500" style="width:${trueDamage}%"></div>
    </div>
    <div class="flex-1 flex justify-center items-center bg-[#141414]">
      <span class="text-[2.5rem] text-center leading-tight">${title}<br>
        <span class="sidebar-score ${classForScore} transition-colors duration-500" style="font-variant-numeric:tabular-nums;">${scoreText(shown)}</span>
      </span>
    </div>
    ${picks.map((pick, index) => pickHTML(side, pick, index, activeSide && state.activePickBySide[side] === index)).join('')}
    <div class="absolute right-1 top-0">
      <button type="button" class="pick-menu uppercase inline-flex items-center font-medium rounded-md transition ease-in-out duration-150 hover:bg-white/10 text-xl px-1 py-2" data-side-menu="${side}" title="Team menu" aria-label="${title} team menu" aria-haspopup="menu">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-7" aria-hidden="true">${DOTS_SVG}</svg>
      </button>
    </div>`;
}

function pickHTML(side, pick, index, active) {
  const activeClass = active ? 'bg-neutral-700!' : '';
  if (!pick) {
    return `
      <div class="pick-slot flex-1 relative border-t-2 border-neutral-700 hover:bg-neutral-800 transition-colors duration-150 ease-in-out ${activeClass}" data-side="${side}" data-pick="${index}">
        <span class="absolute top-2 left-2 uppercase text-2xl leading-none">PICK ${index + 1}</span>
        <div class="absolute right-0 top-0">
          <button type="button" class="pick-menu uppercase inline-flex items-center font-medium rounded-md transition ease-in-out duration-150 hover:bg-white/10 text-xl px-1 py-2" data-menu-side="${side}" data-menu-pick="${index}" aria-label="Pick ${index + 1} options" aria-haspopup="menu">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-7" aria-hidden="true">${DOTS_SVG}</svg>
          </button>
        </div>
      </div>`;
  }
  const champion = state.byKey.get(pick.key);
  const splash = `https://ddragon.leagueoflegends.com/cdn/img/champion/centered/${encodeURIComponent(champion?.id || pick.id || pick.key)}_0.jpg`;
  return `
    <div class="pick-slot flex-1 relative border-t-2 border-neutral-700 hover:bg-neutral-800 transition-colors duration-150 ease-in-out ${activeClass}" data-side="${side}" data-pick="${index}">
      <div class="absolute top-0 bottom-0 left-0 h-full w-full" style="background-position:center 20%;background-size:cover;background-image:linear-gradient(rgba(25,25,25,.8) 0%,rgba(0,0,0,0) 50%,rgba(25,25,25,.8) 100%),url(&quot;${esc(splash)}&quot;)"></div>
      <span class="absolute top-2 left-2 uppercase text-2xl leading-none">${esc(championName(champion) || pick.name)}</span>
      <div class="absolute bottom-0 left-0 right-0 flex justify-end overflow-x-auto pt-1 overflow-y-hidden bottom-1">
        <div class="flex flex-col items-center relative group mx-[0.4rem]">
          <div class="text-md">${roleIcon(pick.role, 'h-8 lg:h-10')}</div>
          <svg viewBox="0 0 20 20" fill="currentColor" stroke="none" class="absolute -top-1 -right-1 w-[20px]" style="filter:drop-shadow(rgb(25,25,25) 2px 0 0) drop-shadow(rgb(25,25,25) -2px 0 0) drop-shadow(rgb(25,25,25) 0 2px 0) drop-shadow(rgb(25,25,25) 0 -2px 0)">${LOCK_PATH}</svg>
        </div>
      </div>
      <div class="absolute right-0 top-0">
        <button type="button" class="pick-menu uppercase inline-flex items-center font-medium rounded-md transition ease-in-out duration-150 hover:bg-white/10 text-xl px-1 py-2" data-menu-side="${side}" data-menu-pick="${index}" aria-label="${esc(championName(champion) || pick.name)} pick options" aria-haspopup="menu">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-7" aria-hidden="true">${DOTS_SVG}</svg>
        </button>
      </div>
    </div>`;
}

function sidebarTarget(side) {
  const prediction = state.prediction;
  const winrate = side === 'allies'
    ? prediction?.prediction?.allyWinrate
    : prediction?.prediction?.opponentWinrate;
  return Number.isFinite(winrate) ? winrate : 0.5;
}

function animateSidebarScore(side, target) {
  const container = $(side === 'allies' ? 'ally-sidebar' : 'opponent-sidebar');
  const span = container.querySelector('.sidebar-score');
  if (!span) return;
  const from = state.scoreShown[side] ?? target;
  if (state.scoreAnimation[side]) cancelAnimationFrame(state.scoreAnimation[side]);
  if (Math.abs(from - target) < 0.00001) {
    state.scoreShown[side] = target;
    span.textContent = scoreText(target);
    span.className = `sidebar-score ${winrateClass(target)} transition-colors duration-500`;
    return;
  }
  const duration = 2800;
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    const value = from + (target - from) * eased;
    state.scoreShown[side] = value;
    span.textContent = scoreText(value);
    span.className = `sidebar-score ${winrateClass(value)} transition-colors duration-500`;
    if (t < 1) {
      state.scoreAnimation[side] = requestAnimationFrame(step);
    } else {
      state.scoreAnimation[side] = null;
      state.scoreShown[side] = target;
      span.textContent = scoreText(target);
    }
  };
  state.scoreAnimation[side] = requestAnimationFrame(step);
}

function renderSidebars() {
  for (const side of ['allies', 'opponents']) {
    if (state.scoreAnimation[side]) {
      cancelAnimationFrame(state.scoreAnimation[side]);
      state.scoreAnimation[side] = null;
    }
  }
  $('ally-sidebar').innerHTML = sidebarHTML('allies');
  $('opponent-sidebar').innerHTML = sidebarHTML('opponents');
  $('ally-sidebar').onclick = sidebarClick;
  $('opponent-sidebar').onclick = sidebarClick;
  animateSidebarScore('allies', sidebarTarget('allies'));
  animateSidebarScore('opponents', sidebarTarget('opponents'));
}

function sidebarClick(event) {
  const menuButton = event.target.closest('[data-menu-side]');
  if (menuButton) {
    event.stopPropagation();
    openPickMenu(menuButton.dataset.menuSide, Number(menuButton.dataset.menuPick), menuButton);
    return;
  }
  const sideMenu = event.target.closest('[data-side-menu]');
  if (sideMenu) {
    event.stopPropagation();
    openTeamMenu(sideMenu.dataset.sideMenu, sideMenu);
    return;
  }
  const slot = event.target.closest('[data-side][data-pick]');
  if (!slot) return;
  const side = slot.dataset.side;
  const pick = Number(slot.dataset.pick);
  state.activeSide = side;
  state.sideToggle = side;
  state.activePick = pick;
  state.activePickBySide[side] = pick;
  renderSidebars();
  renderSideToggle();
}

function openPickMenu(side, index, anchor) {
  const pick = state[side][index];
  const items = [];
  if (pick) {
    items.push({ label: 'Remove pick', action: () => { state[side][index] = null; predictNow(); renderAll(); } });
    items.push({ separator: true });
    for (const role of ROLES) {
      items.push({
        label: `${ROLE_NAMES[role]}${pick.role === role ? ' ✓' : ''}`,
        action: () => { pick.role = role; predictNow(); renderAll(); },
      });
    }
  } else {
    items.push({ label: 'Clear team', action: () => { state[side] = [null, null, null, null, null]; predictNow(); renderAll(); } });
  }
  openContextMenu(anchor, items);
}

function openTeamMenu(side, anchor) {
  openContextMenu(anchor, [
    { label: `Clear ${side === 'allies' ? 'ally' : 'opponent'} picks`, action: () => { state[side] = [null, null, null, null, null]; predictNow(); renderAll(); } },
    { label: 'Clear all picks', action: () => { state.allies = [null, null, null, null, null]; state.opponents = [null, null, null, null, null]; predictNow(); renderAll(); } },
    { separator: true },
    { label: 'Quick JSON', action: () => openJsonModal() },
  ]);
}

function openContextMenu(anchor, items) {
  const menu = $('context-menu');
  menu._anchor = anchor;
  menu.innerHTML = items.map((item, index) => {
    if (item.separator) return '<div class="my-1.5 h-px border-neutral-700 bg-neutral-700" role="separator"></div>';
    if (item.info) return `<div role="menuitem" tabindex="-1" class="w-full text-left relative flex select-none items-center px-3 py-1.5 text-lg text-neutral-400">${esc(item.label)}</div>`;
    return `<button type="button" role="menuitem" tabindex="-1" class="w-full text-left relative flex select-none items-center px-3 py-1.5 text-lg hover:bg-neutral-700 focus:bg-neutral-700 transition-colors uppercase" data-menu-index="${index}">${esc(item.label)}</button>`;
  }).join('');
  menu.classList.remove('hidden');
  const rect = anchor.getBoundingClientRect();
  const width = 220;
  let left = Math.min(window.innerWidth - width - 8, Math.max(8, rect.right - width));
  let top = Math.min(window.innerHeight - 40, rect.bottom + 4);
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  menu.style.minWidth = `${width}px`;
  menu.onclick = (event) => {
    const button = event.target.closest('[data-menu-index]');
    if (!button) return;
    const item = items[Number(button.dataset.menuIndex)];
    const anchor = menu._anchor;
    closeContextMenu();
    if (anchor?.isConnected) anchor.focus();
    item?.action?.();
  };
  const buttons = () => [...menu.querySelectorAll('[role="menuitem"]')];
  const focusItem = (button) => {
    buttons().forEach((item) => { item.tabIndex = -1; });
    if (!button) return;
    button.tabIndex = 0;
    button.focus();
  };
  focusItem(buttons()[0]);
  menu.onkeydown = (event) => {
    const list = buttons();
    if (!list.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const current = list.indexOf(document.activeElement);
      const step = event.key === 'ArrowDown' ? 1 : -1;
      focusItem(list[(Math.max(0, current) + step + list.length) % list.length]);
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      focusItem(event.key === 'Home' ? list[0] : list[list.length - 1]);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeContextMenu(true);
    } else if (event.key === 'Tab') {
      closeContextMenu(false);
    }
  };
  setTimeout(() => document.addEventListener('pointerdown', outsideMenu), 0);
}

function outsideMenu(event) {
  if (!$('context-menu').contains(event.target)) closeContextMenu(true);
}

function closeContextMenu(restoreFocus = false) {
  const menu = $('context-menu');
  const anchor = menu._anchor;
  menu.classList.add('hidden');
  menu.onkeydown = null;
  menu._anchor = null;
  document.removeEventListener('pointerdown', outsideMenu);
  if (restoreFocus && anchor?.isConnected) anchor.focus();
}

function renderSideToggle() {
  const ally = $('side-ally');
  const opponent = $('side-opponent');
  const active = state.sideToggle;
  ally.className = `side-btn text-lg relative inline-flex items-center border text-neutral-300 border-neutral-700 bg-primary px-3 py-1 font-medium hover:bg-neutral-800 uppercase rounded-l-md ${active === 'allies' ? 'text-white bg-neutral-700!' : ''}`;
  opponent.className = `side-btn text-lg relative inline-flex items-center border text-neutral-300 border-neutral-700 bg-primary px-3 py-1 font-medium hover:bg-neutral-800 uppercase rounded-r-md -ml-px ${active === 'opponents' ? 'text-white bg-neutral-700!' : ''}`;
  ally.setAttribute('aria-pressed', String(active === 'allies'));
  opponent.setAttribute('aria-pressed', String(active === 'opponents'));
}

function renderRoleFilter() {
  const container = $('role-filter');
  container.innerHTML = ROLES.map((role) => {
    const active = state.roleFilter === role;
    return `<button type="button" data-role-filter="${role}" aria-pressed="${active}" aria-label="${ROLE_NAMES[role]} role" title="${ROLE_NAMES[role]}" class="w-full text-lg relative inline-flex justify-center items-center border text-neutral-300 border-neutral-700 bg-primary px-1 sm:px-3 py-1 font-medium hover:enabled:bg-neutral-800 focus:z-10 ${active ? 'text-white bg-neutral-700!' : ''} ${role === 0 ? 'rounded-l-md' : ''} ${role === 4 ? 'rounded-r-md -ml-px' : '-ml-px'}">${roleIcon(role, 'h-7')}</button>`;
  }).join('');
}

function draftRows() {
  if (!state.bootstrap) return [];
  // The original draft table is the ranked suggestion list for the team that
  // is currently being edited: already-picked champions and locked roles are
  // absent, and each winrate is the team winrate after that pick.
  const suggestions = state.suggestions?.[state.sideToggle] || [];
  const rows = [];
  for (const suggestion of suggestions) {
    const champion = state.byKey.get(String(suggestion.championKey));
    if (!champion) continue;
    const roleEntry = {
      ...suggestion,
      role: suggestion.role,
      winrate: suggestion.winrate,
      winrateText: suggestion.winrateText,
      damage: champion.roleMap?.get(suggestion.role)?.damage,
    };
    rows.push({ champion, roleEntry });
  }
  return rows;
}

function renderDraftTable() {
  if (!state.bootstrap) return;
  const lockedRoles = new Set(state[state.sideToggle].filter(Boolean).map((pick) => pick.role));
  if (state.roleFilter !== null && lockedRoles.has(state.roleFilter)) {
    state.roleFilter = null;
    renderRoleFilter();
  }
  const query = state.search.trim().toLowerCase();
  const picked = pickedKeys();
  const rows = draftRows().filter(({ champion, roleEntry }) => {
    if (state.roleFilter !== null && state.roleFilter !== roleEntry.role) return false;
    if (state.favoritesOnly && !state.favorites.has(`${champion.key}:${roleEntry.role}`)) return false;
    if (!query) return true;
    return [champion.name, champion.nameZh, champion.id, champion.key]
      .filter(Boolean).some((value) => String(value).toLowerCase().includes(query));
  });
  let firstFocusable = true;
  const body = rows.map(({ champion, roleEntry }) => {
    const isPicked = picked.has(champion.key);
    const favorite = state.favorites.has(`${champion.key}:${roleEntry.role}`);
    const rowTabIndex = !isPicked && firstFocusable ? 0 : -1;
    if (!isPicked && firstFocusable) firstFocusable = false;
    return `<tr class="transition duration-200 ease-out group/row hover:bg-neutral-800 ${isPicked ? 'opacity-30' : ''}" data-champion-key="${esc(champion.key)}" data-role="${roleEntry.role}" data-winrate-text="${esc(roleEntry.winrateText)}" tabindex="${rowTabIndex}">
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors pl-4 hover:bg-neutral-800 cursor-default">
        <div class="flex items-center justify-center">
          <button type="button" class="favorite-btn" data-favorite-key="${esc(champion.key)}" data-favorite-role="${roleEntry.role}" title="Favourite" aria-label="${favorite ? 'Remove' : 'Add'} ${esc(championName(champion))} ${ROLE_NAMES[roleEntry.role]} ${favorite ? 'from' : 'to'} favourites" aria-pressed="${favorite}" tabindex="-1">
            <svg viewBox="0 0 24 24" fill="${favorite ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.5" class="w-6 ${favorite ? 'opacity-100' : 'opacity-0 group-hover/row:opacity-50'} transition duration-200 ease-out" aria-hidden="true">${STAR_SVG}</svg>
          </button>
        </div>
      </td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors">
        <div class="flex items-center justify-center" aria-hidden="true">${roleIcon(roleEntry.role, 'h-8')}</div>
      </td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors">
        <div class="flex gap-2">${championIcon(champion, 36)}<span class="uppercase truncate">${esc(championName(champion))}</span></div>
      </td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors">
        <div class="flex justify-end"><span style="font-variant-numeric:tabular-nums" class="relative ${winrateClass(roleEntry.winrate)}">${esc(roleEntry.winrateText)}</span></div>
      </td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors pr-4">
        <button type="button" class="info-btn py-2" data-info-key="${esc(champion.key)}" data-info-role="${roleEntry.role}" aria-label="Details for ${esc(championName(champion))} ${ROLE_NAMES[roleEntry.role]}" tabindex="-1">
          <svg viewBox="0 0 20 20" fill="currentColor" stroke="none" class="w-5 h-5 opacity-40 hover:opacity-80 transition duration-150 ease-in-out" aria-hidden="true">${INFO_SVG}</svg>
        </button>
      </td>
    </tr>`;
  }).join('');
  $('draft-table').innerHTML = `<table class="min-w-full text-lg md:text-xl lg:text-2xl">
    <caption class="visually-hidden">Champion suggestions for the ${state.sideToggle === 'allies' ? 'ally' : 'opponent'} team</caption>
    <thead class="bg-neutral-900 sticky top-0 z-1"><tr>
      <th scope="col" class="py-3 px-2 text-left font-normal uppercase whitespace-nowrap pl-4 w-1"><button id="favorites-header" class="inline-flex group" title="Favourites only" aria-label="Show favourites only" aria-pressed="${state.favoritesOnly}"><svg viewBox="0 0 24 24" fill="${state.favoritesOnly ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.5" class="w-6 inline group-hover:opacity-80 transition duration-200 ease-out opacity-50" aria-hidden="true">${STAR_SVG}</svg></button></th>
      <th scope="col" class="py-3 px-2 text-left font-normal uppercase whitespace-nowrap w-1">Role</th>
      <th scope="col" class="py-3 px-2 text-left font-normal uppercase w-full whitespace-nowrap">Champion</th>
      <th scope="col" aria-sort="descending" class="py-3 px-2 text-left font-normal uppercase w-full whitespace-nowrap">Winrate</th>
      <th scope="col" class="py-3 px-2 text-left font-normal uppercase w-full whitespace-nowrap pr-4"></th>
    </tr></thead>
    <tbody class="divide-y divide-neutral-800 bg-primary">${body || `<tr><td colspan="5" class="py-10 text-center text-neutral-500 uppercase">No champions match</td></tr>`}</tbody>
  </table>`;
  $('draft-table').onclick = draftTableClick;
  $('draft-table').onkeydown = draftTableKeydown;
  $('draft-table').onfocusin = (event) => {
    const row = event.target.closest('tr[data-champion-key]');
    if (row) setRovingRow(row);
  };
  $('favorites-btn').setAttribute('aria-pressed', String(state.favoritesOnly));
  if (pendingRowFocus) {
    const target = tableRow(pendingRowFocus.key, pendingRowFocus.role);
    pendingRowFocus = null;
    if (target) focusTableRow(target);
    else $('draftTableSearch').focus();
  }
}

let pendingRowFocus = null;

function tableRow(key, role) {
  return [...$('draft-table').querySelectorAll('tr[data-champion-key]')]
    .find((row) => row.dataset.championKey === key && Number(row.dataset.role) === role) || null;
}

function setRovingRow(row) {
  for (const candidate of $('draft-table').querySelectorAll('tr[data-champion-key]')) {
    candidate.tabIndex = candidate === row ? 0 : -1;
  }
}

function focusTableRow(row) {
  setRovingRow(row);
  row.focus();
  row.scrollIntoView({ block: 'nearest' });
}

function toggleFavoriteRow(key, role) {
  const id = `${key}:${role}`;
  if (state.favorites.has(id)) state.favorites.delete(id); else state.favorites.add(id);
  localStorage.setItem('draftgap.favorites', JSON.stringify([...state.favorites]));
  pendingRowFocus = { key, role };
  renderDraftTable();
  if (state.favoritesOnly) announceDraftCount();
}

function announceDraftCount() {
  const count = $('draft-table').querySelectorAll('tbody tr[data-champion-key]').length;
  $('draft-table-status').textContent = `${count} champion suggestion${count === 1 ? '' : 's'}`;
}

function draftTableClick(event) {
  const favorite = event.target.closest('[data-favorite-key]');
  if (favorite) {
    event.stopPropagation();
    toggleFavoriteRow(favorite.dataset.favoriteKey, Number(favorite.dataset.favoriteRole));
    return;
  }
  if (event.target.closest('#favorites-header')) {
    state.favoritesOnly = !state.favoritesOnly;
    renderDraftTable();
    announceDraftCount();
    $('favorites-header')?.focus();
    return;
  }
  const info = event.target.closest('[data-info-key]');
  if (info) {
    event.stopPropagation();
    const row = info.closest('tr[data-champion-key]');
    showChampionInfo(
      info.dataset.infoKey,
      Number(info.dataset.infoRole),
      info,
      row?.dataset.winrateText,
    );
    return;
  }
  const row = event.target.closest('tr[data-champion-key]');
  if (!row) return;
  if (row.classList.contains('opacity-30')) return;
  assignChampion(row.dataset.championKey, Number(row.dataset.role));
}

function draftTableKeydown(event) {
  const row = event.target.closest('tr[data-champion-key]');
  if (!row || event.target !== row) return;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    if (!row.classList.contains('opacity-30')) assignChampion(row.dataset.championKey, Number(row.dataset.role));
    return;
  }
  if (event.key.toLowerCase() === 'f') {
    event.preventDefault();
    toggleFavoriteRow(row.dataset.championKey, Number(row.dataset.role));
    return;
  }
  if (event.key.toLowerCase() === 'i') {
    event.preventDefault();
    showChampionInfo(row.dataset.championKey, Number(row.dataset.role), row, row.dataset.winrateText);
    return;
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End', 'PageDown', 'PageUp'].includes(event.key)) return;
  const rows = [...$('draft-table').querySelectorAll('tr[data-champion-key]')]
    .filter((candidate) => !candidate.classList.contains('opacity-30'));
  if (!rows.length) return;
  event.preventDefault();
  const index = rows.indexOf(row);
  let next = index;
  if (event.key === 'ArrowDown') next = Math.min(rows.length - 1, index + 1);
  else if (event.key === 'ArrowUp') next = Math.max(0, index - 1);
  else if (event.key === 'Home') next = 0;
  else if (event.key === 'End') next = rows.length - 1;
  else if (event.key === 'PageDown') next = Math.min(rows.length - 1, index + 10);
  else if (event.key === 'PageUp') next = Math.max(0, index - 10);
  focusTableRow(rows[next]);
}

function assignChampion(key, role) {
  const champion = state.byKey.get(key);
  if (!champion) return;
  if (pickedKeys().has(key)) return;
  const side = state.sideToggle;
  const index = state.activePickBySide[side];
  state[side][index] = { key, id: champion.id, name: champion.name, nameZh: champion.nameZh, role };
  const next = state[side].findIndex((pick) => !pick);
  state.activePickBySide[side] = next >= 0 ? next : index;
  state.activePick = state.activePickBySide[side];
  if (state.roleFilter === role) state.roleFilter = null;
  state.search = '';
  $('draftTableSearch').value = '';
  renderAll();
  $('draftTableSearch').focus();
  predictNow();
}

function showChampionInfo(key, role, anchor, suggestionWinrateText) {
  const champion = state.byKey.get(key);
  const info = champion?.roleMap?.get(role);
  if (!info) return;
  const items = [
    { label: `${championName(champion)} · ${ROLE_NAMES[role]}`, info: true },
    { separator: true },
    { label: `Pick winrate ${suggestionWinrateText ?? info.winrateText}`, info: true },
    { label: `Patch games ${Math.round(info.games)}`, info: true },
    { label: `Base winrate ${info.winrateText}`, info: true },
  ];
  openContextMenu(anchor, items);
}

function renderAll() {
  renderHeader();
  renderSidebars();
  renderSideToggle();
  renderRoleFilter();
  renderDraftTable();
  if (state.tab === 'analysis') renderAnalysis();
  renderTabs();
}

function renderTabs() {
  document.querySelectorAll('.tab-btn').forEach((button) => {
    const active = button.dataset.tab === state.tab;
    button.className = `tab-btn px-4 py-3 uppercase font-semibold ${active ? 'text-neutral-50' : 'text-neutral-500 hover:text-neutral-400'}`;
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  });
  $('tab-draft').hidden = state.tab !== 'draft';
  $('tab-analysis').hidden = state.tab !== 'analysis';
}

function selectTab(tab) {
  state.tab = tab;
  renderTabs();
  if (tab === 'analysis') renderAnalysis();
}

function initTablist() {
  const tablist = $('draft-tablist');
  tablist.addEventListener('keydown', (event) => {
    const tabs = [...tablist.querySelectorAll('[role="tab"]')];
    const index = tabs.indexOf(document.activeElement);
    if (index < 0) return;
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    selectTab(tabs[next].dataset.tab);
    tabs[next].focus();
  });
}

function payloadForDraft() {
  const team = (side) => state[side].filter(Boolean).map((pick) => ({ champion: pick.key, role: pick.role }));
  const allies = team('allies');
  const opponents = team('opponents');
  // If the user picked two champions with the same role, let the model infer
  // the whole team instead of sending an invalid duplicate-role request.
  const dedupeRoles = (entries) => {
    const roles = entries.map((entry) => entry.role);
    return new Set(roles).size === roles.length ? entries : entries.map(({ champion }) => ({ champion }));
  };
  return {
    allies: dedupeRoles(allies),
    opponents: dedupeRoles(opponents),
    riskLevel: state.config.riskLevel,
    ignoreChampionWinrates: state.config.ignoreChampionWinrates,
    minGames: state.config.minGames,
    suggestions: 1000,
    includeTables: true,
    scaling: true,
  };
}

async function predictNow() {
  clearTimeout(state.predictionTimer);
  state.predictionTimer = setTimeout(predict, 30);
}

async function predict() {
  const requestId = ++state.requestId;
  const payload = payloadForDraft();
  try {
    const result = await api('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (requestId !== state.requestId) return;
    state.prediction = result;
    state.suggestions = result.suggestions || { allies: [], opponents: [] };
    renderSidebars();
    renderDraftTable();
    if (state.tab === 'analysis') renderAnalysis();
  } catch (error) {
    if (requestId !== state.requestId) return;
    // With an empty board the previous prediction is a valid 50% prior, so
    // keep the page usable even when the local service is restarting.
    if (!payload.allies.length && !payload.opponents.length) {
      state.prediction = emptyPrediction();
      renderSidebars();
    }
    toast(`${error.code || 'error'}: ${error.message}`);
  }
}

function emptyPrediction() {
  const zero = {
    championRating: 0, championWinrate: 0.5, championWinrateText: '50.00',
    matchupRating: 0, matchupWinrate: 0.5, matchupWinrateText: '50.00',
    duoRating: 0, duoWinrate: 0.5, duoWinrateText: '50.00',
    totalRating: 0, winrate: 0.5, winrateText: '50.00',
  };
  return {
    model: { currentPatch: state.bootstrap?.dataset || {}, config: state.config },
    draft: { allies: [], opponents: [], roleAssignmentsEvaluated: { allies: 0, opponents: 0 } },
    prediction: { allyWinrate: 0.5, allyWinrateText: '50.00', opponentWinrate: 0.5, opponentWinrateText: '50.00', ally: { ...zero }, opponent: { ...zero } },
    breakdown: { allies: { rows: [], totals: { baseText: '50.00', matchupText: '50.00', duoText: '50.00', totalText: '50.00' } }, opponents: { rows: [], totals: { baseText: '50.00', matchupText: '50.00', duoText: '50.00', totalText: '50.00' } } },
    matchups: { results: [], sameRoleResults: [], totals: { all: { allyText: '50.00', opponentText: '50.00' }, sameRole: { allyText: '50.00', opponentText: '50.00' } } },
    duos: { allies: { results: [], totals: { winrateText: '50.00' } }, opponents: { results: [], totals: { winrateText: '50.00' } } },
    scaling: { allies: [], opponents: [] },
    suggestions: { allies: [], opponents: [] },
    warnings: [],
  };
}

function card(team, icon, title, value, text, anchor) {
  const color = team === 'ally' ? 'bg-[#3c82f6]' : 'bg-opponent';
  return `<a href="#${anchor}" class="px-4 py-5 flex gap-4 items-center text-left">
    <div class="rounded-full h-[48px] w-[48px] flex items-center justify-center ${color}"><svg viewBox="0 0 24 24" fill="currentColor" stroke="none" class="w-6">${CARD_ICONS[icon]}</svg></div>
    <div><div class="text-lg text-neutral-400 uppercase">${title}</div>
      <div class="flex items-baseline justify-between md:block lg:flex -mt-1"><div class="flex items-baseline text-3xl"><span style="font-variant-numeric:tabular-nums" class="relative ${winrateClass(value)}">${text}</span></div></div>
    </div></a>`;
}

function cardsHTML(prediction, team) {
  const side = team === 'ally' ? prediction.prediction.ally : prediction.prediction.opponent;
  const total = team === 'ally' ? prediction.prediction.allyWinrate : prediction.prediction.opponentWinrate;
  const totalText = team === 'ally' ? prediction.prediction.allyWinrateText : prediction.prediction.opponentWinrateText;
  return `<div team="${team}" class="grid divide-neutral-700 overflow-hidden rounded-lg bg-primary grid-cols-2 md:grid-cols-4 md:divide-x ${team === 'opponent' ? 'mb-12 mt-6' : ''}">
    ${card(team, 'champions', 'Champions', side.championWinrate, side.championWinrateText, 'champions-result')}
    ${card(team, 'matchups', 'Matchups', side.matchupWinrate, side.matchupWinrateText, 'matchup-result')}
    ${card(team, 'duos', 'Duos', side.duoWinrate, side.duoWinrateText, 'duo-result')}
    ${card(team, 'winrate', 'Winrate', total, totalText, 'total-result')}
  </div>`;
}

function tableHead(columns) {
  return `<thead class="bg-neutral-900 sticky top-0 z-1"><tr>${columns.map((column, index) => `<th scope="col" class="py-3 px-2 text-left font-normal uppercase whitespace-nowrap ${index === 0 ? 'pl-4' : ''} ${index === columns.length - 1 ? 'pr-4' : ''} ${column.wide ? 'w-full' : 'w-1'}">${esc(column.label)}</th>`).join('')}</tr></thead>`;
}

function championCell(champion) {
  return `<div class="flex gap-2">${championIcon(champion, 36)}<span class="uppercase truncate">${esc(championName(champion))}</span></div>`;
}

function overviewTable(sideKey, prediction) {
  const rows = prediction.breakdown[sideKey].rows.map((row) => {
    const champion = state.byKey.get(row.championKey);
    return `<tr class="transition duration-200 ease-out group/row">
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors pl-4"><div class="flex items-center justify-center">${roleIcon(row.role, 'h-8')}</div></td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors">${championCell(champion)}</td>
      ${['base', 'matchup', 'duo', 'total'].map((key, index) => `<td class="whitespace-nowrap py-3 px-2 group/cell transition-colors ${index === 3 ? 'pr-4' : ''}"><span style="font-variant-numeric:tabular-nums" class="relative ${winrateClass(row[`${key}Winrate`])}">${esc(row[`${key}Text`])}</span></td>`).join('')}
    </tr>`;
  }).join('');
  const totals = prediction.breakdown[sideKey].totals;
  const totalCells = ['baseText', 'matchupText', 'duoText', 'totalText'].map((key, index) => `<th scope="col" class="py-3 px-2 text-left font-normal uppercase w-1 ${index === 3 ? 'pr-4' : ''}"><span style="font-variant-numeric:tabular-nums" class="relative ${winrateClass(prediction.breakdown[sideKey].totals[`${['base', 'matchup', 'duo', 'total'][index]}Winrate`])}">${esc(totals[key])}</span></th>`).join('');
  return `<div class="md:w-1/2"><h3 class="text-3xl mb-1 uppercase ml-4">${sideKey === 'allies' ? 'Ally' : 'Opponent'} overview</h3>
    <div class="rounded-md overflow-auto max-h-full max-w-full"><table class="min-w-full text-lg md:text-xl lg:text-2xl">
      ${tableHead([{ label: 'Role' }, { label: 'Champion', wide: true }, { label: 'Base' }, { label: 'Matchup' }, { label: 'Duo' }, { label: 'Total' }])}
      <tbody class="divide-y divide-neutral-800 bg-primary">${rows || `<tr><td colspan="6" class="py-8 text-center text-neutral-500 uppercase">No champions</td></tr>`}</tbody>
      <tfoot class="bg-neutral-900"><tr><th class="py-3 px-2 pl-4"></th><th class="py-3 px-2"></th>${totalCells}</tr></tfoot>
    </table></div></div>`;
}

function championsTable(sideKey, prediction) {
  const rows = prediction.breakdown[sideKey].rows.map((row) => {
    const champion = state.byKey.get(row.championKey);
    return `<tr class="transition duration-200 ease-out group/row">
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors pl-4"><div class="flex items-center justify-center">${roleIcon(row.role, 'h-8')}</div></td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors">${championCell(champion)}</td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors pr-4"><span style="font-variant-numeric:tabular-nums" class="relative ${winrateClass(row.baseWinrate)}">${esc(row.baseText)}</span></td>
    </tr>`;
  }).join('');
  return `<div class="sm:w-1/2"><h3 class="text-3xl uppercase mb-1 ml-4">${sideKey === 'allies' ? 'Ally' : 'Opponent'} champions</h3>
    <div class="rounded-md overflow-auto max-h-full max-w-full"><table class="min-w-full text-lg md:text-xl lg:text-2xl">
      ${tableHead([{ label: 'Role' }, { label: 'Champion', wide: true }, { label: 'Winrate' }])}
      <tbody class="divide-y divide-neutral-800 bg-primary">${rows || `<tr><td colspan="3" class="py-8 text-center text-neutral-500 uppercase">No champions</td></tr>`}</tbody>
      <tfoot class="bg-neutral-900"><tr><th class="py-3 px-2 pl-4"></th><th class="py-3 px-2"></th><th class="py-3 px-2 pr-4"><span style="font-variant-numeric:tabular-nums" class="relative ${winrateClass(prediction.breakdown[sideKey].totals.baseWinrate)}">${esc(prediction.breakdown[sideKey].totals.baseText)}</span></th></tr></tfoot>
    </table></div></div>`;
}

function matchupRow(row) {
  const ally = state.byKey.get(row.championKeyA);
  const opponent = state.byKey.get(row.championKeyB);
  const allyWins = row.allyWinrate >= row.opponentWinrate;
  const warning = row.games < 1000;
  const warn = warning ? `<div class="absolute -top-1 -right-6"><svg viewBox="0 0 20 20" fill="currentColor" stroke="none" class="text-yellow-500 w-5 h-5">${WARN_PATH}</svg></div>` : '';
  return `<tr class="transition duration-200 ease-out group/row">
    <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors pl-4"><div class="flex items-center justify-center">${roleIcon(row.roleA, 'h-8')}</div></td>
    <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors">${championCell(ally)}</td>
    <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors"><span style="font-variant-numeric:tabular-nums" class="relative ${winrateClass(row.allyWinrate)}">${esc(row.allyText)}${warn}</span></td>
    <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors"><div class="flex justify-center items-center w-full relative"><svg viewBox="0 0 20 20" fill="currentColor" stroke="none" class="absolute w-6 ${allyWins ? 'text-ally' : 'text-opponent'}">${allyWins ? LEFT_ARROW : RIGHT_ARROW}</svg></div></td>
    <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors"><div class="flex items-center justify-center">${roleIcon(row.roleB, 'h-8')}</div></td>
    <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors">${championCell(opponent)}</td>
    <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors pr-4"><span style="font-variant-numeric:tabular-nums" class="relative ${winrateClass(row.opponentWinrate)}">${esc(row.opponentText)}${warn}</span></td>
  </tr>`;
}

function matchupsSection(prediction) {
  const mode = state.matchupMode;
  const rows = (mode === 'all' ? prediction.matchups.results : prediction.matchups.sameRoleResults) || [];
  const totals = mode === 'all' ? prediction.matchups.totals.all : prediction.matchups.totals.sameRole;
  const button = (value, label, rounded) => `<button type="button" data-matchup-mode="${value}" class="uppercase leading-4 relative inline-flex items-center border border-neutral-700 px-3 font-medium hover:bg-neutral-600 focus:z-10 transition-all ease-in-out duration-150 py-2 ${rounded} ${mode === value ? 'text-white bg-neutral-700' : 'text-neutral-300 bg-primary'}">${label}</button>`;
  return `<div id="matchup-result"><div class="flex flex-col sm:flex-row sm:items-end justify-between mb-4">
    <div><h3 class="text-3xl uppercase ml-4">Matchups</h3><p class="text-neutral-500 uppercase ml-4">Champion winrates normalized</p></div>
    <div class="isolate inline-flex rounded-md shadow-xs ml-4 sm:ml-0">${button('sameRole', 'HEAD 2 HEAD', 'rounded-l-md')}${button('all', 'ALL', 'rounded-r-md -ml-px')}</div>
  </div>
  <div class="rounded-md overflow-auto max-h-full max-w-full w-full mb-8"><table class="min-w-full text-lg md:text-xl lg:text-2xl">
    ${tableHead([{ label: 'Role' }, { label: 'Ally' }, { label: 'Winrate' }, { label: 'Winner', wide: true }, { label: 'Role' }, { label: 'Opponent', wide: true }, { label: 'Winrate' }])}
    <tbody class="divide-y divide-neutral-800 bg-primary">${rows.map(matchupRow).join('') || `<tr><td colspan="7" class="py-8 text-center text-neutral-500 uppercase">Pick both teams to see matchups</td></tr>`}</tbody>
    <tfoot class="bg-neutral-900"><tr><th class="py-3 px-2 pl-4"></th><th class="py-3 px-2"></th><th class="py-3 px-2"><span style="font-variant-numeric:tabular-nums" class="${winrateClass(totals.allyWinrate)}">${esc(totals.allyText)}</span></th><th class="py-3 px-2"></th><th class="py-3 px-2"></th><th class="py-3 px-2"></th><th class="py-3 px-2 pr-4"><span style="font-variant-numeric:tabular-nums" class="${winrateClass(totals.opponentWinrate)}">${esc(totals.opponentText)}</span></th></tr></tfoot>
  </table></div></div>`;
}

function duoTable(sideKey, prediction) {
  const side = prediction.duos[sideKey];
  const rows = side.results.map((row) => {
    const a = state.byKey.get(row.championKeyA);
    const b = state.byKey.get(row.championKeyB);
    return `<tr class="transition duration-200 ease-out group/row">
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors pl-4"><div class="flex items-center justify-center">${roleIcon(row.roleA, 'h-8')}</div></td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors">${championCell(a)}</td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors"><div class="flex items-center justify-center">${roleIcon(row.roleB, 'h-8')}</div></td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors">${championCell(b)}</td>
      <td class="whitespace-nowrap py-3 px-2 group/cell transition-colors pr-4"><span style="font-variant-numeric:tabular-nums" class="relative ${winrateClass(row.winrate)}">${esc(row.winrateText)}</span></td>
    </tr>`;
  }).join('');
  return `<div class="sm:w-1/2"><h3 class="text-3xl uppercase mb-1 ml-4">${sideKey === 'allies' ? 'Ally' : 'Opponent'} duos</h3><p class="text-neutral-500 uppercase ml-4">Champion winrates normalized</p>
    <div class="rounded-md overflow-auto max-h-full max-w-full"><table class="min-w-full text-lg md:text-xl lg:text-2xl">
      ${tableHead([{ label: 'Role' }, { label: 'Champion' }, { label: 'Role' }, { label: 'Champion' }, { label: 'Winrate' }])}
      <tbody class="divide-y divide-neutral-800 bg-primary">${rows || `<tr><td colspan="5" class="py-8 text-center text-neutral-500 uppercase">Pick a team to see duos</td></tr>`}</tbody>
      <tfoot class="bg-neutral-900"><tr><th class="py-3 px-2 pl-4"></th><th class="py-3 px-2"></th><th class="py-3 px-2"></th><th class="py-3 px-2"></th><th class="py-3 px-2 pr-4"><span style="font-variant-numeric:tabular-nums" class="${winrateClass(side.totals.winrate)}">${esc(side.totals.winrateText)}</span></th></tr></tfoot>
    </table></div></div>`;
}

function renderScaling(prediction) {
  const canvas = $('scaling-canvas');
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  const width = Math.max(280, rect.width - 32);
  const height = Math.max(180, rect.height - 32);
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const ally = (prediction.scaling?.allies || []).map((point) => point.winrate);
  const opponent = (prediction.scaling?.opponents || []).map((point) => point.winrate);
  if (!ally.length) {
    ctx.fillStyle = '#8a8a8a';
    ctx.font = '14px Oswald, sans-serif';
    ctx.fillText('Pick champions to see the scaling curve', 16, height / 2);
    return;
  }
  const labels = (prediction.scaling.allies || []).map((point) => point.label);
  const values = [...ally, ...opponent].filter(Number.isFinite);
  let min = Math.min(...values) * 100;
  let max = Math.max(...values) * 100;
  min = Math.floor(min - 1);
  max = Math.ceil(max + 1);
  if (max - min < 6) { const mid = (min + max) / 2; min = mid - 3; max = mid + 3; }
  const pad = { left: 38, right: 14, top: 18, bottom: 30 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const x = (index) => pad.left + (labels.length === 1 ? plotW / 2 : (index / (labels.length - 1)) * plotW);
  const y = (value) => pad.top + (1 - (value * 100 - min) / (max - min)) * plotH;
  ctx.font = '11px OpenSans, sans-serif';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i++) {
    const tick = min + ((max - min) * i) / 4;
    const yy = y(tick / 100);
    ctx.strokeStyle = '#2b2b2b';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.left, yy); ctx.lineTo(width - pad.right, yy); ctx.stroke();
    ctx.fillStyle = '#8a8a8a';
    ctx.textAlign = 'right';
    ctx.fillText(`${tick.toFixed(1)}%`, pad.left - 7, yy);
  }
  ctx.textAlign = 'center';
  labels.forEach((label, index) => { ctx.fillStyle = '#8a8a8a'; ctx.fillText(label, x(index), height - 10); });
  const drawLine = (points, color) => {
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.beginPath();
    points.forEach((point, index) => { const xx = x(index); const yy = y(point); index ? ctx.lineTo(xx, yy) : ctx.moveTo(xx, yy); });
    ctx.stroke();
    points.forEach((point, index) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x(index), y(point), 3.5, 0, Math.PI * 2); ctx.fill(); });
  };
  drawLine(ally, '#3b82f6');
  drawLine(opponent, '#ef4444');
  ctx.textAlign = 'left';
  ctx.fillStyle = '#3b82f6'; ctx.fillRect(pad.left, 6, 10, 3); ctx.fillStyle = '#d6d6d6'; ctx.fillText('ALLY', pad.left + 15, 8);
  ctx.fillStyle = '#ef4444'; ctx.fillRect(pad.left + 64, 6, 10, 3); ctx.fillStyle = '#d6d6d6'; ctx.fillText('OPPONENT', pad.left + 79, 8);
}

function renderAnalysis() {
  const prediction = state.prediction || emptyPrediction();
  $('analysis-body').innerHTML = `
    <div>${cardsHTML(prediction, 'ally')}${cardsHTML(prediction, 'opponent')}</div>
    <div class="flex-col md:flex-row flex gap-4 mb-8 overflow-hidden" id="total-result">${overviewTable('allies', prediction)}${overviewTable('opponents', prediction)}</div>
    <div class="flex-col flex sm:flex-row gap-4 mb-8" id="champions-result">${championsTable('allies', prediction)}${championsTable('opponents', prediction)}</div>
    ${matchupsSection(prediction)}
    <div class="flex-col flex sm:flex-row gap-4 mb-8" id="duo-result">${duoTable('allies', prediction)}${duoTable('opponents', prediction)}</div>
    <div><h3 class="text-3xl uppercase ml-4">Scaling</h3><span class="text-neutral-500 uppercase ml-4 mb-2">Team winrate normalized</span>
      <div class="p-4 rounded-md bg-primary w-full md:w-1/2 max-w-2xl h-64"><canvas id="scaling-canvas"></canvas></div>
    </div>`;
  $('analysis-body').onclick = (event) => {
    const mode = event.target.closest('[data-matchup-mode]');
    if (mode) { state.matchupMode = mode.dataset.matchupMode; renderAnalysis(); }
  };
  requestAnimationFrame(() => renderScaling(prediction));
}

const QUICK_JSON_STORAGE = 'draftgap.quickJson';
let quickJsonSaveTimer = null;

function persistJsonInput() {
  clearTimeout(quickJsonSaveTimer);
  try { localStorage.setItem(QUICK_JSON_STORAGE, $('json-input').value); } catch { /* storage may be unavailable */ }
}

function schedulePersistJsonInput() {
  clearTimeout(quickJsonSaveTimer);
  quickJsonSaveTimer = setTimeout(persistJsonInput, 400);
}

function openJsonModal() {
  const dialog = $('json-dialog');
  if (dialog.open) return;
  if (!$('json-input').value.trim()) {
    try { $('json-input').value = localStorage.getItem(QUICK_JSON_STORAGE) || ''; } catch { /* storage may be unavailable */ }
  }
  dialog.showModal();
  $('json-input').focus();
  $('json-input').scrollTop = 0;
}

function closeJsonModal() {
  const dialog = $('json-dialog');
  persistJsonInput();
  if (dialog.open) dialog.close();
}

function setJsonStatus(message) {
  $('json-status').textContent = message;
}

function announceJson(message) {
  const live = $('json-live');
  live.textContent = '';
  setTimeout(() => { live.textContent = message; }, 80);
}

function setJsonError(message) {
  const input = $('json-input');
  const error = $('json-error');
  error.textContent = message;
  error.hidden = false;
  input.setAttribute('aria-invalid', 'true');
  const ids = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter((id) => id && id !== 'json-error');
  ids.push('json-error');
  input.setAttribute('aria-describedby', ids.join(' '));
  input.focus();
  announceJson(`JSON error: ${message}`);
}

function clearJsonError() {
  const input = $('json-input');
  const error = $('json-error');
  error.hidden = true;
  error.textContent = '';
  input.setAttribute('aria-invalid', 'false');
  const ids = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter((id) => id && id !== 'json-error');
  if (ids.length) input.setAttribute('aria-describedby', ids.join(' '));
  else input.removeAttribute('aria-describedby');
}

function parseJsonObject(text) {
  let payload;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new Error(`Invalid JSON: ${error.message}. Check quotes, commas, and braces.`);
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('Draft must be a JSON object with "allies" and "opponents".');
  }
  return payload;
}

function parseBoardPayload(payload) {
  const team = (value) => {
    if (Array.isArray(value)) return value;
    if (value && typeof value === 'object') {
      return Object.entries(value).map(([role, champion]) => ({ champion, role }));
    }
    return [];
  };
  return { allies: team(payload.allies), opponents: team(payload.opponents) };
}

function parseDraftText(text) {
  if (!state.bootstrap) throw new Error('The champion list is still loading. Try again in a moment.');
  const payload = parseJsonObject(text);
  const parsed = parseBoardPayload(payload);
  if (!parsed.allies.length && !parsed.opponents.length) {
    throw new Error('No picks found. Add at least one champion under "allies" or "opponents".');
  }
  const resolve = (entry) => {
    const value = typeof entry === 'string' ? entry : (entry?.champion ?? entry?.name ?? entry?.key);
    const champion = findChampionByName(value);
    if (!champion) {
      throw new Error(`Unknown champion: ${value ?? '(missing)'}. Use a DDragon id, English name, Chinese name, or numeric key.`);
    }
    return { champion, role: typeof entry === 'string' ? null : roleFromValue(entry?.role) };
  };
  const allies = parsed.allies.map(resolve);
  const opponents = parsed.opponents.map(resolve);
  if (allies.length > 5 || opponents.length > 5) {
    throw new Error('Each team can have at most 5 picks.');
  }
  return { payload, allies, opponents };
}

function jsonMetricTile(label, winrate, text) {
  const pct = Number.isFinite(winrate) ? winrate * 100 : 50;
  const delta = Math.max(-50, Math.min(50, pct - 50));
  const width = Math.min(50, Math.abs(delta) * 4);
  const side = delta >= 0 ? 'right' : 'left';
  const color = winrateClass(winrate);
  const fill = width > 0.5
    ? `<span class="ui-bar-fill ui-bar-fill--${side}" style="width:${width.toFixed(2)}%"></span>`
    : '';
  return `<div class="ui-kpi">
    <div class="ui-kpi-label">${esc(label)}</div>
    <div class="ui-kpi-value ${color}">${esc(text)}</div>
    <div class="ui-bar ${color}" aria-hidden="true">${fill}</div>
  </div>`;
}

function jsonBreakdownTable(sideKey, result) {
  const rows = result.breakdown?.[sideKey]?.rows || [];
  if (!rows.length) return '';
  const body = rows.map((row) => {
    const champion = state.byKey.get(row.championKey);
    const name = champion ? championName(champion) : row.name;
    return `<tr>
      <td><span class="ui-champion-cell">${championIcon(champion, 24)}<span>${esc(name)}</span></span></td>
      <td>${esc(ROLE_NAMES[row.role] ?? row.roleName)}</td>
      <td class="ui-num">${esc(row.baseText)}</td>
      <td class="ui-num">${esc(row.matchupText)}</td>
      <td class="ui-num">${esc(row.duoText)}</td>
      <td class="ui-num ${winrateClass(row.totalWinrate)}">${esc(row.totalText)}</td>
    </tr>`;
  }).join('');
  const team = sideKey === 'allies' ? 'ally' : 'opponent';
  return `<table class="ui-table">
    <caption class="visually-hidden">Per-champion winrate contributions for the ${team} team</caption>
    <thead><tr><th scope="col">Champion</th><th scope="col">Role</th><th scope="col" class="ui-num">Champ</th><th scope="col" class="ui-num">Vs</th><th scope="col" class="ui-num">Duo</th><th scope="col" class="ui-num">Total</th></tr></thead>
    <tbody>${body}</tbody>
  </table>`;
}

function jsonTeamSection(sideKey, result) {
  const isAlly = sideKey === 'allies';
  const cards = isAlly ? result.prediction.ally : result.prediction.opponent;
  const totalWinrate = isAlly ? result.prediction.allyWinrate : result.prediction.opponentWinrate;
  const totalText = isAlly ? result.prediction.allyWinrateText : result.prediction.opponentWinrateText;
  const label = isAlly ? 'Ally' : 'Opponent';
  return `<section class="ui-team" aria-label="${label} team prediction">
    <div class="ui-team-head">
      <span class="ui-team-name">${label}</span>
      <span class="ui-team-score ${winrateClass(totalWinrate)}">${esc(totalText)}<small>%</small></span>
    </div>
    <div class="ui-kpi-grid">
      ${jsonMetricTile('Champions', cards.championWinrate, cards.championWinrateText)}
      ${jsonMetricTile('Matchups', cards.matchupWinrate, cards.matchupWinrateText)}
      ${jsonMetricTile('Duos', cards.duoWinrate, cards.duoWinrateText)}
      ${jsonMetricTile('Total', totalWinrate, totalText)}
    </div>
    ${jsonBreakdownTable(sideKey, result)}
  </section>`;
}

function renderJsonResult(result) {
  const warnings = result.warnings || [];
  const warningBlock = warnings.length
    ? `<div class="ui-warnings" role="note"><svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">${WARN_PATH}</svg><div><strong>Warnings</strong><ul>${warnings.map((warning) => `<li>${esc(warning)}</li>`).join('')}</ul></div></div>`
    : '';
  $('json-result').innerHTML = `<div class="ui-team-grid">
    ${jsonTeamSection('allies', result)}
    ${jsonTeamSection('opponents', result)}
  </div>${warningBlock}`;
}

async function jsonPredict() {
  clearJsonError();
  let parsed;
  try {
    parsed = parseDraftText($('json-input').value);
  } catch (error) {
    setJsonError(error.message);
    setJsonStatus('Prediction not run.');
    $('json-result').innerHTML = '';
    $('json-copy').disabled = true;
    jsonPredict.lastResult = null;
    return;
  }
  const payload = parsed.payload;
  payload.riskLevel = state.config.riskLevel;
  payload.ignoreChampionWinrates = state.config.ignoreChampionWinrates;
  payload.minGames = state.config.minGames;
  if (payload.includeTables === undefined && payload.config?.includeTables === undefined) payload.includeTables = false;
  if (payload.scaling === undefined && payload.config?.scaling === undefined) payload.scaling = false;
  persistJsonInput();
  const button = $('json-predict');
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  $('json-result').setAttribute('aria-busy', 'true');
  setJsonStatus(`Predicting ${parsed.allies.length}v${parsed.opponents.length}…`);
  announceJson('Predicting draft.');
  try {
    const result = await api('/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    renderJsonResult(result);
    jsonPredict.lastResult = result;
    $('json-copy').disabled = false;
    const datasetDate = String(result.model.currentPatch.date || '').slice(0, 10);
    setJsonStatus(`Dataset ${result.model.currentPatch.version} · ${datasetDate} · ${parsed.allies.length}v${parsed.opponents.length}`);
    announceJson(`Ally winrate ${result.prediction.allyWinrateText} percent. Opponent ${result.prediction.opponentWinrateText} percent. Dataset ${result.model.currentPatch.version}.`);
  } catch (error) {
    setJsonStatus(`Prediction failed: ${error.code || 'error'} — ${error.message}`);
    announceJson('Prediction failed.');
  } finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
    $('json-result').removeAttribute('aria-busy');
  }
}

function jsonFormat() {
  clearJsonError();
  try {
    const payload = parseJsonObject($('json-input').value);
    $('json-input').value = JSON.stringify(payload, null, 2);
    setJsonStatus('Formatted JSON.');
    persistJsonInput();
    announceJson('JSON formatted.');
  } catch (error) {
    setJsonError(error.message);
    setJsonStatus('Formatting failed.');
  }
}

async function jsonCopy() {
  if (!jsonPredict.lastResult) return;
  const result = jsonPredict.lastResult;
  const summary = {
    prediction: result.prediction,
    draft: result.draft,
    breakdown: result.breakdown,
    warnings: result.warnings || [],
  };
  try {
    await navigator.clipboard.writeText(JSON.stringify(summary, null, 2));
    setJsonStatus('Result copied as JSON.');
    announceJson('Result copied as JSON.');
  } catch {
    setJsonStatus('Copy failed because the browser blocked clipboard access.');
    announceJson('Copy failed.');
  }
}

function applyPredictionToBoard(result) {
  state.allies = [null, null, null, null, null];
  state.opponents = [null, null, null, null, null];
  result.draft.allies.forEach((entry, index) => { if (index < 5) state.allies[index] = { key: entry.championKey, id: entry.championId, name: entry.name, nameZh: entry.nameZh, role: entry.role }; });
  result.draft.opponents.forEach((entry, index) => { if (index < 5) state.opponents[index] = { key: entry.championKey, id: entry.championId, name: entry.name, nameZh: entry.nameZh, role: entry.role }; });
  state.prediction = result;
  state.suggestions = result.suggestions || { allies: [], opponents: [] };
  state.activePickBySide = { allies: state.allies.findIndex((p) => !p), opponents: state.opponents.findIndex((p) => !p) };
  if (state.activePickBySide.allies < 0) state.activePickBySide.allies = 0;
  if (state.activePickBySide.opponents < 0) state.activePickBySide.opponents = 0;
  state.activePick = 0;
}

async function jsonToBoard() {
  clearJsonError();
  let parsed;
  try {
    parsed = parseDraftText($('json-input').value);
  } catch (error) {
    setJsonError(error.message);
    setJsonStatus('Could not load the board.');
    return;
  }
  const request = {
    allies: parsed.allies.map((e) => ({ champion: e.champion.key, ...(e.role == null ? {} : { role: e.role }) })),
    opponents: parsed.opponents.map((e) => ({ champion: e.champion.key, ...(e.role == null ? {} : { role: e.role }) })),
    riskLevel: state.config.riskLevel,
    ignoreChampionWinrates: state.config.ignoreChampionWinrates,
    minGames: state.config.minGames,
    suggestions: 1000,
  };
  const button = $('json-to-board');
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  setJsonStatus('Loading draft into the board…');
  announceJson('Loading draft into the board.');
  try {
    const result = await api('/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
    applyPredictionToBoard(result);
    state.tab = 'analysis';
    closeJsonModal();
    renderAll();
    toast(`Loaded ${parsed.allies.length}v${parsed.opponents.length} into the board`);
  } catch (error) {
    setJsonStatus(`Load failed: ${error.code || 'error'} — ${error.message}`);
    announceJson('Loading the board failed.');
  } finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
}

function openSettings() {
  const dialog = $('settings-dialog');
  $('risk-select').value = state.config.riskLevel;
  $('min-games-select').value = String(state.config.minGames);
  $('ignore-base').checked = state.config.ignoreChampionWinrates;
  if (!dialog.open) dialog.showModal();
  $('risk-select').focus();
}

function closeSettings() {
  const dialog = $('settings-dialog');
  if (dialog.open) dialog.close();
}

const PM_STATUS = { live: 'Live', upcoming: 'Upcoming', recent: 'Recent', finished: 'Final' };
const PM_TIME = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

function pmTimeLabel(value) {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? PM_TIME.format(new Date(timestamp)) : 'Time unknown';
}

function pmErrorText(error) {
  if (!error) return 'Unknown error';
  const code = error.code ? `${error.code}: ` : '';
  return `${code}${error.message || String(error)}${error.hint ? ` ${error.hint}` : ''}`;
}

function announceMarket(message) {
  const node = $('pm-live');
  if (node) node.textContent = message;
}

function openMarket() {
  const dialog = $('market-dialog');
  if (!dialog.open) dialog.showModal();
  if (!state.market.loaded && !state.market.loading) {
    loadMarketMatches();
  } else {
    renderMarketListStatus();
    renderMarketMatches();
    renderMarketPager();
    renderMarketDetail();
  }
  requestAnimationFrame(() => {
    const selected = $('pm-matches')?.querySelector('[aria-pressed="true"]');
    (selected || $('pm-refresh'))?.focus();
  });
}

function closeMarket() {
  const dialog = $('market-dialog');
  if (dialog.open) dialog.close();
}

function pmPageLabel() {
  const pm = state.market;
  return Number.isInteger(pm.totalPages) ? `Page ${pm.page} of ${pm.totalPages}` : `Page ${pm.page}`;
}

function renderMarketListStatus() {
  const node = $('pm-list-status');
  if (!node) return;
  const pm = state.market;
  if (pm.loading) {
    const page = pm.pendingPage || pm.page;
    node.textContent = pm.loaded ? `Loading matches page ${page}…` : 'Loading LoL matches…';
  } else if (pm.listError) {
    node.textContent = `Could not load matches. ${pm.listError}`;
  } else if (!pm.loaded) {
    node.textContent = 'Loading LoL matches…';
  } else if (pm.total === 0) {
    node.textContent = 'No LoL matches are listed right now.';
  } else {
    const hasTotal = Number.isInteger(pm.total);
    const first = pm.matches.length ? (pm.page - 1) * pm.pageSize + 1 : 0;
    const last = pm.matches.length ? first + pm.matches.length - 1 : 0;
    const summary = pm.matches.length
      ? `Showing ${first}–${last}${hasTotal ? ` of ${pm.total}` : ''} matches.`
      : (hasTotal ? `${pm.total} matches available.` : 'No matches on this page.');
    const more = !hasTotal && pm.hasNext ? ' More matches are available.' : '';
    node.textContent = pm.notes.length
      ? `${summary}${more} ${pm.notes[0]}`
      : `${summary}${more} Live drafts come from the market; finished games use the archive when needed.`;
  }
  const refresh = $('pm-refresh');
  if (refresh) {
    refresh.disabled = pm.loading;
    refresh.toggleAttribute('aria-busy', pm.loading);
  }
}

function pmMatchButton(match) {
  const active = state.market.selectedSlug === match.slug;
  const status = PM_STATUS[match.state] || match.state;
  const score = match.score ? `<span class="pm-match-score">${esc(match.score)}</span>` : '';
  const teams = match.teams || [];
  const left = teams[0]?.name || 'Team 1';
  const right = teams[1]?.name || 'Team 2';
  return `<button type="button" class="pm-match" data-pm-match="${esc(match.slug)}" aria-pressed="${active ? 'true' : 'false'}">
    <span class="pm-match-top">
      <span class="pm-match-teams">${esc(left)} <span class="pm-vs">vs</span> ${esc(right)}</span>
      ${score}
    </span>
    <span class="pm-match-meta">
      <span class="pm-status pm-status--${esc(match.state)}">${esc(status)}</span>
      <span class="pm-match-competition">${esc(match.competition || 'League of Legends')}</span>
      <time datetime="${esc(match.startTime || '')}">${esc(pmTimeLabel(match.startTime))}</time>
    </span>
  </button>`;
}

function renderMarketMatches() {
  const root = $('pm-matches');
  if (!root) return;
  const pm = state.market;
  root.toggleAttribute('aria-busy', pm.loading);
  if (!pm.matches.length) {
    root.innerHTML = pm.loading
      ? '<p class="pm-empty">Loading matches…</p>'
      : `<p class="pm-empty">${pm.listError ? 'The market could not be reached. Check the server proxy setting and try Refresh.' : 'No matches to display.'}</p>`;
    return;
  }
  root.innerHTML = pm.matches.map(pmMatchButton).join('');
}

function renderMarketPager() {
  const root = $('pm-pager');
  if (!root) return;
  const pm = state.market;
  if (!pm.loaded || pm.listError || pm.total === 0) {
    root.hidden = true;
    root.innerHTML = '';
    return;
  }
  root.hidden = false;
  root.innerHTML = `
    <button type="button" class="ui-btn pm-page-btn" data-pm-page="${pm.page - 1}" aria-controls="pm-matches" aria-label="Previous matches page"${pm.hasPrevious && !pm.loading ? '' : ' disabled'}>Previous</button>
    <span class="pm-page-status" role="status" aria-live="polite">${pmPageLabel()}</span>
    <button type="button" class="ui-btn pm-page-btn" data-pm-page="${pm.page + 1}" aria-controls="pm-matches" aria-label="Next matches page"${pm.hasNext && !pm.loading ? '' : ' disabled'}>Next</button>`;
}

function pmGameButtons(detail) {
  const games = detail?.games || [];
  if (!games.length) return '<p class="pm-empty">No games are listed for this match yet.</p>';
  return games.map((game) => {
    const selected = state.market.selectedGame === game.number;
    const winner = game.winnerSide === 'home'
      ? detail.home?.name
      : game.winnerSide === 'away' ? detail.away?.name : null;
    const kills = Number.isFinite(game.homeKills) && Number.isFinite(game.awayKills)
      ? `<span class="pm-game-meta">${game.homeKills}–${game.awayKills} kills</span>`
      : '';
    return `<button type="button" class="pm-game" data-pm-game="${game.number}" aria-pressed="${selected ? 'true' : 'false'}">
      <span class="pm-game-head"><span>${esc(game.label)}</span><span class="pm-status pm-status--${esc(game.status)}">${esc(PM_STATUS[game.status] || game.status)}</span></span>
      ${winner ? `<span class="pm-game-winner">${esc(winner)} won</span>` : ''}
      ${kills}
    </button>`;
  }).join('');
}

function renderMarketGames(focusGame = null) {
  const node = $('pm-games');
  if (!node) return;
  node.innerHTML = pmGameButtons(state.market.detail);
  if (focusGame != null) {
    requestAnimationFrame(() => node.querySelector(`[data-pm-game="${focusGame}"]`)?.focus());
  }
}

function pmTeamCard(side, team, allySide) {
  const picks = team?.picks || [];
  const rows = picks.length
    ? picks.map(pmPickRow).join('')
    : '<li class="pm-pick-empty">No lineup is published for this team yet.</li>';
  const bans = (team?.bans || []).length
    ? `<p class="pm-bans"><span>Bans</span> ${team.bans.map((ban) => esc(state.language === 'zh' && ban.nameZh ? ban.nameZh : ban.name || ban.champion)).join(', ')}</p>`
    : '';
  let roleNote = 'Roles were not published with this snapshot.';
  if (team?.roleSource === 'leaguepedia-pick-order') roleNote = 'Roles follow Leaguepedia’s top/jungle/mid/bottom/support pick order.';
  else if (team?.roleSource === 'market-player-order') roleNote = 'Roles are inferred from the market’s player order.';
  return `<article class="pm-team-card ${side === allySide ? 'is-ally' : ''}">
    <header class="pm-team-head">
      <div>
        <p class="pm-kicker">${side === allySide ? 'Your allies' : 'Your opponents'}</p>
        <h4>${esc(team?.name || 'Unknown team')}</h4>
      </div>
      <div class="pm-team-marks">
        ${team?.won ? '<span class="pm-win">Win</span>' : ''}
        ${Number.isFinite(team?.gameKills) ? `<span>${team.gameKills} kills</span>` : ''}
      </div>
    </header>
    <ol class="pm-picks">${rows}</ol>
    ${bans}
    <p class="pm-role-note">${esc(roleNote)}</p>
  </article>`;
}

function pmPickRow(pick) {
  const roleKnown = Number.isInteger(pick.role);
  const roleMark = roleKnown
    ? `<span class="pm-role-icon" aria-hidden="true">${roleIcon(pick.role, 'h-5 w-5')}</span>`
    : '<span class="pm-role-unknown" aria-hidden="true">?</span>';
  const championNameValue = state.language === 'zh' && pick.nameZh
    ? pick.nameZh
    : (pick.name || pick.champion || 'Unknown');
  const icon = pick.resolved && pick.championId
    ? championIcon({ id: pick.championId }, 30)
    : '<span class="pm-champ-missing" aria-hidden="true">?</span>';
  const player = pick.player ? `<span class="pm-pick-player">${esc(pick.player)}</span>` : '';
  const unresolved = pick.resolved ? '' : '<span class="pm-unmapped">unmapped</span>';
  const roleLabel = roleKnown ? ROLE_NAMES[pick.role] : 'Role unavailable';
  return `<li class="pm-pick${pick.resolved ? '' : ' is-unresolved'}">
    <span class="pm-pick-role" title="${esc(roleLabel)}" aria-label="${esc(roleLabel)}">${roleMark}</span>
    ${icon}
    <span class="pm-pick-text"><span class="pm-pick-name">${esc(championNameValue)}</span>${player}</span>
    ${unresolved}
  </li>`;
}

function pmCoverageText(lineup) {
  const coverage = lineup?.coverage || {};
  const mapped = coverage.resolved || 0;
  const picks = coverage.picks || 0;
  return `${mapped}/${picks || '—'} picks matched${coverage.complete ? ' · 5v5' : ' · partial lineup'}`;
}

function renderMarketLineup() {
  const node = $('pm-lineup');
  if (!node) return;
  const pm = state.market;
  if (pm.lineupLoading) {
    node.innerHTML = '<p class="pm-empty">Loading lineup…</p>';
    return;
  }
  if (pm.lineupError) {
    node.innerHTML = `<div class="pm-error"><strong>Could not load the lineup.</strong><p>${esc(pm.lineupError)}</p><button type="button" class="ui-btn" data-pm-retry-lineup="true">Retry</button></div>`;
    return;
  }
  const lineup = pm.lineup;
  if (!lineup) {
    node.innerHTML = '<p class="pm-empty">Choose a game to see its published lineup.</p>';
    return;
  }
  const source = lineup.source || {};
  const kind = ['market', 'leaguepedia', 'none'].includes(source.kind) ? source.kind : 'none';
  if (kind === 'none') {
    node.innerHTML = `<div class="pm-no-lineup">
      <span class="pm-source pm-source--none">${esc(source.label || 'No lineup published')}</span>
      <p>${esc(source.note || 'No lineup is available for this game yet.')}</p>
      <button type="button" class="ui-btn" data-pm-retry-lineup="true">Refresh lineup</button>
    </div>`;
    return;
  }
  const allySide = pm.allySide === 'away' ? 'away' : 'home';
  const warnings = (lineup.warnings || []).length
    ? `<div class="pm-warnings"><strong>Notes</strong><ul>${lineup.warnings.map((warning) => `<li>${esc(warning)}</li>`).join('')}</ul></div>`
    : '';
  const canLoad = (lineup.home?.picks || []).some((pick) => pick.resolved)
    || (lineup.away?.picks || []).some((pick) => pick.resolved);
  node.innerHTML = `
    <div class="pm-lineup-head">
      <span class="pm-source pm-source--${esc(kind)}">${esc(source.label || 'Lineup')}</span>
      <span class="pm-lineup-game">${esc(lineup.gameLabel || '')}</span>
      <span class="pm-coverage">${esc(pmCoverageText(lineup))}</span>
    </div>
    <p class="pm-source-note">${esc(source.note || '')}</p>
    <div class="pm-ally-picker">
      <span class="ui-field-label" id="pm-ally-label">Load which team as allies?</span>
      <div class="pm-ally-options" role="group" aria-labelledby="pm-ally-label">
        <button type="button" data-pm-ally="home" aria-pressed="${allySide === 'home' ? 'true' : 'false'}">${esc(lineup.home?.name || 'Home')}</button>
        <button type="button" data-pm-ally="away" aria-pressed="${allySide === 'away' ? 'true' : 'false'}">${esc(lineup.away?.name || 'Away')}</button>
      </div>
    </div>
    <div class="pm-team-grid">
      ${pmTeamCard('home', lineup.home, allySide)}
      ${pmTeamCard('away', lineup.away, allySide)}
    </div>
    <div class="pm-loadbar">
      <span>${esc(pmCoverageText(lineup))}</span>
      <button id="pm-load" type="button" class="ui-btn ui-btn--primary" ${canLoad && !pm.loadingBoard ? '' : 'disabled'} aria-busy="${pm.loadingBoard ? 'true' : 'false'}">${pm.loadingBoard ? 'Loading…' : `Load ${esc(lineup.gameLabel || 'lineup')} into DraftGap`}</button>
    </div>
    ${pm.actionError ? `<p class="pm-error-inline" role="alert">${esc(pm.actionError)}</p>` : ''}
    ${warnings}`;
}

function renderMarketDetail() {
  const root = $('pm-detail');
  if (!root) return;
  const pm = state.market;
  if (pm.detailLoading) {
    root.innerHTML = '<p class="pm-empty">Loading match…</p>';
    return;
  }
  if (pm.detailError) {
    root.innerHTML = `<div class="pm-error"><strong>Could not load this match.</strong><p>${esc(pm.detailError)}</p><button type="button" class="ui-btn" data-pm-retry-match="true">Retry</button></div>`;
    return;
  }
  const detail = pm.detail;
  if (!detail) {
    root.innerHTML = '<p class="pm-empty">Choose a match to see its games and lineups.</p>';
    return;
  }
  const score = detail.score ? `<span class="pm-score">${esc(detail.score)}</span>` : '';
  const bestOf = detail.bestOf ? `Best of ${detail.bestOf}` : '';
  const notes = (detail.notes || []).map((note) => `<p class="pm-note">${esc(note)}</p>`).join('');
  root.innerHTML = `
    <div class="pm-detail-head">
      <div>
        <p class="pm-kicker">${esc(detail.competition || 'League of Legends')}</p>
        <h3>${esc(detail.title)}</h3>
      </div>
    </div>
    <div class="pm-facts">
      <span class="pm-status pm-status--${esc(detail.state)}">${esc(PM_STATUS[detail.state] || detail.state)}</span>
      <span>${esc(pmTimeLabel(detail.startTime))}</span>
      ${bestOf ? `<span>${esc(bestOf)}</span>` : ''}
      ${score}
    </div>
    <div class="pm-games-head"><span class="ui-field-label">Games</span><span>${detail.games?.length ? `${detail.games.length} listed` : ''}</span></div>
    <div id="pm-games" class="pm-games" role="group" aria-label="Games in this match">${pmGameButtons(detail)}</div>
    ${notes}
    <div id="pm-lineup" class="pm-lineup"></div>`;
  renderMarketLineup();
}

function applyMarketPage(data, fallbackPage) {
  const pm = state.market;
  const pagination = data.pagination || {};
  pm.loaded = true;
  pm.loading = false;
  pm.pendingPage = null;
  pm.listError = null;
  pm.matches = Array.isArray(data.matches) ? data.matches : [];
  pm.notes = Array.isArray(data.notes) ? data.notes : [];
  const previousTotal = pm.total;
  const previousTotalPages = pm.totalPages;
  pm.page = Number.isInteger(pagination.page) ? pagination.page : fallbackPage;
  pm.pageSize = Number.isInteger(pagination.pageSize) ? pagination.pageSize : pm.pageSize;
  pm.total = Number.isInteger(pagination.total) ? pagination.total : previousTotal;
  pm.totalPages = Number.isInteger(pagination.totalPages) ? pagination.totalPages : previousTotalPages;
  pm.hasPrevious = pagination.hasPrevious === true;
  pm.hasNext = pagination.hasNext === true;
}

async function loadMarketMatches(page = state.market.page, force = false) {
  const pm = state.market;
  if (pm.loading) return;
  const targetPage = Math.max(1, Number(page) || 1);
  if (force) {
    pm.pageCache.clear();
    pm.total = null;
    pm.totalPages = null;
  }
  const cached = force ? null : pm.pageCache.get(targetPage);
  if (cached) {
    applyMarketPage(cached, targetPage);
    renderMarketListStatus();
    renderMarketMatches();
    renderMarketPager();
    announceMarket(`${pmPageLabel()}: ${pm.matches.length} matches loaded.`);
    return;
  }
  pm.loading = true;
  pm.pendingPage = targetPage;
  pm.listError = null;
  renderMarketListStatus();
  renderMarketMatches();
  renderMarketPager();
  const seq = ++pm.listSeq;
  try {
    const data = await api(`/api/market/matches?page=${targetPage}&limit=${pm.pageSize}${force ? '&refresh=1' : ''}`);
    if (seq !== pm.listSeq) return;
    pm.pageCache.set(targetPage, data);
    applyMarketPage(data, targetPage);
    pm.pageCache.set(pm.page, data);
    renderMarketListStatus();
    renderMarketMatches();
    renderMarketPager();
    announceMarket(`${pmPageLabel()}: ${pm.matches.length} matches loaded.`);
    if (!pm.selectedSlug) renderMarketDetail();
  } catch (error) {
    if (seq !== pm.listSeq) return;
    pm.loading = false;
    pm.pendingPage = null;
    pm.loaded = true;
    pm.listError = pmErrorText(error);
    renderMarketListStatus();
    renderMarketMatches();
    renderMarketPager();
    announceMarket('Could not load matches.');
  }
}

async function selectMarketMatch(slug) {
  if (!slug) return;
  const pm = state.market;
  pm.selectedSlug = slug;
  pm.allySide = 'home';
  pm.actionError = null;
  pm.detail = null;
  pm.detailError = null;
  pm.detailLoading = true;
  pm.selectedGame = null;
  pm.lineup = null;
  pm.lineupError = null;
  pm.lineupLoading = false;
  pm.lineupSeq += 1;
  renderMarketMatches();
  renderMarketDetail();
  const seq = ++pm.detailSeq;
  try {
    const detail = await api(`/api/market/match?slug=${encodeURIComponent(slug)}`);
    if (seq !== pm.detailSeq || pm.selectedSlug !== slug) return;
    pm.detailLoading = false;
    pm.detail = detail;
    pm.selectedGame = pmDefaultGame(detail.games || []);
    renderMarketDetail();
    announceMarket(`Loaded ${detail.title}.`);
    if (pm.selectedGame != null) await loadMarketLineup(slug, pm.selectedGame);
  } catch (error) {
    if (seq !== pm.detailSeq || pm.selectedSlug !== slug) return;
    pm.detailLoading = false;
    pm.detailError = pmErrorText(error);
    renderMarketDetail();
  }
}

function pmDefaultGame(games) {
  const live = games.find((game) => game.status === 'live');
  if (live) return live.number;
  const upcoming = games.find((game) => game.status === 'upcoming');
  if (upcoming) return upcoming.number;
  for (let index = games.length - 1; index >= 0; index -= 1) {
    if (games[index].status === 'finished') return games[index].number;
  }
  return games[0]?.number ?? null;
}

async function selectMarketGame(gameNumber, focus = true) {
  const pm = state.market;
  if (!pm.detail || pm.selectedGame === gameNumber && (pm.lineup || pm.lineupLoading)) {
    if (focus) renderMarketGames(gameNumber);
    return;
  }
  pm.selectedGame = gameNumber;
  pm.lineup = null;
  pm.lineupError = null;
  pm.actionError = null;
  pm.lineupSeq += 1;
  renderMarketGames(focus ? gameNumber : null);
  renderMarketLineup();
  await loadMarketLineup(pm.selectedSlug, gameNumber);
}

async function loadMarketLineup(slug, gameNumber) {
  const pm = state.market;
  const seq = ++pm.lineupSeq;
  pm.lineupLoading = true;
  pm.lineupError = null;
  pm.actionError = null;
  renderMarketLineup();
  try {
    const lineup = await api(`/api/market/lineup?slug=${encodeURIComponent(slug)}&game=${gameNumber}`);
    if (seq !== pm.lineupSeq || pm.selectedSlug !== slug || pm.selectedGame !== gameNumber) return;
    pm.lineupLoading = false;
    pm.lineup = lineup;
    renderMarketLineup();
    announceMarket(`${lineup.gameLabel} lineup loaded from ${lineup.source?.label || 'the data source'}.`);
  } catch (error) {
    if (seq !== pm.lineupSeq || pm.selectedSlug !== slug || pm.selectedGame !== gameNumber) return;
    pm.lineupLoading = false;
    pm.lineupError = pmErrorText(error);
    renderMarketLineup();
    announceMarket('Lineup loading failed.');
  }
}

function pmEntries(picks) {
  const entries = (picks || [])
    .filter((pick) => pick.resolved && pick.championKey)
    .slice(0, 5)
    .map((pick) => ({ champion: pick.championKey, ...(Number.isInteger(pick.role) ? { role: pick.role } : {}) }));
  const roles = entries.filter((entry) => entry.role != null).map((entry) => entry.role);
  return new Set(roles).size === roles.length ? entries : entries.map(({ champion }) => ({ champion }));
}

async function loadMarketIntoBoard() {
  const pm = state.market;
  const lineup = pm.lineup;
  const detail = pm.detail;
  if (!lineup || !detail) return;
  const allySide = pm.allySide === 'away' ? 'away' : 'home';
  const opponentSide = allySide === 'home' ? 'away' : 'home';
  const allies = pmEntries(lineup[allySide]?.picks);
  const opponents = pmEntries(lineup[opponentSide]?.picks);
  if (!allies.length && !opponents.length) {
    pm.actionError = 'This lineup has no champions that DraftGap can load.';
    renderMarketLineup();
    return;
  }
  pm.loadingBoard = true;
  pm.actionError = null;
  renderMarketLineup();
  try {
    const result = await api('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        allies,
        opponents,
        riskLevel: state.config.riskLevel,
        ignoreChampionWinrates: state.config.ignoreChampionWinrates,
        minGames: state.config.minGames,
        suggestions: 1000,
      }),
    });
    applyPredictionToBoard(result);
    state.tab = 'analysis';
    pm.loadingBoard = false;
    const count = allies.length + opponents.length;
    const sourceLabel = lineup.source?.label || 'market';
    closeMarket();
    renderAll();
    toast(`Loaded ${lineup.gameLabel} from ${sourceLabel} (${count}/10 picks)`);
  } catch (error) {
    pm.loadingBoard = false;
    pm.actionError = pmErrorText(error);
    renderMarketLineup();
  }
}

function initLightDismiss(dialog) {
  if ('closedBy' in HTMLDialogElement.prototype) return;
  let pressedOutside = false;
  const outside = (event) => {
    const rect = dialog.getBoundingClientRect();
    return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
  };
  dialog.addEventListener('pointerdown', (event) => { pressedOutside = outside(event); });
  dialog.addEventListener('pointerup', (event) => {
    if (pressedOutside && outside(event)) dialog.close();
    pressedOutside = false;
  });
}

function wireEvents() {
  const switchSide = (side) => {
    state.sideToggle = side;
    state.activeSide = side;
    renderSideToggle();
    renderSidebars();
    renderDraftTable();
    announceDraftCount();
  };
  $('side-ally').addEventListener('click', () => switchSide('allies'));
  $('side-opponent').addEventListener('click', () => switchSide('opponents'));
  $('draftTableSearch').addEventListener('input', (event) => { state.search = event.target.value; renderDraftTable(); });
  $('role-filter').addEventListener('click', (event) => {
    const button = event.target.closest('[data-role-filter]');
    if (!button) return;
    const role = Number(button.dataset.roleFilter);
    state.roleFilter = state.roleFilter === role ? null : role;
    renderRoleFilter();
    renderDraftTable();
    announceDraftCount();
  });
  $('favorites-btn').addEventListener('click', () => {
    state.favoritesOnly = !state.favoritesOnly;
    renderDraftTable();
    announceDraftCount();
  });
  document.querySelectorAll('.tab-btn').forEach((button) => button.addEventListener('click', () => selectTab(button.dataset.tab)));
  $('market-open').addEventListener('click', openMarket);
  $('pm-close').addEventListener('click', closeMarket);
  $('pm-refresh').addEventListener('click', () => loadMarketMatches(1, true));
  $('pm-matches').addEventListener('click', (event) => {
    const button = event.target.closest('[data-pm-match]');
    if (!button) return;
    selectMarketMatch(button.dataset.pmMatch);
  });
  $('pm-pager').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-pm-page]');
    if (!button || button.disabled) return;
    await loadMarketMatches(Number(button.dataset.pmPage));
    if (!state.market.listError) {
      requestAnimationFrame(() => $('pm-matches')?.querySelector('[data-pm-match]')?.focus());
    }
  });
  $('pm-detail').addEventListener('click', (event) => {
    const game = event.target.closest('[data-pm-game]');
    if (game) {
      selectMarketGame(Number(game.dataset.pmGame));
      return;
    }
    const ally = event.target.closest('[data-pm-ally]');
    if (ally) {
      state.market.allySide = ally.dataset.pmAlly === 'away' ? 'away' : 'home';
      renderMarketLineup();
      requestAnimationFrame(() => document.querySelector(`[data-pm-ally="${state.market.allySide}"]`)?.focus());
      return;
    }
    if (event.target.closest('#pm-load')) {
      loadMarketIntoBoard();
      return;
    }
    if (event.target.closest('[data-pm-retry-lineup]')) {
      if (state.market.selectedSlug && state.market.selectedGame != null) {
        loadMarketLineup(state.market.selectedSlug, state.market.selectedGame);
      }
      return;
    }
    if (event.target.closest('[data-pm-retry-match]')) {
      if (state.market.selectedSlug) selectMarketMatch(state.market.selectedSlug);
    }
  });
  $('json-open').addEventListener('click', openJsonModal);
  $('json-close').addEventListener('click', closeJsonModal);
  $('json-form').addEventListener('submit', (event) => { event.preventDefault(); jsonPredict(); });
  $('json-input').addEventListener('input', () => {
    if (!$('json-error').hidden) clearJsonError();
    schedulePersistJsonInput();
  });
  $('json-input').addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && !event.isComposing) {
      event.preventDefault();
      $('json-form').requestSubmit();
    }
  });
  $('json-sample').addEventListener('click', () => {
    $('json-input').value = JSON.stringify(SAMPLE, null, 2);
    clearJsonError();
    setJsonStatus('Sample draft loaded. Press Predict.');
    $('json-input').focus();
    $('json-input').scrollTop = 0;
    persistJsonInput();
  });
  $('json-format').addEventListener('click', jsonFormat);
  $('json-copy').addEventListener('click', jsonCopy);
  $('json-to-board').addEventListener('click', jsonToBoard);
  $('settings-btn').addEventListener('click', openSettings);
  $('settings-close').addEventListener('click', closeSettings);
  $('settings-form').addEventListener('submit', (event) => event.preventDefault());
  $('risk-select').addEventListener('change', (event) => { state.config.riskLevel = event.target.value; localStorage.setItem('draftgap.risk', state.config.riskLevel); predictNow(); });
  $('min-games-select').addEventListener('change', (event) => { state.config.minGames = Number(event.target.value); localStorage.setItem('draftgap.minGames', String(state.config.minGames)); predictNow(); });
  $('ignore-base').addEventListener('change', (event) => { state.config.ignoreChampionWinrates = event.target.checked; localStorage.setItem('draftgap.ignoreBase', event.target.checked ? '1' : '0'); predictNow(); });
  $('lang-btn').addEventListener('click', () => {
    state.language = state.language === 'en' ? 'zh' : 'en';
    localStorage.setItem('draftgap.language', state.language);
    renderAll();
  });
  $('sync-btn').addEventListener('click', async () => {
    const button = $('sync-btn');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = 'Syncing…';
    try {
      await api('/api/refresh', { method: 'POST' });
      toast('Checking DraftGap datasets…');
      setTimeout(refreshHealth, 1200);
    } catch (error) { toast(`${error.code || 'error'}: ${error.message}`); }
    finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.textContent = 'Sync with league client';
    }
  });
  $('menu-btn').addEventListener('click', (event) => {
    openContextMenu(event.currentTarget, [
      { label: 'LoL market lineups', action: openMarket },
      { label: 'Quick JSON', action: openJsonModal },
      { label: 'Refresh datasets', action: async () => { try { await api('/api/refresh', { method: 'POST' }); toast('Refreshing datasets…'); setTimeout(refreshHealth, 1200); } catch (error) { toast(error.message); } } },
      { separator: true },
      { label: 'Clear all picks', action: () => { state.allies = [null, null, null, null, null]; state.opponents = [null, null, null, null, null]; state.suggestions = { allies: [], opponents: [] }; state.prediction = emptyPrediction(); predictNow(); renderAll(); } },
    ]);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeContextMenu();
    const editable = event.target.closest?.('input, textarea, select, [contenteditable="true"]');
    if (!editable && !event.metaKey && !event.ctrlKey && !event.altKey && event.key.toLowerCase() === 'j'
      && !$('json-dialog').open && !$('settings-dialog').open && !$('market-dialog').open) {
      closeContextMenu();
      openJsonModal();
    }
  });
}

async function refreshHealth() {
  try {
    const health = await api('/health');
    state.health = health;
    if (health.refreshing) { toast('Refreshing datasets…'); setTimeout(refreshHealth, 2000); return; }
    const patchChanged = state.datasetDate && health.currentPatchDate
      && health.currentPatchDate !== state.datasetDate;
    const thirtyChanged = state.thirtyDayDate && health.thirtyDayDate
      && health.thirtyDayDate !== state.thirtyDayDate;
    if (patchChanged || thirtyChanged) {
      await loadBootstrap();
      toast(`Dataset updated to ${health.currentPatch}`);
    }
    if (health.refreshError) toast(`Refresh failed: ${health.refreshError}`);
  } catch (error) { /* keep the page usable offline */ }
}

function init() {
  try {
    const stored = JSON.parse(localStorage.getItem('draftgap.favorites') || '[]');
    state.favorites = new Set(
      stored.flatMap((value) => {
        const text = String(value);
        // Older builds stored only the champion key.
        return text.includes(':') ? [text] : ROLES.map((role) => `${text}:${role}`);
      }),
    );
  } catch {
    state.favorites = new Set();
  }
  wireEvents();
  initToast();
  initTablist();
  initLightDismiss($('json-dialog'));
  initLightDismiss($('settings-dialog'));
  initLightDismiss($('market-dialog'));
  $('json-input').setAttribute('aria-invalid', 'false');
  renderHeader();
  loadBootstrap().catch((error) => toast(`Model unavailable: ${error.message}`));
  setInterval(refreshHealth, 30000);
  setInterval(renderHeader, 60000);
}

window.addEventListener('DOMContentLoaded', init);
