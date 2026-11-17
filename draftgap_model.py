#!/usr/bin/env python3
"""Reproducible reimplementation of DraftGap's League of Legends draft model.

The model is an additive Elo/logit model over three components:

    total = ally champion base ratings
          + ally duo synergy corrections
          + cross-team matchup corrections
          - enemy champion base ratings
          - enemy duo synergy corrections

    winrate = 1 / (1 + 10 ** (-total / 400))

Every component is shrunk with pseudo-games (the "DraftGap risk level").  The
current champion sample is shrunk toward its 30-day role winrate; pair samples
are shrunk toward the no-synergy expectation, and the time buckets toward a
50% baseline.  See README.md for the evidence and fidelity notes.

The module has no third-party dependencies.  It can be used as a library, as a
CLI, or as a small local HTTP service with a one-click prediction page.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import math
import os
import re
import socket
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Model constants (transcribed from the public DraftGap bundle)
# ---------------------------------------------------------------------------

ROLES = (0, 1, 2, 3, 4)
ROLE_NAMES = {
    0: "Top",
    1: "Jungle",
    2: "Middle",
    3: "Bottom",
    4: "Support",
}
ROLE_NAMES_ZH = {
    0: "上单",
    1: "打野",
    2: "中单",
    3: "下路",
    4: "辅助",
}
# Draft model risk levels -> prior pseudo-games.
RISK_PRIOR = {
    "very-low": 3000,
    "low": 2000,
    "medium": 1000,
    "high": 500,
    "very-high": 250,
}
# The Builds (beta) model uses 3000/2000/1000/750/500, but that model is
# Lolalytics-backed and does not participate in draft winrate calculations.

DATASET_BASE = "https://bucket.draftgap.com/datasets/v5"
DATASET_NAMES = ("current-patch.json", "30-days.json")
MODEL_BUNDLE = "https://draftgap.com/assets/index-DS2QEuLT.js"
MODEL_BUNDLE_SHA256 = (
    "1ef2909b7cb59a7b2e1c9398b62902a31bc74b2a296686f92ff1a9a2679ca3a1"
)
DEFAULT_MIN_GAMES = 1000  # weekly games, used only by suggestions
DEFAULT_SUGGESTIONS = 0

ZERO = (0.0, 0.0)

ROLE_ALIASES = {
    "0": 0,
    "top": 0,
    "toplane": 0,
    "top lane": 0,
    "上单": 0,
    "上路": 0,
    "1": 1,
    "jungle": 1,
    "jg": 1,
    "jungler": 1,
    "打野": 1,
    "2": 2,
    "mid": 2,
    "middle": 2,
    "midlane": 2,
    "mid lane": 2,
    "中单": 2,
    "中路": 2,
    "3": 3,
    "bottom": 3,
    "bot": 3,
    "adc": 3,
    "下路": 3,
    "4": 4,
    "support": 4,
    "sup": 4,
    "utility": 4,
    "辅助": 4,
}

TEAM_KEYS = {
    "allies": ("allies", "ally", "allyTeam", "blue", "blueTeam", "team1"),
    "opponents": (
        "opponents",
        "opponent",
        "opponentTeam",
        "red",
        "redTeam",
        "team2",
    ),
}

CONFIG_KEYS = (
    "riskLevel",
    "risk",
    "ignoreChampionWinrates",
    "minGames",
    "suggestions",
    "scaling",
    "includeTables",
    "priorGames",
)

# Config keys the web client also sends but that do not affect draft analysis.
IGNORED_CONFIG_KEYS = {
    "showFavouritesAtTop",
    "banPlacement",
    "unownedPlacement",
    "showAdvancedWinrates",
    "language",
    "defaultStatsSite",
    "enableBetaFeatures",
    "disableLeagueClientIntegration",
}

# Known DraftGap aliases that are not derived mechanically from id/name.
EXTRA_CHAMPION_ALIASES = {
    "57": ("maokai", "扭曲树精"),
    "62": ("wukong", "monkeyking", "齐天大圣"),
    "145": ("kaisa", "虚空之女"),
}


class InputError(ValueError):
    """The caller's draft/config is malformed or ambiguous."""


# ---------------------------------------------------------------------------
# Numeric helpers.  These mirror the JavaScript semantics deliberately.
# ---------------------------------------------------------------------------


def winrate_from_rating(rating: float) -> float:
    """Be(e) = 1 / (1 + 10^(-e/400))."""
    if math.isnan(rating):
        return float("nan")
    if rating == float("inf"):
        return 1.0
    if rating == float("-inf"):
        return 0.0
    try:
        return 1.0 / (1.0 + math.pow(10.0, -rating / 400.0))
    except OverflowError:
        # -rating / 400 exceeded the double exponent range.
        return 0.0 if rating > 0 else 1.0


def rating_from_winrate(winrate: float) -> float:
    """Ke(e) = -400 * log10(1/e - 1)."""
    if math.isnan(winrate):
        return float("nan")
    if winrate <= 0.0:
        return float("-inf")
    if winrate >= 1.0:
        return float("inf")
    return -400.0 * math.log10(1.0 / winrate - 1.0)


def _to_fixed(number: float, digits: int = 2) -> str:
    """Approximate JavaScript Number.prototype.toFixed for finite positives."""
    if not math.isfinite(number):
        return "NaN"
    try:
        quantum = Decimal(1).scaleb(-digits)
        return str(Decimal(number).quantize(quantum, rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, OverflowError):
        return repr(number)


def percent_text(winrate: float) -> str:
    """Dl(rating) = (100 * W(rating)).toFixed(2)."""
    if not math.isfinite(winrate):
        return "NaN"
    return _to_fixed(winrate * 100.0, 2)


def rating_text(rating: float) -> str:
    return percent_text(winrate_from_rating(rating))


def _num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else default
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _stat_pair(value: Any) -> tuple[float, float]:
    if isinstance(value, Mapping):
        return (_num(value.get("games")), _num(value.get("wins")))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (_num(value[0]), _num(value[1]))
    return ZERO


def _base_winrate(stat: tuple[float, float]) -> float:
    games, wins = stat
    return 0.5 if games == 0 else wins / games


def _normalize_alias(text: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]+", "", text.lower())


def _normalize_role_key(text: str) -> str:
    value = str(text).strip().lower()
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"\s+", " ", value)
    return value


def _role_from_json(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value in ROLES else None
    if isinstance(value, float) and value.is_integer():
        candidate = int(value)
        return candidate if candidate in ROLES else None
    if isinstance(value, str):
        if value.strip() == "":
            return None
        try:
            candidate = int(value)
        except ValueError:
            return None
        return candidate if candidate in ROLES else None
    return None


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


class RoleStats:
    __slots__ = ("games", "wins", "matchup", "synergy", "stats_by_time", "damage")

    def __init__(
        self,
        games: float,
        wins: float,
        matchup: dict[int, dict[str, tuple[float, float]]],
        synergy: dict[int, dict[str, tuple[float, float]]],
        stats_by_time: list[tuple[float, float]],
        damage: tuple[float, float, float] | None = None,
    ) -> None:
        self.games = games
        self.wins = wins
        self.matchup = matchup
        self.synergy = synergy
        self.stats_by_time = stats_by_time
        self.damage = damage


class ChampionInfo:
    __slots__ = ("key", "champion_id", "name", "name_zh", "roles")

    def __init__(
        self,
        key: str,
        champion_id: str | None,
        name: str | None,
        name_zh: str | None,
        roles: dict[int, RoleStats],
    ) -> None:
        self.key = key
        self.champion_id = champion_id or key
        self.name = name or champion_id or key
        self.name_zh = name_zh
        self.roles = roles


class Dataset:
    """A compacted DraftGap v5 dataset."""

    __slots__ = ("path", "label", "version", "date", "champions")

    def __init__(self, path: str, label: str) -> None:
        self.path = path
        self.label = label
        with open(path, "r", encoding="utf-8") as handle:
            try:
                raw = json.load(handle)
            except json.JSONDecodeError as error:
                raise InputError(f"{path}: invalid JSON: {error}") from error
        if not isinstance(raw, dict) or not isinstance(raw.get("championData"), dict):
            raise InputError(f"{path}: not a DraftGap v5 dataset (missing championData)")

        self.version = raw.get("version")
        self.date = raw.get("date")
        champions: dict[str, ChampionInfo] = {}
        champion_raw = raw["championData"]

        for raw_key, raw_champion in champion_raw.items():
            if not isinstance(raw_champion, dict):
                continue
            key = str(raw_key)
            i18n = raw_champion.get("i18n")
            name_zh = None
            if isinstance(i18n, Mapping):
                zh = i18n.get("zh_CN")
                if isinstance(zh, Mapping):
                    name_zh = zh.get("name")
            roles: dict[int, RoleStats] = {}
            for raw_role, raw_stats in (raw_champion.get("statsByRole") or {}).items():
                role = _role_from_json(raw_role)
                if role is None or not isinstance(raw_stats, dict):
                    continue

                matchup: dict[int, dict[str, tuple[float, float]]] = {}
                for raw_enemy_role, table in (raw_stats.get("matchup") or {}).items():
                    enemy_role = _role_from_json(raw_enemy_role)
                    if enemy_role is None or not isinstance(table, dict):
                        continue
                    # Compact in place: the parsed object is not needed again.
                    for champion_key in table:
                        table[champion_key] = _stat_pair(table[champion_key])
                    matchup[enemy_role] = table

                synergy: dict[int, dict[str, tuple[float, float]]] = {}
                for raw_ally_role, table in (raw_stats.get("synergy") or {}).items():
                    ally_role = _role_from_json(raw_ally_role)
                    if ally_role is None or not isinstance(table, dict):
                        continue
                    for champion_key in table:
                        table[champion_key] = _stat_pair(table[champion_key])
                    synergy[ally_role] = table

                stats_by_time: list[tuple[float, float]] = []
                for bucket in raw_stats.get("statsByTime") or []:
                    stats_by_time.append(_stat_pair(bucket))

                damage = None
                raw_damage = raw_stats.get("damageProfile")
                if isinstance(raw_damage, Mapping):
                    damage = (
                        _num(raw_damage.get("physical")),
                        _num(raw_damage.get("magic")),
                        _num(raw_damage.get("true")),
                    )

                roles[role] = RoleStats(
                    _num(raw_stats.get("games")),
                    _num(raw_stats.get("wins")),
                    matchup,
                    synergy,
                    stats_by_time,
                    damage,
                )
            champions[key] = ChampionInfo(
                key,
                str(raw_champion.get("id") or key),
                str(raw_champion.get("name") or raw_champion.get("id") or key),
                str(name_zh) if name_zh else None,
                roles,
            )

        if not champions:
            raise InputError(f"{path}: dataset has no champions")
        self.champions = champions

    def champion_key_order(self) -> list[str]:
        """JS Object.keys order: integer-like keys ascending, then insertion."""
        numeric = [key for key in self.champions if key.isdigit()]
        other = [key for key in self.champions if not key.isdigit()]
        return sorted(numeric, key=int) + other


# ---------------------------------------------------------------------------
# Draft input parsing
# ---------------------------------------------------------------------------


class TeamEntry:
    __slots__ = ("key", "role")

    def __init__(self, key: str, role: int | None) -> None:
        self.key = key
        self.role = role


class RoleAssignment:
    __slots__ = ("team_map", "role_probabilities", "composition_count")

    def __init__(
        self,
        team_map: dict[int, str],
        role_probabilities: dict[str, dict[int, float]],
        composition_count: int,
    ) -> None:
        self.team_map = team_map
        self.role_probabilities = role_probabilities
        self.composition_count = composition_count


def _first_present(
    payload: Mapping[str, Any], names: Sequence[str]
) -> tuple[str | None, Any]:
    for name in names:
        if name in payload:
            return name, payload[name]
    return None, None


def _parse_role(value: Any, *, what: str) -> int | None:
    if value is None:
        return None
    direct = _role_from_json(value)
    if direct is not None:
        return direct
    if isinstance(value, str):
        normalized = _normalize_role_key(value)
        if normalized in ("", "fill", "any", "unknown", "?", "未知"):
            return None
        if normalized in ROLE_ALIASES:
            return ROLE_ALIASES[normalized]
        # Try "0 - top" and similar decorated values.
        for alias, role in ROLE_ALIASES.items():
            if normalized == alias or normalized.startswith(alias + " "):
                return role
    raise InputError(
        f"{what}: unknown role {value!r}; use top/jungle/middle/bottom/support or 0-4"
    )


def _parse_champion_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        for field in (
            "championKey",
            "championId",
            "champion",
            "championName",
            "key",
            "id",
            "name",
        ):
            if field in value and value[field] not in (None, ""):
                return value[field]
        raise InputError(f"team entry has no champion field: {value!r}")
    return value


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class DraftModel:
    def __init__(self, current: Dataset, thirty: Dataset) -> None:
        self.current = current
        self.thirty = thirty
        self.champions: dict[str, ChampionInfo] = dict(current.champions)
        for key, champion in thirty.champions.items():
            self.champions.setdefault(key, champion)

        self.aliases: dict[str, str] = {}
        self.ambiguous_aliases: dict[str, set[str]] = defaultdict(set)
        for key in self._champion_order():
            champion = self.champions[key]
            values: list[str] = [key, champion.champion_id, champion.name]
            if champion.name_zh:
                values.append(champion.name_zh)
            values.extend(EXTRA_CHAMPION_ALIASES.get(key, ()))
            for value in values:
                if not value:
                    continue
                self._add_alias(str(value), key)
                self._add_alias(_normalize_alias(str(value)), key)
            # "Nunu & Willump" also answers to "Nunu".
            if "&" in champion.name:
                first = champion.name.split("&", 1)[0].strip()
                if len(first) >= 3:
                    self._add_alias(first, key)
                    self._add_alias(_normalize_alias(first), key)

    def _add_alias(self, alias: str, key: str) -> None:
        alias = alias.strip().lower()
        if not alias:
            return
        if alias in self.ambiguous_aliases:
            self.ambiguous_aliases[alias].add(key)
            return
        previous = self.aliases.get(alias)
        if previous is None:
            self.aliases[alias] = key
        elif previous != key:
            self.aliases.pop(alias, None)
            self.ambiguous_aliases[alias].update((previous, key))

    def _champion_order(self) -> list[str]:
        keys = self.current.champion_key_order()
        seen = set(keys)
        for key in self.thirty.champion_key_order():
            if key not in seen:
                keys.append(key)
                seen.add(key)
        return keys

    def resolve_champion(self, value: Any) -> str:
        original = value
        if isinstance(value, bool):
            raise InputError(f"invalid champion value {value!r}")
        if isinstance(value, int):
            key = str(value)
        elif isinstance(value, float) and value.is_integer():
            key = str(int(value))
        elif isinstance(value, str):
            text = value.strip()
            if text in self.champions:
                key = text
            else:
                key = self.aliases.get(text.lower()) or self.aliases.get(
                    _normalize_alias(text)
                )
                if key is None and text.lower() in self.ambiguous_aliases:
                    candidates = ", ".join(
                        sorted(self.ambiguous_aliases[text.lower()], key=int)
                    )
                    raise InputError(
                        f"ambiguous champion {original!r}; candidates: {candidates}"
                    )
        else:
            raise InputError(f"invalid champion value {original!r}")

        if key is None or key not in self.champions:
            text = str(original)
            close = self._close_aliases(text)
            hint = f"; did you mean {', '.join(close)}?" if close else ""
            raise InputError(f"unknown champion {original!r}{hint}")
        return key

    def _close_aliases(self, text: str) -> list[str]:
        import difflib

        needle = text.lower()
        normalized = _normalize_alias(text)
        pool = set(self.aliases)
        pool.update(self.ambiguous_aliases)
        matches = difflib.get_close_matches(needle, sorted(pool), n=3, cutoff=0.6)
        if not matches and normalized:
            matches = difflib.get_close_matches(
                normalized, sorted(pool), n=3, cutoff=0.6
            )
        seen: list[str] = []
        for match in matches:
            key = self.aliases.get(match)
            if key is None:
                continue
            label = self.champions[key].name
            if label not in seen:
                seen.append(label)
        return seen

    # -- input -------------------------------------------------------------

    def parse_team(
        self, payload: Mapping[str, Any], side: str, warnings: list[str]
    ) -> list[TeamEntry]:
        names = TEAM_KEYS[side]
        present = [name for name in names if name in payload]
        if len(present) > 1:
            warnings.append(
                f"{side}: multiple team keys present ({', '.join(present)}); "
                f"using {present[0]}"
            )
        found_name, raw = _first_present(payload, names)
        if found_name is None:
            return []
        if raw is None:
            return []
        if isinstance(raw, Mapping):
            items: list[tuple[Any, Any]] = list(raw.items())
        elif isinstance(raw, (list, tuple)):
            items = [(None, item) for item in raw]
        else:
            raise InputError(
                f"{side}: expected an array of champions or a role->champion object"
            )

        entries: list[TeamEntry] = []
        seen_keys: dict[str, int] = {}
        seen_roles: dict[int, str] = {}
        for index, (mapping_role, item) in enumerate(items):
            role_from_mapping = (
                _parse_role(mapping_role, what=f"{side}[{mapping_role!r}]")
                if mapping_role is not None
                else None
            )
            role_from_item = None
            champion_value = item
            if isinstance(item, Mapping):
                for field in ("role", "position", "lane", "teamPosition"):
                    if field in item and item[field] not in (None, ""):
                        role_from_item = _parse_role(
                            item[field], what=f"{side}[{index}].{field}"
                        )
                        break
                champion_value = _parse_champion_value(item)
                while isinstance(champion_value, Mapping):
                    champion_value = _parse_champion_value(champion_value)
            elif item is None or (isinstance(item, str) and not item.strip()):
                raise InputError(f"{side}[{index}]: empty champion")

            key = self.resolve_champion(champion_value)
            if role_from_mapping is not None and role_from_item is not None:
                if role_from_mapping != role_from_item:
                    raise InputError(
                        f"{side}[{index}]: conflicting roles "
                        f"{role_from_mapping} and {role_from_item}"
                    )
            role = (
                role_from_mapping
                if role_from_mapping is not None
                else role_from_item
            )
            if key in seen_keys:
                raise InputError(
                    f"{side}: champion {self.champions[key].name} appears twice"
                )
            if role is not None and role in seen_roles:
                raise InputError(
                    f"{side}: role {ROLE_NAMES[role]} is assigned to both "
                    f"{seen_roles[role]} and {self.champions[key].name}"
                )
            seen_keys[key] = index
            if role is not None:
                seen_roles[role] = self.champions[key].name
            entries.append(TeamEntry(key, role))

        if len(entries) > 5:
            raise InputError(f"{side}: at most 5 champions are allowed")
        return entries

    def _compositions(
        self,
        assigned: dict[int, str],
        unknown: list[TeamEntry],
        index: int = 0,
        weight: float = 1.0,
    ) -> list[tuple[dict[int, str], float]]:
        if index >= len(unknown):
            return [(dict(assigned), weight)]
        entry = unknown[index]
        champion = self.champions[entry.key]
        total_games = sum(
            champion.roles[role].games if role in champion.roles else 0.0
            for role in ROLES
        )
        results: list[tuple[dict[int, str], float]] = []
        for role in ROLES:  # JS Object.entries(statsByRole) order: 0..4
            if role in assigned or role not in champion.roles:
                continue
            if total_games > 0:
                role_weight = champion.roles[role].games / total_games
            else:
                role_weight = 1.0 / len(ROLES)
            next_assigned = dict(assigned)
            next_assigned[role] = entry.key
            results.extend(
                self._compositions(
                    next_assigned, unknown, index + 1, weight * role_weight
                )
            )
        return results

    def assign_roles(
        self, entries: list[TeamEntry], side: str, warnings: list[str]
    ) -> RoleAssignment:
        explicit: dict[int, str] = {}
        unknown: list[TeamEntry] = []
        for entry in entries:
            if entry.role is None:
                unknown.append(entry)
            else:
                explicit[entry.role] = entry.key

        compositions = self._compositions(explicit, unknown)
        if not compositions:
            raise InputError(
                f"{side}: cannot assign a role to every champion with the "
                "available role data"
            )
        compositions.sort(key=lambda item: item[1], reverse=True)
        team_map, top_weight = compositions[0]
        if len(team_map) != len(entries):
            raise InputError(
                f"{side}: role assignment produced {len(team_map)} roles for "
                f"{len(entries)} champions"
            )

        total_weight = sum(weight for _, weight in compositions)
        probabilities: dict[str, dict[int, float]] = {
            entry.key: {} for entry in entries
        }
        if total_weight > 0:
            for composition, weight in compositions:
                share = weight / total_weight
                for role, key in composition.items():
                    probabilities[key][role] = (
                        probabilities[key].get(role, 0.0) + share
                    )
        else:
            # Degenerate data (every role has zero games): stay deterministic.
            uniform = 1.0 / len(compositions)
            for composition, _ in compositions:
                for role, key in composition.items():
                    probabilities[key][role] = (
                        probabilities[key].get(role, 0.0) + uniform
                    )
            warnings.append(
                f"{side}: role data has zero games; role probabilities are uniform"
            )
        if len(compositions) > 1 and top_weight == compositions[1][1]:
            warnings.append(
                f"{side}: multiple role assignments tie on weight; the first "
                "DraftGap order was used"
            )
        return RoleAssignment(team_map, probabilities, len(compositions))

    # -- model primitives --------------------------------------------------

    def _hs(self, role: int, key: str, prior: float) -> dict[str, Any]:
        base = self._team_stat(self.current, key, role)
        thirty = self._team_stat(self.thirty, key, role)
        center = 0.5 if thirty[0] == 0 else thirty[1] / thirty[0]
        games = base[0] + prior
        wins = base[1] + prior * center
        return {
            "role": role,
            "championKey": key,
            "rating": rating_from_winrate(wins / games),
            "wins": base[1],
            "games": base[0],
        }

    def _xd(
        self,
        team_map: Mapping[int, str],
        prior: float,
        ignore_champion_winrates: bool,
    ) -> dict[str, Any]:
        if ignore_champion_winrates:
            return {"championResults": [], "totalRating": 0.0}
        results = []
        total = 0.0
        for role, key in team_map.items():
            result = self._hs(role, key, prior)
            results.append(result)
            total += result["rating"]
        return {"championResults": results, "totalRating": total}

    def _duo(
        self, team_map: Mapping[int, str], prior: float, warnings: list[str]
    ) -> dict[str, Any]:
        entries = sorted(team_map.items(), key=lambda item: item[0])
        results = []
        total = 0.0
        for index, (role_a, key_a) in enumerate(entries):
            for role_b, key_b in entries[index + 1 :]:
                stat_a = self._team_stat(self.thirty, key_a, role_a)
                stat_b = self._team_stat(self.thirty, key_b, role_b)
                base_rating = rating_from_winrate(
                    _base_winrate(stat_a)
                ) + rating_from_winrate(_base_winrate(stat_b))
                expected = winrate_from_rating(base_rating)
                duo_a = self._pair_stat(
                    self.thirty, key_a, role_a, False, role_b, key_b
                )
                duo_b = self._pair_stat(
                    self.thirty, key_b, role_b, False, role_a, key_a
                )
                games = (duo_a[0] + duo_b[0]) / 2.0
                wins = (duo_a[1] + duo_b[1]) / 2.0
                if games > 0:
                    observed = (wins + prior * expected) / (games + prior)
                    rating = rating_from_winrate(observed) - base_rating
                else:
                    rating = 0.0
                    warnings.append(
                        "no duo sample for "
                        f"{self.champions[key_a].name}/{self.champions[key_b].name}; "
                        "treated as neutral"
                    )
                results.append(
                    {
                        "roleA": role_a,
                        "championKeyA": key_a,
                        "roleB": role_b,
                        "championKeyB": key_b,
                        "rating": rating,
                        "games": games,
                    }
                )
                total += rating
        return {"duoResults": results, "totalRating": total}

    def _ks(
        self,
        ally_map: Mapping[int, str],
        enemy_map: Mapping[int, str],
        prior: float,
        warnings: list[str],
    ) -> dict[str, Any]:
        results = []
        total = 0.0
        for role_a, key_a in ally_map.items():
            for role_b, key_b in enemy_map.items():
                stat_a = self._team_stat(self.thirty, key_a, role_a)
                stat_b = self._team_stat(self.thirty, key_b, role_b)
                base_rating = rating_from_winrate(
                    _base_winrate(stat_a)
                ) - rating_from_winrate(_base_winrate(stat_b))
                expected = winrate_from_rating(base_rating)
                game_a = self._pair_stat(
                    self.thirty, key_a, role_a, True, role_b, key_b
                )
                game_b = self._pair_stat(
                    self.thirty, key_b, role_b, True, role_a, key_a
                )
                enemy_losses = game_b[0] - game_b[1]
                wins = (game_a[1] + enemy_losses) / 2.0
                games = (game_a[0] + game_b[0]) / 2.0
                if games > 0:
                    observed = (wins + prior * expected) / (games + prior)
                    rating = rating_from_winrate(observed) - base_rating
                else:
                    rating = 0.0
                    warnings.append(
                        "no matchup sample for "
                        f"{self.champions[key_a].name} vs "
                        f"{self.champions[key_b].name}; treated as neutral"
                    )
                results.append(
                    {
                        "roleA": role_a,
                        "championKeyA": key_a,
                        "roleB": role_b,
                        "championKeyB": key_b,
                        "rating": rating,
                        "games": games,
                    }
                )
                total += rating
        return {"matchupResults": results, "totalRating": total}

    @staticmethod
    def _team_stat(
        dataset: Dataset, key: str, role: int
    ) -> tuple[float, float]:
        champion = dataset.champions.get(key)
        if champion is None:
            return ZERO
        stats = champion.roles.get(role)
        if stats is None:
            return ZERO
        return (stats.games, stats.wins)

    @staticmethod
    def _pair_stat(
        dataset: Dataset,
        key: str,
        role: int,
        is_matchup: bool,
        other_role: int,
        other_key: str,
    ) -> tuple[float, float]:
        champion = dataset.champions.get(key)
        if champion is None:
            return ZERO
        stats = champion.roles.get(role)
        if stats is None:
            return ZERO
        table = (stats.matchup if is_matchup else stats.synergy).get(other_role)
        if not table:
            return ZERO
        return table.get(other_key, ZERO)

    def _il(
        self,
        ally_map: Mapping[int, str],
        enemy_map: Mapping[int, str],
        prior: float,
        ignore_champion_winrates: bool,
        warnings: list[str],
    ) -> dict[str, Any]:
        ally_base = self._xd(ally_map, prior, ignore_champion_winrates)
        enemy_base = self._xd(enemy_map, prior, ignore_champion_winrates)
        ally_duo = self._duo(ally_map, prior, warnings)
        enemy_duo = self._duo(enemy_map, prior, warnings)
        matchup = self._ks(ally_map, enemy_map, prior, warnings)
        total = (
            ally_base["totalRating"]
            + ally_duo["totalRating"]
            + matchup["totalRating"]
            - enemy_base["totalRating"]
            - enemy_duo["totalRating"]
        )
        return {
            "allyChampionRating": ally_base,
            "enemyChampionRating": enemy_base,
            "allyDuoRating": ally_duo,
            "enemyDuoRating": enemy_duo,
            "matchupRating": matchup,
            "totalRating": total,
            "winrate": winrate_from_rating(total),
        }

    # -- scaling -----------------------------------------------------------

    def _scaling(
        self, team_map: Mapping[int, str], prior: float, warnings: list[str]
    ) -> dict[str, Any]:
        data: list[RoleStats | None] = []
        for role, key in team_map.items():
            champion = self.thirty.champions.get(key)
            stats = champion.roles.get(role) if champion else None
            if stats is None:
                warnings.append(
                    f"scaling: no 30-day role data for "
                    f"{self.champions[key].name} {ROLE_NAMES[role]}"
                )
            data.append(stats)

        by_time = []
        for time_index, label in enumerate(("0-20", "20-25", "25-30", "30-35", "35+")):
            champion_results = []
            total = 0.0
            for (role, key), stats in zip(team_map.items(), data):
                if stats is None:
                    rating = 0.0
                else:
                    # wf(): the champion's own games are shrunk toward 50%,
                    # then each time bucket is shrunk toward that baseline.
                    base = (stats.wins + prior * 0.5) / (stats.games + prior)
                    base_rating = rating_from_winrate(base)
                    bucket = (
                        stats.stats_by_time[time_index]
                        if time_index < len(stats.stats_by_time)
                        else ZERO
                    )
                    games = bucket[0] + prior
                    wins = bucket[1] + prior * base
                    rating = rating_from_winrate(wins / games) - base_rating
                champion_results.append(
                    {"championKey": key, "role": role, "rating": rating}
                )
                total += rating
            bucket_winrate = winrate_from_rating(total)
            by_time.append(
                {
                    "label": label,
                    "championResults": champion_results,
                    "totalRating": total,
                    "winrate": bucket_winrate,
                    "winrateText": percent_text(bucket_winrate),
                }
            )
        return {"ratingByTime": by_time}

    # -- suggestions -------------------------------------------------------

    def _suggestions(
        self,
        team_map: Mapping[int, str],
        enemy_map: Mapping[int, str],
        prior: float,
        ignore_champion_winrates: bool,
        min_games: float,
        limit: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        available_roles = [role for role in ROLES if role not in team_map]
        unavailable = set(enemy_map.values()) | set(team_map.values())
        results: list[dict[str, Any]] = []
        warnings: list[str] = []
        for key in self.current.champion_key_order():
            if key in unavailable:
                continue
            champion = self.champions[key]
            for role in available_roles:
                games = self._team_stat(self.thirty, key, role)[0]
                if games / 30.0 * 7.0 < min_games:
                    continue
                simulated = dict(team_map)
                simulated[role] = key
                draft_result = self._il(
                    simulated,
                    enemy_map,
                    prior,
                    ignore_champion_winrates,
                    warnings,
                )
                cards = self._cards(draft_result)
                results.append(
                    {
                        "championKey": key,
                        "championId": champion.champion_id,
                        "name": champion.name,
                        "nameZh": champion.name_zh,
                        "role": role,
                        "roleName": ROLE_NAMES[role],
                        "roleNameZh": ROLE_NAMES_ZH[role],
                        "winrate": cards["winrate"],
                        "winrateText": cards["winrateText"],
                        "totalRating": cards["totalRating"],
                        "championWinrateText": cards["championWinrateText"],
                        "matchupWinrateText": cards["matchupWinrateText"],
                        "duoWinrateText": cards["duoWinrateText"],
                    }
                )
        results.sort(key=lambda item: item["winrate"], reverse=True)
        return results[:limit]

    # -- public API --------------------------------------------------------

    def analyze(
        self, payload: Mapping[str, Any], config_override: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise InputError("request body must be a JSON object")
        warnings: list[str] = []
        config = self._parse_config(payload, config_override, warnings)

        allies = self.parse_team(payload, "allies", warnings)
        opponents = self.parse_team(payload, "opponents", warnings)
        if not allies and not opponents:
            warnings.append("both teams are empty; the prediction is the 50% prior")

        ally_keys = {entry.key for entry in allies}
        opponent_keys = {entry.key for entry in opponents}
        overlap = ally_keys & opponent_keys
        if overlap:
            names = ", ".join(self.champions[key].name for key in sorted(overlap))
            raise InputError(f"champion appears on both teams: {names}")

        bans = self._parse_bans(payload, warnings)
        banned_keys = {ban["championKey"] for ban in bans}
        for key in sorted(banned_keys & (ally_keys | opponent_keys)):
            warnings.append(
                f"{self.champions[key].name} is both banned and in a team"
            )

        ally_assignment = self.assign_roles(allies, "allies", warnings)
        opponent_assignment = self.assign_roles(opponents, "opponents", warnings)

        ally_analysis = self._il(
            ally_assignment.team_map,
            opponent_assignment.team_map,
            config["priorGames"],
            config["ignoreChampionWinrates"],
            warnings,
        )
        opponent_analysis = self._il(
            opponent_assignment.team_map,
            ally_assignment.team_map,
            config["priorGames"],
            config["ignoreChampionWinrates"],
            warnings,
        )

        ally_cards = self._cards(ally_analysis)
        opponent_cards = self._cards(opponent_analysis)
        ally_breakdown = self._breakdown(ally_analysis, ally_assignment.team_map)
        opponent_breakdown = self._breakdown(
            opponent_analysis, opponent_assignment.team_map
        )

        suggestions: dict[str, list[dict[str, Any]]] = {
            "allies": [],
            "opponents": [],
        }
        if config["suggestions"] > 0:
            suggestions["allies"] = self._suggestions(
                ally_assignment.team_map,
                opponent_assignment.team_map,
                config["priorGames"],
                config["ignoreChampionWinrates"],
                config["minGames"],
                config["suggestions"],
            )
            suggestions["opponents"] = self._suggestions(
                opponent_assignment.team_map,
                ally_assignment.team_map,
                config["priorGames"],
                config["ignoreChampionWinrates"],
                config["minGames"],
                config["suggestions"],
            )

        result: dict[str, Any] = {
            "model": {
                "name": "draftgap-draft-model",
                "implementation": "python",
                "sourceBundle": MODEL_BUNDLE,
                "sourceBundleSha256": MODEL_BUNDLE_SHA256,
                "datasetBase": DATASET_BASE,
                "currentPatch": {
                    "version": self.current.version,
                    "date": self.current.date,
                    "champions": len(self.current.champions),
                },
                "thirtyDay": {
                    "version": self.thirty.version,
                    "date": self.thirty.date,
                    "champions": len(self.thirty.champions),
                },
                "config": {
                    "riskLevel": config["riskLevel"],
                    "priorGames": config["priorGames"],
                    "ignoreChampionWinrates": config["ignoreChampionWinrates"],
                    "minGames": config["minGames"],
                    "suggestions": config["suggestions"],
                },
            },
            "draft": {
                "allies": self._team_json(
                    allies, ally_assignment, ally_breakdown
                ),
                "opponents": self._team_json(
                    opponents, opponent_assignment, opponent_breakdown
                ),
                "roleAssignmentsEvaluated": {
                    "allies": ally_assignment.composition_count,
                    "opponents": opponent_assignment.composition_count,
                },
                "bans": bans,
            },
            "prediction": {
                "allyWinrate": ally_cards["winrate"],
                "allyWinrateText": ally_cards["winrateText"],
                "opponentWinrate": opponent_cards["winrate"],
                "opponentWinrateText": opponent_cards["winrateText"],
                "ally": ally_cards,
                "opponent": opponent_cards,
            },
            "breakdown": {
                "allies": ally_breakdown,
                "opponents": opponent_breakdown,
            },
            "matchups": (
                self._matchup_json(ally_analysis)
                if config["includeTables"]
                else None
            ),
            "duos": (
                {
                    "allies": self._duo_json(ally_analysis),
                    "opponents": self._duo_json(opponent_analysis),
                }
                if config["includeTables"]
                else None
            ),
            "scaling": (
                {
                    "allies": self._scaling(
                        ally_assignment.team_map, config["priorGames"], warnings
                    )["ratingByTime"],
                    "opponents": self._scaling(
                        opponent_assignment.team_map, config["priorGames"], warnings
                    )["ratingByTime"],
                }
                if config["scaling"]
                else None
            ),
            "suggestions": suggestions,
            "warnings": _unique(warnings),
        }

        if not config["includeTables"]:
            for key in ("matchups", "duos"):
                result.pop(key, None)
        return _sanitize(result)

    def ui_payload(self, prior_games: float = 1000.0) -> dict[str, Any]:
        """Metadata used by the draft board: champion-role winrates and damage."""
        champions: list[dict[str, Any]] = []
        for key in self._champion_order():
            info = self.champions[key]
            role_entries: list[dict[str, Any]] = []
            for role in ROLES:
                stats = info.roles.get(role)
                if stats is None or stats.games <= 0:
                    continue
                shrunk = self._hs(role, key, prior_games)
                winrate = winrate_from_rating(shrunk["rating"])
                damage = None
                if stats.damage is not None:
                    damage = {
                        "physical": stats.damage[0],
                        "magic": stats.damage[1],
                        "true": stats.damage[2],
                    }
                role_entries.append(
                    {
                        "role": role,
                        "roleName": ROLE_NAMES[role],
                        "roleNameZh": ROLE_NAMES_ZH[role],
                        "games": stats.games,
                        "wins": stats.wins,
                        "winrate": winrate,
                        "winrateText": percent_text(winrate),
                        "damage": damage,
                    }
                )
            champions.append(
                {
                    "key": key,
                    "id": info.champion_id,
                    "name": info.name,
                    "nameZh": info.name_zh,
                    "roles": role_entries,
                }
            )
        return {
            "dataset": {
                "version": self.current.version,
                "date": self.current.date,
                "champions": len(self.current.champions),
                "thirtyDayDate": self.thirty.date,
            },
            "roles": [
                {
                    "role": role,
                    "name": ROLE_NAMES[role],
                    "nameZh": ROLE_NAMES_ZH[role],
                }
                for role in ROLES
            ],
            "priorGames": prior_games,
            "champions": champions,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    def _parse_config(
        self,
        payload: Mapping[str, Any],
        config_override: Mapping[str, Any] | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        raw: dict[str, Any] = {}
        nested = payload.get("config")
        if isinstance(nested, Mapping):
            raw.update(nested)
        elif nested is not None:
            raise InputError("config must be an object")
        for key in CONFIG_KEYS:
            if key in payload:
                raw[key] = payload[key]
        if config_override:
            raw.update(config_override)

        for key in list(raw):
            normalized = _normalize_config_key(key)
            if normalized != key:
                value = raw.pop(key)
                if normalized not in raw:
                    raw[normalized] = value
                elif normalized == "riskLevel" and key == "risk":
                    # An explicit riskLevel wins over the short alias.
                    pass
                else:
                    raw[normalized] = value

        for key in list(raw):
            if key not in CONFIG_KEYS and key not in IGNORED_CONFIG_KEYS:
                warnings.append(f"ignored unknown config key {key!r}")
                raw.pop(key)
            elif key in IGNORED_CONFIG_KEYS:
                raw.pop(key)

        risk_raw = raw.get("riskLevel", raw.get("risk", "medium"))
        if not isinstance(risk_raw, str):
            raise InputError("riskLevel must be a string")
        risk = re.sub(
            r"-+", "-", risk_raw.strip().lower().replace("_", "-").replace(" ", "-")
        )
        if risk not in RISK_PRIOR:
            raise InputError(
                f"unknown riskLevel {risk_raw!r}; use one of "
                + ", ".join(RISK_PRIOR)
            )

        ignore = raw.get("ignoreChampionWinrates", False)
        if not isinstance(ignore, bool):
            if isinstance(ignore, str) and ignore.lower() in ("true", "false"):
                ignore = ignore.lower() == "true"
            else:
                raise InputError("ignoreChampionWinrates must be a boolean")

        min_games = raw.get("minGames", DEFAULT_MIN_GAMES)
        if isinstance(min_games, bool) or not isinstance(min_games, (int, float)):
            raise InputError("minGames must be a number")
        min_games = float(min_games)
        if not math.isfinite(min_games) or min_games < 0:
            raise InputError("minGames must be a finite number >= 0")

        suggestions = raw.get("suggestions", DEFAULT_SUGGESTIONS)
        if isinstance(suggestions, bool) or not isinstance(suggestions, (int, float)):
            raise InputError("suggestions must be an integer")
        if int(suggestions) != suggestions or suggestions < 0:
            raise InputError("suggestions must be a non-negative integer")
        suggestions = min(int(suggestions), 1000)

        scaling = raw.get("scaling", True)
        if not isinstance(scaling, bool):
            raise InputError("scaling must be a boolean")
        include_tables = raw.get("includeTables", True)
        if not isinstance(include_tables, bool):
            raise InputError("includeTables must be a boolean")

        prior_override = raw.get("priorGames")
        if prior_override is None:
            prior = float(RISK_PRIOR[risk])
        else:
            if isinstance(prior_override, bool) or not isinstance(
                prior_override, (int, float)
            ):
                raise InputError("priorGames must be a number")
            prior = float(prior_override)
            if not math.isfinite(prior) or prior <= 0:
                raise InputError("priorGames must be a finite number > 0")

        return {
            "riskLevel": risk,
            "priorGames": prior,
            "ignoreChampionWinrates": ignore,
            "minGames": min_games,
            "suggestions": suggestions,
            "scaling": scaling,
            "includeTables": include_tables,
        }

    def _parse_bans(
        self, payload: Mapping[str, Any], warnings: list[str]
    ) -> list[dict[str, Any]]:
        raw = payload.get("bans")
        if raw is None:
            return []
        if isinstance(raw, Mapping):
            values = list(raw.values())
        elif isinstance(raw, (list, tuple)):
            values = list(raw)
        else:
            raise InputError("bans must be an array")
        bans = []
        seen_bans: set[str] = set()
        for index, value in enumerate(values):
            if value in (None, ""):
                continue
            key = self.resolve_champion(_parse_champion_value(value))
            champion = self.champions[key]
            if key in seen_bans:
                warnings.append(f"duplicate ban: {champion.name}")
            seen_bans.add(key)
            bans.append(
                {
                    "championKey": key,
                    "championId": champion.champion_id,
                    "name": champion.name,
                    "nameZh": champion.name_zh,
                    "inputIndex": index,
                }
            )
        if len(bans) > 10:
            warnings.append("more than 10 bans were provided")
        return bans

    # -- output shaping ----------------------------------------------------

    def _cards(self, analysis: Mapping[str, Any]) -> dict[str, Any]:
        champion_rating = analysis["allyChampionRating"]["totalRating"]
        matchup_rating = analysis["matchupRating"]["totalRating"]
        duo_rating = analysis["allyDuoRating"]["totalRating"]
        total_rating = analysis["totalRating"]
        champion_wr = winrate_from_rating(champion_rating)
        matchup_wr = winrate_from_rating(matchup_rating)
        duo_wr = winrate_from_rating(duo_rating)
        total_wr = winrate_from_rating(total_rating)
        return {
            "championRating": champion_rating,
            "championWinrate": champion_wr,
            "championWinrateText": percent_text(champion_wr),
            "matchupRating": matchup_rating,
            "matchupWinrate": matchup_wr,
            "matchupWinrateText": percent_text(matchup_wr),
            "duoRating": duo_rating,
            "duoWinrate": duo_wr,
            "duoWinrateText": percent_text(duo_wr),
            "totalRating": total_rating,
            "winrate": total_wr,
            "winrateText": percent_text(total_wr),
        }

    def _breakdown(
        self, analysis: Mapping[str, Any], team_map: Mapping[int, str]
    ) -> dict[str, Any]:
        base_by: dict[str, float] = {}
        for result in analysis["allyChampionRating"]["championResults"]:
            base_by[result["championKey"]] = result["rating"]

        duo_by: dict[str, float] = defaultdict(float)
        for result in analysis["allyDuoRating"]["duoResults"]:
            duo_by[result["championKeyA"]] += result["rating"] / 2.0
            duo_by[result["championKeyB"]] += result["rating"] / 2.0

        matchup_by: dict[str, float] = defaultdict(float)
        for result in analysis["matchupRating"]["matchupResults"]:
            matchup_by[result["championKeyA"]] += result["rating"]

        rows = []
        for role, key in sorted(team_map.items(), key=lambda item: item[0]):
            champion = self.champions[key]
            base = base_by.get(key, 0.0)
            matchup = matchup_by.get(key, 0.0)
            duo = duo_by.get(key, 0.0)
            total = base + matchup + duo
            rows.append(
                {
                    "role": role,
                    "roleName": ROLE_NAMES[role],
                    "roleNameZh": ROLE_NAMES_ZH[role],
                    "championKey": key,
                    "championId": champion.champion_id,
                    "name": champion.name,
                    "nameZh": champion.name_zh,
                    "baseRating": base,
                    "baseWinrate": winrate_from_rating(base),
                    "baseText": rating_text(base),
                    "matchupRating": matchup,
                    "matchupWinrate": winrate_from_rating(matchup),
                    "matchupText": rating_text(matchup),
                    "duoRating": duo,
                    "duoWinrate": winrate_from_rating(duo),
                    "duoText": rating_text(duo),
                    "totalRating": total,
                    "totalWinrate": winrate_from_rating(total),
                    "totalText": rating_text(total),
                }
            )
        totals = {
            "baseRating": sum(row["baseRating"] for row in rows),
            "matchupRating": sum(row["matchupRating"] for row in rows),
            "duoRating": sum(row["duoRating"] for row in rows),
            "totalRating": sum(row["totalRating"] for row in rows),
        }
        totals["baseText"] = rating_text(totals["baseRating"])
        totals["matchupText"] = rating_text(totals["matchupRating"])
        totals["duoText"] = rating_text(totals["duoRating"])
        totals["totalText"] = rating_text(totals["totalRating"])
        return {"rows": rows, "totals": totals}

    def _team_json(
        self,
        entries: list[TeamEntry],
        assignment: RoleAssignment,
        breakdown: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        rows_by_key = {
            row["championKey"]: row for row in breakdown.get("rows", [])
        }
        role_by_key = {
            champion_key: role for role, champion_key in assignment.team_map.items()
        }
        output = []
        for entry in entries:
            champion = self.champions[entry.key]
            role = role_by_key[entry.key]
            row = rows_by_key.get(entry.key, {})
            output.append(
                {
                    "championKey": entry.key,
                    "championId": champion.champion_id,
                    "name": champion.name,
                    "nameZh": champion.name_zh,
                    "role": role,
                    "roleName": ROLE_NAMES[role],
                    "roleNameZh": ROLE_NAMES_ZH[role],
                    "roleInferred": entry.role is None,
                    "inputRole": entry.role,
                    "roleProbabilities": [
                        {
                            "role": probability_role,
                            "roleName": ROLE_NAMES[probability_role],
                            "probability": probability,
                        }
                        for probability_role, probability in sorted(
                            assignment.role_probabilities.get(
                                entry.key, {}
                            ).items()
                        )
                    ],
                    "totalRating": row.get("totalRating"),
                    "totalWinrate": row.get("totalWinrate"),
                    "totalText": row.get("totalText"),
                }
            )
        return output

    def _matchup_json(self, analysis: Mapping[str, Any]) -> dict[str, Any]:
        results = []
        same_role = []
        total = 0.0
        same_role_total = 0.0
        for result in analysis["matchupRating"]["matchupResults"]:
            key_a = result["championKeyA"]
            key_b = result["championKeyB"]
            champion_a = self.champions[key_a]
            champion_b = self.champions[key_b]
            rating = result["rating"]
            item = {
                "roleA": result["roleA"],
                "roleNameA": ROLE_NAMES[result["roleA"]],
                "championKeyA": key_a,
                "championIdA": champion_a.champion_id,
                "nameA": champion_a.name,
                "nameZhA": champion_a.name_zh,
                "roleB": result["roleB"],
                "roleNameB": ROLE_NAMES[result["roleB"]],
                "championKeyB": key_b,
                "championIdB": champion_b.champion_id,
                "nameB": champion_b.name,
                "nameZhB": champion_b.name_zh,
                "sameRole": result["roleA"] == result["roleB"],
                "rating": rating,
                "allyWinrate": winrate_from_rating(rating),
                "allyText": rating_text(rating),
                "opponentWinrate": winrate_from_rating(-rating),
                "opponentText": rating_text(-rating),
                "games": result["games"],
            }
            results.append(item)
            total += rating
            if item["sameRole"]:
                same_role.append(item)
                same_role_total += rating
        return {
            "results": results,
            "sameRoleResults": same_role,
            "totals": {
                "all": {
                    "rating": total,
                    "allyWinrate": winrate_from_rating(total),
                    "allyText": rating_text(total),
                    "opponentWinrate": winrate_from_rating(-total),
                    "opponentText": rating_text(-total),
                },
                "sameRole": {
                    "rating": same_role_total,
                    "allyWinrate": winrate_from_rating(same_role_total),
                    "allyText": rating_text(same_role_total),
                    "opponentWinrate": winrate_from_rating(-same_role_total),
                    "opponentText": rating_text(-same_role_total),
                },
            },
        }

    def _duo_json(self, analysis: Mapping[str, Any]) -> dict[str, Any]:
        results = []
        total = 0.0
        for result in analysis["allyDuoRating"]["duoResults"]:
            key_a = result["championKeyA"]
            key_b = result["championKeyB"]
            champion_a = self.champions[key_a]
            champion_b = self.champions[key_b]
            rating = result["rating"]
            results.append(
                {
                    "roleA": result["roleA"],
                    "roleNameA": ROLE_NAMES[result["roleA"]],
                    "championKeyA": key_a,
                    "championIdA": champion_a.champion_id,
                    "nameA": champion_a.name,
                    "nameZhA": champion_a.name_zh,
                    "roleB": result["roleB"],
                    "roleNameB": ROLE_NAMES[result["roleB"]],
                    "championKeyB": key_b,
                    "championIdB": champion_b.champion_id,
                    "nameB": champion_b.name,
                    "nameZhB": champion_b.name_zh,
                    "rating": rating,
                    "winrate": winrate_from_rating(rating),
                    "winrateText": rating_text(rating),
                    "halfRating": rating / 2.0,
                    "games": result["games"],
                }
            )
            total += rating
        return {
            "results": results,
            "totals": {
                "rating": total,
                "winrate": winrate_from_rating(total),
                "winrateText": rating_text(total),
            },
        }


def _normalize_config_key(key: str) -> str:
    mapping = {
        "risk_level": "riskLevel",
        "risk": "riskLevel",
        "ignore_champion_winrates": "ignoreChampionWinrates",
        "min_games": "minGames",
        "prior_games": "priorGames",
        "include_tables": "includeTables",
    }
    return mapping.get(key, key)


def _unique(values: Iterable[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _sanitize(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Dataset download / loading
# ---------------------------------------------------------------------------


def download_dataset(name: str, data_dir: str, *, timeout: float = 180.0) -> str:
    url = f"{DATASET_BASE}/{name}"
    final_path = os.path.join(data_dir, name)
    part_path = final_path + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": "draftgap-model/1"})
    print(f"downloading {url} ...", file=sys.stderr)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        with open(part_path, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    # Validate before replacing a known-good file.
    try:
        with open(part_path, "r", encoding="utf-8") as handle:
            parsed = json.load(handle)
        if not isinstance(parsed, dict) or not isinstance(
            parsed.get("championData"), dict
        ):
            raise ValueError("missing championData")
    except Exception as error:
        os.unlink(part_path)
        raise InputError(f"{url}: downloaded dataset is invalid: {error}") from error
    os.replace(part_path, final_path)
    size = os.path.getsize(final_path)
    print(f"wrote {final_path} ({size} bytes)", file=sys.stderr)
    return final_path


DATASET_META_NAME = "remote-meta.json"


def _dataset_meta_path(data_dir: str) -> str:
    return os.path.join(data_dir, DATASET_META_NAME)


def _read_dataset_meta(data_dir: str) -> dict[str, Any]:
    try:
        with open(_dataset_meta_path(data_dir), "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_dataset_meta(data_dir: str, meta: Mapping[str, Any]) -> None:
    path = _dataset_meta_path(data_dir)
    part = path + ".part"
    with open(part, "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
    os.replace(part, path)


def _remote_dataset_meta(name: str, *, timeout: float = 20.0) -> dict[str, Any]:
    url = f"{DATASET_BASE}/{name}"
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "draftgap-model/1"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        return {
            "etag": response.headers.get("ETag"),
            "lastModified": response.headers.get("Last-Modified"),
            "contentLength": int(length) if length and length.isdigit() else None,
        }


def refresh_datasets_if_needed(
    data_dir: str, *, force: bool = False, timeout: float = 20.0
) -> list[str]:
    """Download datasets whose upstream ETag changed. Returns changed names.

    A missing sidecar is treated as unknown, so the first run after upgrading
    performs one full download even when the JSON happens to be current.
    """
    os.makedirs(data_dir, exist_ok=True)
    meta = _read_dataset_meta(data_dir)
    changed: list[str] = []
    for name in DATASET_NAMES:
        path = os.path.join(data_dir, name)
        remote = _remote_dataset_meta(name, timeout=timeout)
        known = meta.get(name) if isinstance(meta.get(name), dict) else {}
        local_exists = os.path.exists(path) and os.path.getsize(path) > 0
        if remote.get("etag"):
            stale = known.get("etag") != remote.get("etag")
        else:
            stale = (
                known.get("lastModified") != remote.get("lastModified")
                or known.get("contentLength") != remote.get("contentLength")
            )
        if force or not local_exists or not known or stale:
            download_dataset(name, data_dir)
            meta[name] = {**remote, "downloadedAt": datetime.now(timezone.utc).isoformat()}
            _write_dataset_meta(data_dir, meta)
            changed.append(name)
    return changed


def ensure_datasets(data_dir: str, *, refresh: bool = False) -> tuple[str, str]:
    os.makedirs(data_dir, exist_ok=True)
    if refresh:
        refresh_datasets_if_needed(data_dir, force=True)
    paths = []
    for name in DATASET_NAMES:
        path = os.path.join(data_dir, name)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            download_dataset(name, data_dir)
        paths.append(path)
    return paths[0], paths[1]


def load_model(data_dir: str, *, refresh: bool = False) -> DraftModel:
    current_path, thirty_path = ensure_datasets(data_dir, refresh=refresh)
    current = Dataset(current_path, "current-patch")
    thirty = Dataset(thirty_path, "30-days")
    return DraftModel(current, thirty)


class _ModelStore:
    """Owns the current model and hot-swaps it after a dataset refresh."""

    def __init__(
        self,
        data_dir: str,
        model: DraftModel,
        *,
        refresh_interval: float = 300.0,
    ) -> None:
        self.data_dir = data_dir
        self.refresh_interval = refresh_interval
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._model = model
        self._ui_cache: dict[str, Any] | None = None
        self._ui_cache_date: str | None = None
        self.last_checked: str | None = None
        self.last_refresh_error: str | None = None
        self.refreshing = False

    def get(self) -> DraftModel:
        with self._lock:
            return self._model

    def ui_payload(self, prior_games: float = 1000.0) -> dict[str, Any]:
        with self._lock:
            model = self._model
            date = model.current.date
            if self._ui_cache is not None and self._ui_cache_date == date:
                return self._ui_cache
        payload = model.ui_payload(prior_games)
        with self._lock:
            self._ui_cache = payload
            self._ui_cache_date = date
        return payload

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            model = self._model
            return {
                "currentPatch": model.current.version,
                "currentPatchDate": model.current.date,
                "thirtyDayDate": model.thirty.date,
                "champions": len(model.champions),
                "lastChecked": self.last_checked,
                "refreshError": self.last_refresh_error,
                "refreshing": self.refreshing,
                "refreshIntervalSeconds": self.refresh_interval,
            }

    def refresh_once(self, *, force: bool = False) -> bool:
        if not self._refresh_lock.acquire(blocking=False):
            return False
        self.refreshing = True
        try:
            changed = refresh_datasets_if_needed(
                self.data_dir, force=force, timeout=15.0
            )
            if changed:
                current = Dataset(
                    os.path.join(self.data_dir, DATASET_NAMES[0]), "current-patch"
                )
                thirty = Dataset(
                    os.path.join(self.data_dir, DATASET_NAMES[1]), "30-days"
                )
                new_model = DraftModel(current, thirty)
                with self._lock:
                    self._model = new_model
                    self._ui_cache = None
                    self._ui_cache_date = None
                print(
                    f"dataset refreshed: {current.version} @ {current.date}",
                    file=sys.stderr,
                )
            self.last_checked = datetime.now(timezone.utc).isoformat()
            self.last_refresh_error = None
            return bool(changed)
        except Exception as error:
            self.last_checked = datetime.now(timezone.utc).isoformat()
            self.last_refresh_error = str(error)
            print(f"dataset refresh failed: {error}", file=sys.stderr)
            return False
        finally:
            self.refreshing = False
            self._refresh_lock.release()

    def start(self) -> None:
        if self.refresh_interval <= 0:
            return
        thread = threading.Thread(target=self._loop, name="dataset-refresh", daemon=True)
        thread.start()
        self._thread = thread

    def _loop(self) -> None:
        while not self._stop.wait(max(5.0, self.refresh_interval)):
            self.refresh_once()

    def stop(self) -> None:
        self._stop.set()


# ---------------------------------------------------------------------------
# Market LoL match discovery and live/archive lineups
# ---------------------------------------------------------------------------

POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"
POLYMARKET_WEB = "https://polymarket.com"
POLYMARKET_INTERNAL_API = "https://api.defi.polymarket.com"
POLYMARKET_WS_HOST = "ws-live-v2.polymarket.com"
POLYMARKET_WS_PATH = "/ws"
POLYMARKET_LOL_SERIES_ID = "10311"
_MARKET_MATCH_LIMIT = 40
LEAGUEPEDIA_API = "https://lol.fandom.com/api.php"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")
_UPSTREAM_JSON_LIMIT = 16 * 1024 * 1024
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_WS_MESSAGE_LIMIT = 4 * 1024 * 1024


class _MarketError(Exception):
    """A tagged failure that is safe to return to an API caller."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        upstream_status: int | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.upstream_status = upstream_status
        self.hint = hint

    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {"error": self.message, "code": self.code}
        if self.hint:
            result["hint"] = self.hint
        return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _normalize_team_name(value: Any) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(value or "").casefold())


def _team_names_match(left: Any, right: Any) -> bool:
    first = _normalize_team_name(left)
    second = _normalize_team_name(right)
    if not first or not second:
        return False
    if first == second:
        return True
    shorter, longer = sorted((first, second), key=len)
    return len(shorter) >= 4 and longer.startswith(shorter)


def _split_csv(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _game_number_from_market(market: Mapping[str, Any]) -> int | None:
    for key in ("title", "groupItemTitle", "question", "slug"):
        text = market.get(key)
        if not isinstance(text, str):
            continue
        match = re.search(r"\bgame\s*(\d+)\b", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        match = re.search(r"-game(\d+)(?:$|-)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _market_winner_name(market: Mapping[str, Any]) -> str | None:
    outcomes = _json_list(market.get("outcomes"))
    prices = _json_list(market.get("outcomePrices") or market.get("outcome_prices"))
    if len(outcomes) == len(prices) and outcomes:
        best_index = -1
        best_price = -1.0
        for index, price in enumerate(prices):
            try:
                numeric = float(price)
            except (TypeError, ValueError):
                continue
            if numeric > best_price:
                best_price = numeric
                best_index = index
        if best_index >= 0 and best_price >= 0.99:
            return str(outcomes[best_index])
    for side in market.get("marketSides") or []:
        if not isinstance(side, Mapping):
            continue
        if side.get("won") is True:
            return str(side.get("label") or side.get("team") or "") or None
        try:
            price = float(side.get("price"))
        except (TypeError, ValueError):
            continue
        if price >= 0.99:
            label = side.get("label")
            if not label and isinstance(side.get("team"), Mapping):
                label = side["team"].get("name")
            if label:
                return str(label)
    return None


def _best_of_from_text(*values: Any) -> int | None:
    for value in values:
        if not isinstance(value, str):
            continue
        match = re.search(r"\bBO\s*([1-9])\b|\bBo\s*([1-9])\b", value)
        if match:
            return int(match.group(1) or match.group(2))
    return None


def _event_phase(event: Mapping[str, Any], now: datetime) -> str:
    start = _parse_iso(event.get("startTime") or event.get("startDate"))
    end = _parse_iso(event.get("endDate"))
    if event.get("live"):
        return "live"
    if event.get("closed") or event.get("ended"):
        return "finished"
    if start and start > now:
        return "upcoming"
    if end and end < now:
        return "finished"
    if start and start <= now:
        return "live"
    return "upcoming"


def _event_score_text(event: Mapping[str, Any]) -> str | None:
    score = event.get("score")
    if isinstance(score, str) and "|" in score:
        pieces = score.split("|")
        if len(pieces) > 1 and re.fullmatch(r"\d+-\d+", pieces[1].strip()):
            return pieces[1].strip()
    return None


class _MarketService:
    """Fetches LoL series metadata and lineups without exposing credentials.

    Market's public series-state feed carries GRID-backed player and draft
    snapshots while a game is live.  It does not retain those snapshots after a
    series finishes, so finished games fall back to Leaguepedia's public Cargo
    archive and report that source separately.
    """

    def __init__(
        self,
        model_provider: Callable[[], DraftModel],
        *,
        proxy: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._model_provider = model_provider
        self._proxy = (proxy or "").strip() or None
        self._timeout = max(2.0, min(float(timeout), 60.0))
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_lock = threading.Lock()

    # -- cache and transport -------------------------------------------------

    def _cache_get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._cache_lock:
            item = self._cache.get(key)
            if item is None:
                return None
            expires, value = item
            if expires <= now:
                self._cache.pop(key, None)
                return None
            return value

    def _cache_put(self, key: str, value: Any, ttl: float) -> Any:
        with self._cache_lock:
            self._cache[key] = (time.monotonic() + ttl, value)
            if len(self._cache) > 192:
                oldest = sorted(
                    self._cache.items(), key=lambda pair: pair[1][0]
                )[:64]
                for old_key, _ in oldest:
                    self._cache.pop(old_key, None)
        return value

    def _cached(self, key: str, ttl: float, loader: Callable[[], Any]) -> Any:
        value = self._cache_get(key)
        if value is not None:
            return value
        return self._cache_put(key, loader(), ttl)

    def _clear_cache(self, prefix: str) -> None:
        with self._cache_lock:
            for key in [key for key in self._cache if key.startswith(prefix)]:
                self._cache.pop(key, None)

    def _fetch_json(self, url: str, *, provider: str) -> Any:
        if self._proxy:
            proxy_handler = urllib.request.ProxyHandler(
                {"http": self._proxy, "https": self._proxy}
            )
        else:
            # A direct request is explicit: do not inherit an unrelated proxy
            # from the ambient environment when the caller did not select one.
            proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "DraftGapModel/1 (local draft analysis)",
            },
        )
        try:
            with opener.open(request, timeout=self._timeout) as response:
                raw = response.read(_UPSTREAM_JSON_LIMIT + 1)
                encoding = (response.headers.get("Content-Encoding") or "").lower()
        except urllib.error.HTTPError as error:
            status = int(error.code)
            if status == 404:
                raise _MarketError(
                    404,
                    "upstream_not_found",
                    f"{provider} has no data for this request.",
                    upstream_status=status,
                ) from error
            raise _MarketError(
                502,
                "upstream_http_error",
                f"{provider} returned HTTP {status}.",
                upstream_status=status,
            ) from error
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            hint = None
            if provider == "Market":
                hint = (
                    "If this machine requires a proxy, pass --proxy=<url> "
                    "to the serve command."
                )
            raise _MarketError(
                502,
                "upstream_unreachable",
                f"Could not reach {provider}.",
                hint=hint,
            ) from error
        if len(raw) > _UPSTREAM_JSON_LIMIT:
            raise _MarketError(
                502,
                "upstream_too_large",
                f"{provider} returned an oversized response.",
            )
        if encoding == "gzip":
            try:
                raw = gzip.decompress(raw)
            except OSError as error:
                raise _MarketError(
                    502,
                    "invalid_upstream_response",
                    f"{provider} returned a malformed compressed response.",
                ) from error
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise _MarketError(
                502,
                "invalid_upstream_response",
                f"{provider} returned invalid JSON.",
            ) from error

    def _gamma_events(self, params: Mapping[str, Any]) -> list[Any]:
        query = urllib.parse.urlencode(params, doseq=True)
        payload = self._fetch_json(
            f"{POLYMARKET_GAMMA_API}/events?{query}", provider="Market"
        )
        return payload if isinstance(payload, list) else []

    # -- live WebSocket snapshot --------------------------------------------

    @staticmethod
    def _read_http_headers(reader: Any) -> bytes:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = reader.recv(1)
            if not chunk:
                raise OSError("connection closed during HTTP handshake")
            data.extend(chunk)
            if len(data) > 64 * 1024:
                raise OSError("HTTP handshake response too large")
        return bytes(data)

    @staticmethod
    def _websocket_accept(key: str) -> str:
        return base64.b64encode(
            hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()
        ).decode("ascii")

    def _open_live_websocket(self) -> Any:
        timeout = min(self._timeout, 10.0)
        proxy = None
        if self._proxy:
            parsed = urllib.parse.urlsplit(self._proxy)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise OSError("unsupported WebSocket proxy")
            proxy = (
                parsed.scheme,
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                parsed.username,
                parsed.password,
            )
        if proxy:
            scheme, proxy_host, proxy_port, username, password = proxy
            raw_socket = socket.create_connection(
                (proxy_host, proxy_port), timeout=timeout
            )
            if scheme == "https":
                raw_socket = ssl.create_default_context().wrap_socket(
                    raw_socket, server_hostname=proxy_host
                )
            connect_lines = [
                f"CONNECT {POLYMARKET_WS_HOST}:443 HTTP/1.1",
                f"Host: {POLYMARKET_WS_HOST}:443",
                "Proxy-Connection: keep-alive",
            ]
            if username is not None:
                credentials = base64.b64encode(
                    f"{urllib.parse.unquote(username)}:"
                    f"{urllib.parse.unquote(password or '')}".encode("utf-8")
                ).decode("ascii")
                connect_lines.append(f"Proxy-Authorization: Basic {credentials}")
            raw_socket.sendall(
                ("\r\n".join(connect_lines) + "\r\n\r\n").encode("ascii")
            )
            response = self._read_http_headers(raw_socket)
            first_line = response.split(b"\r\n", 1)[0].decode("latin1", "replace")
            pieces = first_line.split(" ", 2)
            if len(pieces) < 2 or pieces[1] != "200":
                raw_socket.close()
                raise OSError("WebSocket proxy CONNECT failed")
        else:
            raw_socket = socket.create_connection(
                (POLYMARKET_WS_HOST, 443), timeout=timeout
            )
        try:
            sock = ssl.create_default_context().wrap_socket(
                raw_socket, server_hostname=POLYMARKET_WS_HOST
            )
        except Exception:
            raw_socket.close()
            raise
        sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {POLYMARKET_WS_PATH} HTTP/1.1\r\n"
            f"Host: {POLYMARKET_WS_HOST}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Origin: https://polymarket.com\r\n"
            "User-Agent: DraftGapModel/1 (local draft analysis)\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = self._read_http_headers(sock)
        first_line = response.split(b"\r\n", 1)[0].decode("latin1", "replace")
        if " 101 " not in f" {first_line} ":
            sock.close()
            raise OSError("WebSocket upgrade failed")
        headers: dict[str, str] = {}
        for line in response.split(b"\r\n")[1:]:
            if b":" not in line:
                continue
            name, value = line.split(b":", 1)
            headers[name.decode("latin1").strip().lower()] = value.decode(
                "latin1"
            ).strip()
        if headers.get("sec-websocket-accept") != self._websocket_accept(key):
            sock.close()
            raise OSError("WebSocket accept key mismatch")
        return sock

    @staticmethod
    def _recv_exact(reader: Any, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = reader.recv(size - len(chunks))
            if not chunk:
                raise OSError("WebSocket connection closed")
            chunks.extend(chunk)
        return bytes(chunks)

    @classmethod
    def _ws_send_frame(cls, sock: Any, payload: bytes, opcode: int = 0x1) -> None:
        mask = os.urandom(4)
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask)
        masked = bytes(
            byte ^ mask[index % 4] for index, byte in enumerate(payload)
        )
        sock.sendall(bytes(header) + masked)

    @classmethod
    def _ws_recv_message(cls, sock: Any) -> bytes | None:
        message = bytearray()
        started = False
        while True:
            first, second = cls._recv_exact(sock, 2)
            final = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", cls._recv_exact(sock, 2))[0]
            elif length == 127:
                length = struct.unpack("!Q", cls._recv_exact(sock, 8))[0]
            if length > _WS_MESSAGE_LIMIT:
                raise OSError("WebSocket frame too large")
            mask = cls._recv_exact(sock, 4) if masked else None
            payload = cls._recv_exact(sock, length)
            if mask is not None:
                payload = bytes(
                    byte ^ mask[index % 4] for index, byte in enumerate(payload)
                )
            if opcode == 0x8:
                return None
            if opcode == 0x9:
                cls._ws_send_frame(sock, payload, 0xA)
                continue
            if opcode == 0xA:
                continue
            if opcode in (0x1, 0x2):
                if started:
                    raise OSError("unexpected WebSocket data frame")
                message = bytearray(payload)
                started = True
            elif opcode == 0x0:
                if not started:
                    raise OSError("unexpected WebSocket continuation")
                message.extend(payload)
            else:
                raise OSError("unsupported WebSocket opcode")
            if len(message) > _WS_MESSAGE_LIMIT:
                raise OSError("WebSocket message too large")
            if final:
                return bytes(message)

    def _fetch_live_snapshot(self, event_id: str) -> dict[str, Any] | None:
        sock = self._open_live_websocket()
        try:
            self._ws_send_frame(
                sock,
                json.dumps(
                    {
                        "op": "subscribe",
                        "subscriptions": [
                            {
                                "channel": "esports.series",
                                "filter": {"event_id": str(event_id)},
                            }
                        ],
                    },
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
            while True:
                raw = self._ws_recv_message(sock)
                if raw is None:
                    return None
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(message, Mapping):
                    continue
                if message.get("channel") != "esports.series":
                    continue
                payload = message.get("payload")
                if not isinstance(payload, Mapping):
                    if message.get("snapshot") and payload is None:
                        return None
                    continue
                if str(payload.get("event_id") or "") != str(event_id):
                    continue
                return dict(payload)
        finally:
            try:
                self._ws_send_frame(sock, b"", 0x8)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def _live_snapshot(self, event_id: Any) -> dict[str, Any] | None:
        event_id = str(event_id or "")
        if not event_id:
            return None
        key = f"live:{event_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        try:
            payload = self._fetch_live_snapshot(event_id)
        except (OSError, ssl.SSLError, ValueError, TimeoutError):
            payload = None
        if payload is not None:
            self._cache_put(key, payload, 5.0)
        return payload

    # -- match discovery -----------------------------------------------------

    @staticmethod
    def _match_start_key(match: Mapping[str, Any]) -> tuple[float, str]:
        start = _parse_iso(match.get("startTime"))
        return (
            start.timestamp() if start else float("-inf"),
            str(match.get("slug") or ""),
        )

    def _match_open_summaries(self, now: datetime) -> list[dict[str, Any]]:
        key = "matches:open"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        events = self._gamma_events(
            {
                "series_id": POLYMARKET_LOL_SERIES_ID,
                "active": "true",
                "closed": "false",
                "limit": "50",
                "order": "startTime",
                "ascending": "true",
                "include_markets": "false",
            }
        )
        summaries: list[dict[str, Any]] = []
        for event in events:
            summary = self._match_summary(event, now)
            if summary is None or summary["state"] == "recent":
                # Gamma still lists some long-finished LoL events as open.
                continue
            summaries.append(summary)
        return self._cache_put(key, summaries, 20.0)

    def _match_closed_chunk(self, offset: int, page_size: int) -> dict[str, Any]:
        key = f"matches:closed:{offset}:{page_size}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        events = self._gamma_events(
            {
                "series_id": POLYMARKET_LOL_SERIES_ID,
                "closed": "true",
                "limit": str(page_size + 1),
                "offset": str(offset),
                "order": "startTime",
                "ascending": "false",
                "include_markets": "false",
            }
        )
        now = datetime.now(timezone.utc)
        summaries: list[dict[str, Any]] = []
        for event in events:
            summary = self._match_summary(event, now)
            if summary is not None:
                summaries.append(summary)
        # The extra row tells the next page whether more raw events exist,
        # without walking the whole archive before the first page can render.
        return self._cache_put(
            key,
            {"summaries": summaries, "hasMore": len(events) > page_size},
            20.0,
        )

    def matches(
        self, limit: int = 5, page: int = 1, *, refresh: bool = False
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 40))
        max_page = max(
            1, (_MARKET_MATCH_LIMIT + limit - 1) // limit
        )
        page = max(1, min(int(page), max_page))
        if refresh:
            self._clear_cache("matches:")
        now = datetime.now(timezone.utc)
        by_slug = {
            summary["slug"]: summary
            for summary in self._match_open_summaries(now)
        }
        target = min(_MARKET_MATCH_LIMIT, page * limit + 1)
        offset = 0
        exhausted = False
        while len(by_slug) < target and not exhausted:
            chunk = self._match_closed_chunk(offset, limit)
            for summary in chunk["summaries"]:
                by_slug.setdefault(summary["slug"], summary)
            exhausted = not chunk["hasMore"]
            offset += limit

        all_matches = sorted(
            by_slug.values(), key=self._match_start_key, reverse=True
        )[:_MARKET_MATCH_LIMIT]
        capped = len(all_matches) >= _MARKET_MATCH_LIMIT
        total: int | None = None
        total_pages: int | None = None
        if exhausted or capped:
            total = len(all_matches)
            total_pages = max(1, (total + limit - 1) // limit)
            page = min(page, total_pages)
        start = (page - 1) * limit
        notes: list[str] = []
        if not any(match["state"] in ("live", "upcoming") for match in all_matches):
            notes.append(
                "No live or upcoming LoL matches are listed right now; "
                "recent results are shown."
            )
        return {
            "ok": True,
            "fetchedAt": _now_iso(),
            "source": {
                "provider": "Market",
                "label": "Market LoL",
                "url": f"{POLYMARKET_WEB}/esports/league-of-legends",
            },
            "matches": all_matches[start : start + limit],
            "notes": notes,
            "pagination": {
                "page": page,
                "pageSize": limit,
                "total": total,
                "totalPages": total_pages,
                "hasPrevious": page > 1,
                "hasNext": (
                    page < total_pages if total_pages is not None else True
                ),
            },
        }

    def _match_summary(
        self, event: Any, now: datetime
    ) -> dict[str, Any] | None:
        if not isinstance(event, Mapping):
            return None
        slug = event.get("slug")
        if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
            return None
        teams = event.get("teams")
        if not isinstance(teams, list) or len(teams) < 2:
            return None
        if not event.get("gameId") and not str(slug).startswith("lol-"):
            return None
        title = str(event.get("title") or slug)
        competition = title.split(" - ", 1)[1] if " - " in title else None
        state = _event_phase(event, now)
        summary_state = (
            "live" if state == "live" else "upcoming" if state == "upcoming" else "recent"
        )
        team_payload = []
        for team in teams[:2]:
            if not isinstance(team, Mapping):
                continue
            team_payload.append(
                {
                    "name": str(team.get("name") or ""),
                    "abbreviation": team.get("abbreviation"),
                    "score": _int_or_none(team.get("score")),
                }
            )
        if len(team_payload) < 2 or not all(team["name"] for team in team_payload):
            return None
        start = event.get("startTime") or event.get("startDate")
        return {
            "id": str(event.get("id") or ""),
            "slug": slug,
            "title": title,
            "competition": competition,
            "startTime": start,
            "endTime": event.get("endDate"),
            "state": summary_state,
            "bestOf": _best_of_from_text(title, event.get("score"), event.get("period")),
            "score": _event_score_text(event),
            "teams": team_payload,
            "url": f"{POLYMARKET_WEB}/event/{slug}",
        }

    # -- match details -------------------------------------------------------

    @staticmethod
    def _validate_slug(slug: Any) -> str:
        if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
            raise _MarketError(400, "invalid_slug", "invalid market event slug")
        return slug

    def match(self, slug: str) -> dict[str, Any]:
        slug = self._validate_slug(slug)
        return self._cached(
            f"match:{slug}", 25.0, lambda: self._load_match(slug)
        )

    def _event_view(self, slug: str) -> dict[str, Any]:
        key = f"event:{slug}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        def load() -> dict[str, Any]:
            internal_error: _MarketError | None = None
            encoded = urllib.parse.quote(slug, safe="")
            try:
                data = self._fetch_json(
                    f"{POLYMARKET_INTERNAL_API}/internal/view/events/{encoded}"
                    "?locale=en&group=all",
                    provider="Market",
                )
                if isinstance(data, Mapping) and isinstance(
                    data.get("event"), Mapping
                ):
                    return dict(data["event"])
            except _MarketError as error:
                internal_error = error
            try:
                data = self._fetch_json(
                    f"{POLYMARKET_GAMMA_API}/events/{encoded}",
                    provider="Market",
                )
                if isinstance(data, Mapping):
                    return dict(data)
            except _MarketError:
                if internal_error is not None:
                    raise internal_error
                raise
            if internal_error is not None:
                raise internal_error
            raise _MarketError(
                502, "invalid_upstream_response", "Market returned no event."
            )

        return self._cache_put(key, load(), 60.0)

    def _series_state(self, grid_series_id: str | None) -> dict[str, Any] | None:
        if not grid_series_id:
            return None
        key = f"series:{grid_series_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        def load() -> dict[str, Any] | None:
            try:
                data = self._fetch_json(
                    f"{POLYMARKET_WEB}/api/esports/series-state?seriesId="
                    f"{urllib.parse.quote(grid_series_id, safe='')}",
                    provider="Market",
                )
            except _MarketError:
                return None
            return dict(data) if isinstance(data, Mapping) else None

        return self._cache_put(key, load(), 20.0)

    @staticmethod
    def _event_teams(
        event: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        parsed: list[dict[str, Any]] = []
        for team in event.get("teams") or []:
            if not isinstance(team, Mapping):
                continue
            parsed.append(
                {
                    "id": str(team.get("id") or ""),
                    "name": str(team.get("name") or ""),
                    "abbreviation": team.get("abbreviation"),
                    "score": _int_or_none(team.get("score")),
                    "host": str(team.get("host") or "").lower(),
                }
            )
        if len(parsed) < 2:
            raise _MarketError(
                502, "invalid_upstream_response", "Market event has no teams."
            )
        home = next(
            (team for team in parsed if team.get("host") == "home"),
            parsed[0],
        )
        away = next(
            (
                team
                for team in parsed
                if team.get("host") == "away" and team is not home
            ),
            next(team for team in parsed if team is not home),
        )
        return home, away

    def _load_match(self, slug: str) -> dict[str, Any]:
        event = self._event_view(slug)
        home, away = self._event_teams(event)
        metadata = event.get("metadata")
        grid_series_id = None
        if isinstance(metadata, Mapping) and metadata.get("gridSeriesId"):
            grid_series_id = str(metadata["gridSeriesId"])
        series = self._series_state(grid_series_id)
        now = datetime.now(timezone.utc)
        phase = _event_phase(event, now)
        score = _event_score_text(event)
        if score is None and home.get("score") is not None and away.get("score") is not None:
            score = f"{home['score']}-{away['score']}"
        best_of = _best_of_from_text(
            event.get("title"), event.get("score"), event.get("period")
        )
        played_total = None
        if score is not None:
            score_match = re.fullmatch(r"(\d+)-(\d+)", score)
            if score_match:
                played_total = int(score_match.group(1)) + int(
                    score_match.group(2)
                )
        games = self._games_for_event(
            event, series, home, away, phase, best_of, played_total
        )
        if best_of is None and games:
            best_of = max(game["number"] for game in games)
        notes: list[str] = []
        if phase == "finished":
            notes.append(
                "The market publishes live draft snapshots; finished games "
                "fall back to Leaguepedia's public scoreboard archive when "
                "the market no longer serves the draft."
            )
        elif phase == "upcoming":
            notes.append("Lineups appear after the series and draft begin.")
        return {
            "ok": True,
            "fetchedAt": _now_iso(),
            "slug": slug,
            "eventId": str(event.get("id") or ""),
            "url": f"{POLYMARKET_WEB}/event/{slug}",
            "title": str(event.get("title") or slug),
            "competition": (
                str(event.get("title") or "").split(" - ", 1)[1]
                if " - " in str(event.get("title") or "")
                else None
            ),
            "startTime": event.get("startTime") or event.get("startDate"),
            "endTime": event.get("endDate"),
            "state": phase,
            "score": score,
            "period": event.get("period"),
            "bestOf": best_of,
            "home": {key: value for key, value in home.items() if key != "host"},
            "away": {key: value for key, value in away.items() if key != "host"},
            "games": games,
            "gridSeriesId": grid_series_id,
            "notes": notes,
            "source": {
                "provider": "Market",
                "label": "Market LoL",
                "url": f"{POLYMARKET_WEB}/event/{slug}",
            },
        }

    def _games_for_event(
        self,
        event: Mapping[str, Any],
        series: Mapping[str, Any] | None,
        home: Mapping[str, Any],
        away: Mapping[str, Any],
        phase: str,
        best_of: int | None,
        played_total: int | None,
    ) -> list[dict[str, Any]]:
        markets: dict[int, Mapping[str, Any]] = {}
        market_lists: list[Any] = []
        if isinstance(event.get("marketGroups"), list):
            child_group = next(
                (
                    group
                    for group in event["marketGroups"]
                    if isinstance(group, Mapping)
                    and (
                        group.get("id") == "child_moneyline"
                        or group.get("sportsMarketType") == "child_moneyline"
                    )
                ),
                None,
            )
            if child_group and isinstance(child_group.get("markets"), list):
                market_lists.extend(child_group["markets"])
        if not market_lists and isinstance(event.get("markets"), list):
            # Gamma's event fallback carries the child markets in one flat list;
            # exclude props such as Game 5 duration when Game 5 was never played.
            market_lists.extend(
                market
                for market in event["markets"]
                if isinstance(market, Mapping)
                and (
                    market.get("sportsMarketType") == "child_moneyline"
                    or re.search(
                        r"\bGame\s+\d+\s+Winner\b",
                        str(market.get("groupItemTitle") or market.get("title") or ""),
                        re.IGNORECASE,
                    )
                )
            )
        for market in market_lists:
            if not isinstance(market, Mapping):
                continue
            number = _game_number_from_market(market)
            if number is not None and 1 <= number <= 9:
                markets.setdefault(number, market)

        series_games: dict[int, Mapping[str, Any]] = {}
        if isinstance(series, Mapping) and isinstance(series.get("games"), list):
            for game in series["games"]:
                if not isinstance(game, Mapping):
                    continue
                number = _int_or_none(game.get("number") or game.get("sequenceNumber"))
                if number is not None:
                    series_games[number] = game

        numbers = sorted(set(markets) | set(series_games))
        if not numbers and best_of:
            numbers = list(range(1, best_of + 1))
        if phase == "finished":
            # Closed markets can exist for a game that was never needed,
            # such as Game 4 after a 0-3 sweep. Prefer explicit evidence that
            # a game happened: the final score, a started series game, or a
            # settled winner market.
            played_numbers: set[int] = set()
            if played_total:
                played_numbers.update(range(1, played_total + 1))
            played_numbers.update(
                number
                for number, game in series_games.items()
                if game.get("started") or game.get("finished")
            )
            played_numbers.update(
                number
                for number, market in markets.items()
                if _market_winner_name(market) is not None
            )
            if played_numbers:
                numbers = sorted(played_numbers)
        games: list[dict[str, Any]] = []
        for number in numbers:
            market = markets.get(number)
            series_game = series_games.get(number)
            status = "upcoming"
            winner_side = None
            home_kills = None
            away_kills = None
            lineup_available = False
            if series_game is not None:
                started = bool(series_game.get("started"))
                finished = bool(series_game.get("finished"))
                status = "finished" if finished else "live" if started else "upcoming"
                home_kills, away_kills = self._series_kills(
                    series_game, series, home, away
                )
                winner_side = self._series_winner_side(
                    series_game, series, home, away
                )
                lineup_available = self._series_has_lineup(series_game)
            elif market is not None:
                winner_name = _market_winner_name(market)
                winner_side = self._winner_name_side(winner_name, home, away)
                if market.get("closed"):
                    status = "finished"
                elif phase == "live" and self._period_game(event) == number:
                    status = "live"
            if phase == "upcoming":
                status = "upcoming"
            elif phase == "finished" and status == "upcoming" and market is None:
                continue
            games.append(
                {
                    "number": number,
                    "label": f"Game {number}",
                    "status": status,
                    "winnerSide": winner_side,
                    "homeKills": home_kills,
                    "awayKills": away_kills,
                    "lineupAvailable": lineup_available,
                }
            )
        return games

    @staticmethod
    def _period_game(event: Mapping[str, Any]) -> int | None:
        period = event.get("period")
        if not isinstance(period, str):
            return None
        match = re.match(r"\s*(\d+)\s*/", period)
        return int(match.group(1)) if match else None

    @staticmethod
    def _team_side(
        team_id: Any,
        series: Mapping[str, Any] | None,
        home: Mapping[str, Any],
        away: Mapping[str, Any],
    ) -> str | None:
        team_id = str(team_id or "")
        if isinstance(series, Mapping):
            for team in series.get("teams") or []:
                if not isinstance(team, Mapping) or str(team.get("id") or "") != team_id:
                    continue
                side = str(team.get("polymarket_side") or "").lower()
                if side in ("home", "away"):
                    return side
                if _team_names_match(team.get("name"), home.get("name")):
                    return "home"
                if _team_names_match(team.get("name"), away.get("name")):
                    return "away"
        return None

    def _series_kills(
        self,
        game: Mapping[str, Any],
        series: Mapping[str, Any] | None,
        home: Mapping[str, Any],
        away: Mapping[str, Any],
    ) -> tuple[int | None, int | None]:
        values = {"home": None, "away": None}
        for team in game.get("teams") or []:
            if not isinstance(team, Mapping):
                continue
            side = self._team_side(team.get("team_id") or team.get("id"), series, home, away)
            if side:
                values[side] = _int_or_none(team.get("score"))
        return values["home"], values["away"]

    def _series_winner_side(
        self,
        game: Mapping[str, Any],
        series: Mapping[str, Any] | None,
        home: Mapping[str, Any],
        away: Mapping[str, Any],
    ) -> str | None:
        winner_id = game.get("winner_team_id")
        if winner_id:
            side = self._team_side(winner_id, series, home, away)
            if side:
                return side
        for team in game.get("teams") or []:
            if not isinstance(team, Mapping):
                continue
            if team.get("won") is True:
                return self._team_side(team.get("team_id") or team.get("id"), series, home, away)
        return None

    @staticmethod
    def _series_has_lineup(game: Mapping[str, Any]) -> bool:
        for team in game.get("teams") or []:
            if not isinstance(team, Mapping):
                continue
            for player in team.get("players") or []:
                if isinstance(player, Mapping) and player.get("character"):
                    return True
        for entry in game.get("draft") or []:
            if (
                isinstance(entry, Mapping)
                and entry.get("draftable")
                and str(entry.get("action") or "").lower() == "pick"
            ):
                return True
        return False

    @staticmethod
    def _winner_name_side(
        winner_name: str | None,
        home: Mapping[str, Any],
        away: Mapping[str, Any],
    ) -> str | None:
        if not winner_name:
            return None
        if _team_names_match(winner_name, home.get("name")):
            return "home"
        if _team_names_match(winner_name, away.get("name")):
            return "away"
        return None

    # -- lineups -------------------------------------------------------------

    def lineup(self, slug: str, game_number: int) -> dict[str, Any]:
        slug = self._validate_slug(slug)
        try:
            game_number = int(game_number)
        except (TypeError, ValueError):
            raise _MarketError(400, "invalid_game", "game must be an integer")
        if not 1 <= game_number <= 9:
            raise _MarketError(400, "invalid_game", "game must be between 1 and 9")
        match = self.match(slug)
        game = next(
            (item for item in match["games"] if item["number"] == game_number),
            None,
        )
        if game is None:
            raise _MarketError(
                404, "game_not_found", f"Game {game_number} is not listed for this match"
            )
        event = self._event_view(slug)
        grid_series_id = match.get("gridSeriesId")
        series = self._series_state(grid_series_id)
        home = match["home"]
        away = match["away"]
        payload = None
        if match["state"] == "live":
            snapshot = self._live_snapshot(match.get("eventId"))
            if snapshot is not None:
                payload = self._polymarket_lineup(
                    snapshot, game_number, home, away, game
                )
        if payload is None and series is not None:
            payload = self._polymarket_lineup(
                series, game_number, home, away, game
            )
        if payload is None and match["state"] == "finished":
            payload = self._archive_lineup(match, game_number, home, away, event)
        if payload is None:
            note = (
                "The market has not published a lineup for this game yet."
                if match["state"] != "finished"
                else (
                    "The market no longer serves this finished game's draft, "
                    "and no matching Leaguepedia archive row was found."
                )
            )
            payload = {
                "home": {
                    "name": home["name"],
                    "score": home.get("score"),
                    "gameKills": None,
                    "won": game.get("winnerSide") == "home",
                    "picks": [],
                    "bans": [],
                    "roleSource": "unavailable",
                },
                "away": {
                    "name": away["name"],
                    "score": away.get("score"),
                    "gameKills": None,
                    "won": game.get("winnerSide") == "away",
                    "picks": [],
                    "bans": [],
                    "roleSource": "unavailable",
                },
                "source": {
                    "kind": "none",
                    "label": "No lineup published",
                    "url": match["url"],
                    "note": note,
                    "fetchedAt": _now_iso(),
                },
                "warnings": [],
            }
        if payload.get("source", {}).get("kind") == "market":
            payload["source"]["url"] = match["url"]
        payload.update(
            {
                "ok": True,
                "slug": slug,
                "eventUrl": match["url"],
                "title": match["title"],
                "competition": match["competition"],
                "startTime": match["startTime"],
                "game": game_number,
                "gameLabel": f"Game {game_number}",
                "status": game["status"],
                "winnerSide": game.get("winnerSide"),
                "matchScore": match.get("score"),
                "bestOf": match.get("bestOf"),
            }
        )
        payload["coverage"] = self._lineup_coverage(payload["home"], payload["away"])
        return payload

    def _polymarket_lineup(
        self,
        series: Mapping[str, Any],
        game_number: int,
        home: Mapping[str, Any],
        away: Mapping[str, Any],
        game_meta: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        series_game = None
        for candidate in series.get("games") or []:
            if not isinstance(candidate, Mapping):
                continue
            number = _int_or_none(
                candidate.get("number") or candidate.get("sequenceNumber")
            )
            if number == game_number:
                series_game = candidate
                break
        if series_game is None:
            return None
        sides: dict[str, Mapping[str, Any]] = {}
        for team in series_game.get("teams") or []:
            if not isinstance(team, Mapping):
                continue
            side = self._team_side(team.get("team_id") or team.get("id"), series, home, away)
            if side:
                sides[side] = team
        draft = [
            entry
            for entry in series_game.get("draft") or []
            if isinstance(entry, Mapping) and entry.get("draftable")
        ]
        model = self._model_provider()
        result_sides: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for side, meta in (("home", home), ("away", away)):
            team = sides.get(side, {})
            players = [
                player
                for player in team.get("players") or []
                if isinstance(player, Mapping) and player.get("character")
            ]
            picks: list[dict[str, Any]] = []
            role_source = "unavailable"
            if players:
                role_source = "market-player-order"
                for slot, player in enumerate(players[:5]):
                    picks.append(
                        self._resolve_pick(
                            model,
                            player.get("character"),
                            player.get("character_id"),
                            slot,
                            player.get("name"),
                            warnings,
                        )
                    )
            else:
                team_id = team.get("team_id")
                draft_picks = [
                    entry
                    for entry in sorted(
                        draft, key=lambda item: _int_or_none(item.get("sequence")) or 0
                    )
                    if str(entry.get("team_id") or "") == str(team_id or "")
                    and str(entry.get("action") or "").lower() == "pick"
                ]
                for slot, entry in enumerate(draft_picks[:5]):
                    picks.append(
                        self._resolve_pick(
                            model,
                            entry.get("draftable"),
                            entry.get("draftable_id"),
                            None,
                            None,
                            warnings,
                        )
                    )
            bans = []
            team_id = team.get("team_id")
            for entry in sorted(
                draft, key=lambda item: _int_or_none(item.get("sequence")) or 0
            ):
                if (
                    str(entry.get("team_id") or "") == str(team_id or "")
                    and str(entry.get("action") or "").lower() == "ban"
                ):
                    ban = self._resolve_pick(
                        model,
                        entry.get("draftable"),
                        entry.get("draftable_id"),
                        None,
                        None,
                        warnings,
                    )
                    bans.append(
                        {
                            "champion": ban["champion"],
                            "name": ban.get("name"),
                            "resolved": ban["resolved"],
                        }
                    )
            result_sides[side] = {
                "name": meta["name"],
                "score": meta.get("score"),
                "gameKills": game_meta.get("homeKills")
                if side == "home"
                else game_meta.get("awayKills"),
                "won": game_meta.get("winnerSide") == side,
                "picks": picks,
                "bans": bans,
                "roleSource": role_source,
            }
            if not picks:
                warnings.append(f"No picks were available for {meta['name']}.")
            if role_source == "unavailable" and picks:
                warnings.append(
                    f"{meta['name']}: picks were published without role order."
                )
        if not result_sides["home"]["picks"] and not result_sides["away"]["picks"]:
            return None
        roles_from_players = any(
            side.get("roleSource") == "market-player-order"
            for side in result_sides.values()
        )
        source = {
            "kind": "market",
            "label": "Market live feed",
            "url": "",
            "note": (
                "The market's live esports feed published this draft. "
                + (
                    "Roles follow the feed's player order."
                    if roles_from_players
                    else "Roles were not published with this draft snapshot."
                )
            ),
            "fetchedAt": _now_iso(),
        }
        return {
            "home": result_sides["home"],
            "away": result_sides["away"],
            "source": source,
            "warnings": warnings,
        }

    def _resolve_pick(
        self,
        model: DraftModel,
        raw: Any,
        raw_id: Any,
        role: int | None,
        player: Any,
        warnings: list[str],
    ) -> dict[str, Any]:
        candidates = []
        for candidate in (raw, raw_id):
            if isinstance(candidate, str) and candidate.strip():
                candidates.append(candidate.strip())
        key = None
        for candidate in candidates:
            try:
                key = model.resolve_champion(candidate)
            except InputError:
                continue
            if key:
                break
        display = candidates[0] if candidates else "Unknown"
        if key is None:
            warnings.append(f"Champion {display!r} is not in the DraftGap dataset.")
            return {
                "champion": display,
                "championKey": None,
                "championId": None,
                "name": display,
                "nameZh": None,
                "role": role,
                "roleName": ROLE_NAMES.get(role) if role is not None else None,
                "player": str(player) if player else None,
                "resolved": False,
            }
        info = model.champions[key]
        return {
            "champion": display,
            "championKey": info.key,
            "championId": info.champion_id,
            "name": info.name,
            "nameZh": info.name_zh,
            "role": role,
            "roleName": ROLE_NAMES.get(role) if role is not None else None,
            "player": str(player) if player else None,
            "resolved": True,
        }

    @staticmethod
    def _lineup_coverage(home: Mapping[str, Any], away: Mapping[str, Any]) -> dict[str, Any]:
        picks = [pick for side in (home, away) for pick in side.get("picks") or []]
        resolved = [pick for pick in picks if pick.get("resolved")]
        return {
            "picks": len(picks),
            "resolved": len(resolved),
            "unresolved": len(picks) - len(resolved),
            "homePicks": len(home.get("picks") or []),
            "awayPicks": len(away.get("picks") or []),
            "complete": len(home.get("picks") or []) == 5
            and len(away.get("picks") or []) == 5,
        }

    # -- Leaguepedia archive fallback ----------------------------------------

    def _leaguepedia_archive(
        self, match: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        key = f"leaguepedia:{match.get('slug')}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        start = _parse_iso(match.get("startTime")) or datetime.now(timezone.utc)
        date_from = (start - timedelta(days=1)).strftime("%Y-%m-%d")
        date_to = (start + timedelta(days=3)).strftime("%Y-%m-%d")
        home_name = str(match["home"].get("name") or "")
        away_name = str(match["away"].get("name") or "")
        if not home_name or not away_name:
            return None

        def quote(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        where = (
            f"((Team1={quote(home_name)} AND Team2={quote(away_name)}) "
            f"OR (Team1={quote(away_name)} AND Team2={quote(home_name)})) "
            f"AND DateTime_UTC >= '{date_from}' "
            f"AND DateTime_UTC <= '{date_to}'"
        )
        params = {
            "action": "cargoquery",
            "format": "json",
            "limit": "50",
            "tables": "ScoreboardGames",
            "fields": (
                "OverviewPage,MatchId,GameId,Team1,Team2,Team1Picks,Team2Picks,"
                "Team1Bans,Team2Bans,DateTime_UTC,Tournament,N_GameInMatch,"
                "WinTeam,Team1Players,Team2Players"
            ),
            "where": where,
            "order_by": "DateTime_UTC ASC",
        }

        def load() -> dict[str, Any] | None:
            try:
                data = self._fetch_json(
                    f"{LEAGUEPEDIA_API}?{urllib.parse.urlencode(params)}",
                    provider="Leaguepedia",
                )
            except _MarketError:
                return None
            rows = []
            for item in data.get("cargoquery", []) if isinstance(data, Mapping) else []:
                if isinstance(item, Mapping) and isinstance(item.get("title"), Mapping):
                    rows.append(dict(item["title"]))
            if not rows:
                return None
            return {"rows": rows, "sourceUrl": self._wiki_url(rows[0])}

        return self._cache_put(key, load(), 6 * 3600.0)

    @staticmethod
    def _wiki_url(row: Mapping[str, Any]) -> str:
        overview = str(row.get("OverviewPage") or "")
        if not overview:
            return "https://lol.fandom.com/"
        slug = urllib.parse.quote(
            overview.replace(" ", "_"), safe="/:_-.,()"
        )
        return f"https://lol.fandom.com/wiki/{slug}"

    def _archive_lineup(
        self,
        match: Mapping[str, Any],
        game_number: int,
        home: Mapping[str, Any],
        away: Mapping[str, Any],
        event: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        archive = self._leaguepedia_archive(match)
        if archive is None:
            return None
        rows = archive["rows"]
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            match_id = str(row.get("MatchId") or "")
            if match_id:
                groups[match_id].append(row)
        best: tuple[float, str, list[Mapping[str, Any]]] | None = None
        start = _parse_iso(match.get("startTime")) or datetime.now(timezone.utc)
        for match_id, group in groups.items():
            for row in group:
                if self._archive_game_number(row, group) != game_number:
                    continue
                times = [
                    _parse_iso(candidate.get("DateTime UTC"))
                    for candidate in group
                ]
                times = [value for value in times if value is not None]
                distance = (
                    abs((min(times) - start).total_seconds())
                    if times
                    else float("inf")
                )
                if best is None or distance < best[0]:
                    best = (distance, match_id, group)
                break
        if best is None:
            return None
        selected_match_id, group = best[1], best[2]
        selected_row = next(
            (
                row
                for row in group
                if self._archive_game_number(row, group) == game_number
            ),
            None,
        )
        if selected_row is None:
            return None
        orientation = self._archive_orientation(selected_row, home, away)
        if orientation is None:
            return None
        flipped = orientation == "flipped"
        picks_field = "Team2Picks" if flipped else "Team1Picks"
        bans_field = "Team2Bans" if flipped else "Team1Bans"
        players_field = "Team2Players" if flipped else "Team1Players"
        other_picks = "Team1Picks" if flipped else "Team2Picks"
        other_bans = "Team1Bans" if flipped else "Team2Bans"
        other_players = "Team1Players" if flipped else "Team2Players"
        model = self._model_provider()
        warnings: list[str] = []
        home_picks = self._archive_picks(
            model,
            _split_csv(selected_row.get(picks_field)),
            _split_csv(selected_row.get(players_field)),
            warnings,
        )
        away_picks = self._archive_picks(
            model,
            _split_csv(selected_row.get(other_picks)),
            _split_csv(selected_row.get(other_players)),
            warnings,
        )
        home_bans = self._archive_bans(
            model, _split_csv(selected_row.get(bans_field)), warnings
        )
        away_bans = self._archive_bans(
            model, _split_csv(selected_row.get(other_bans)), warnings
        )
        winner = str(selected_row.get("WinTeam") or "")
        winner_norm = _normalize_team_name(winner)
        home_won = winner_norm == _normalize_team_name(home.get("name"))
        away_won = winner_norm == _normalize_team_name(away.get("name"))
        if home_won:
            winner_side = "home"
        elif away_won:
            winner_side = "away"
        else:
            winner_side = None
        return {
            "home": {
                "name": home["name"],
                "score": home.get("score"),
                "gameKills": None,
                "won": winner_side == "home",
                "picks": home_picks,
                "bans": home_bans,
                "roleSource": "leaguepedia-pick-order",
            },
            "away": {
                "name": away["name"],
                "score": away.get("score"),
                "gameKills": None,
                "won": winner_side == "away",
                "picks": away_picks,
                "bans": away_bans,
                "roleSource": "leaguepedia-pick-order",
            },
            "source": {
                "kind": "leaguepedia",
                "label": "Leaguepedia archive",
                "url": archive["sourceUrl"],
                "note": (
                    "The market no longer serves this finished game's draft; "
                    "picks come from Leaguepedia's public scoreboard archive "
                    "and are ordered by role."
                ),
                "matchId": selected_match_id,
                "fetchedAt": _now_iso(),
                "winnerSide": winner_side,
            },
            "warnings": warnings,
        }

    @staticmethod
    def _archive_game_number(
        row: Mapping[str, Any], group: Sequence[Mapping[str, Any]]
    ) -> int | None:
        value = _int_or_none(row.get("N GameInMatch") or row.get("N_GameInMatch"))
        if value is not None:
            return value
        game_id = str(row.get("GameId") or "")
        match = re.search(r"_(\d+)$", game_id)
        if match:
            return int(match.group(1))
        ordered = list(group)
        try:
            return ordered.index(row) + 1
        except ValueError:
            return None

    @staticmethod
    def _archive_orientation(
        row: Mapping[str, Any],
        home: Mapping[str, Any],
        away: Mapping[str, Any],
    ) -> str | None:
        if _team_names_match(row.get("Team1"), home.get("name")) and _team_names_match(
            row.get("Team2"), away.get("name")
        ):
            return "normal"
        if _team_names_match(row.get("Team2"), home.get("name")) and _team_names_match(
            row.get("Team1"), away.get("name")
        ):
            return "flipped"
        return None

    def _archive_picks(
        self,
        model: DraftModel,
        picks: Sequence[str],
        players: Sequence[str],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        result = []
        for slot, champion in enumerate(picks[:5]):
            player = players[slot] if slot < len(players) else None
            result.append(
                self._resolve_pick(model, champion, None, slot, player, warnings)
            )
        return result

    def _archive_bans(
        self,
        model: DraftModel,
        bans: Sequence[str],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        result = []
        for ban in bans[:5]:
            pick = self._resolve_pick(model, ban, None, None, None, warnings)
            result.append(
                {
                    "champion": pick["champion"],
                    "name": pick.get("name"),
                    "resolved": pick["resolved"],
                }
            )
        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_payload(path: str) -> Any:
    try:
        if path == "-":
            text = sys.stdin.read()
        else:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
    except OSError as error:
        raise InputError(f"cannot read {path}: {error}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise InputError(f"invalid JSON in {path}: {error}") from error


def _print_pretty(result: Mapping[str, Any]) -> None:
    model = result["model"]
    prediction = result["prediction"]
    print(
        "DraftGap draft model | current patch "
        f"{model['currentPatch']['version']} @ {model['currentPatch']['date']} | "
        f"30-day @ {model['thirtyDay']['date']}"
    )
    config = model["config"]
    print(
        f"risk {config['riskLevel']} (prior {config['priorGames']:g} games) | "
        f"{model['currentPatch']['champions']} champions"
    )
    print()
    print(
        f"ALLY     {prediction['allyWinrateText']}%   "
        f"(champions {prediction['ally']['championWinrateText']} | "
        f"matchups {prediction['ally']['matchupWinrateText']} | "
        f"duos {prediction['ally']['duoWinrateText']})"
    )
    print(
        f"OPPONENT {prediction['opponentWinrateText']}%   "
        f"(champions {prediction['opponent']['championWinrateText']} | "
        f"matchups {prediction['opponent']['matchupWinrateText']} | "
        f"duos {prediction['opponent']['duoWinrateText']})"
    )
    print()

    for side, title in (("allies", "ALLY OVERVIEW"), ("opponents", "OPPONENT OVERVIEW")):
        breakdown = result["breakdown"][side]
        print(title)
        print(
            f"{'ROLE':10} {'CHAMPION':16} {'BASE':>7} {'MATCHUP':>8} "
            f"{'DUO':>7} {'TOTAL':>7}"
        )
        inferred_keys = {
            entry["championKey"]
            for entry in result["draft"][side]
            if entry["roleInferred"]
        }
        for row in breakdown["rows"]:
            inferred = "*" if row["championKey"] in inferred_keys else " "
            print(
                f"{row['roleName']:10} "
                f"{(row['name'] + inferred)[:16]:16} "
                f"{row['baseText']:>7} {row['matchupText']:>8} "
                f"{row['duoText']:>7} {row['totalText']:>7}"
            )
        totals = breakdown["totals"]
        print(
            f"{'':10} {'':16} {totals['baseText']:>7} "
            f"{totals['matchupText']:>8} {totals['duoText']:>7} "
            f"{totals['totalText']:>7}"
        )
        print()

    for side, title in (("allies", "TOP ALLY SUGGESTIONS"), ("opponents", "TOP OPPONENT SUGGESTIONS")):
        suggestions = result["suggestions"][side]
        if not suggestions:
            continue
        print(title)
        for index, item in enumerate(suggestions, 1):
            print(
                f"{index:2}. {item['name']:18} {item['roleName']:8} "
                f"{item['winrateText']:>6}%"
            )
        print()

    scaling = result.get("scaling")
    if scaling:
        print("SCALING (team winrate normalized by game time)")
        print(f"{'TIME':8} {'ALLY':>7} {'OPPONENT':>9}")
        for ally, opponent in zip(scaling["allies"], scaling["opponents"]):
            print(
                f"{ally['label']:8} "
                f"{ally['winrateText']:>7} "
                f"{opponent['winrateText']:>9}"
            )
        print()

    warnings = result.get("warnings") or []
    if warnings:
        print("WARNINGS")
        for warning in warnings:
            print(f"- {warning}")


def _serve(args: argparse.Namespace, model: DraftModel) -> None:
    host = args.host
    port = args.port
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    try:
        with open(os.path.join(web_dir, "index.html"), "rb") as handle:
            index_html = handle.read()
        static_files: dict[str, tuple[bytes, str]] = {}
        for route, (relative, content_type) in {
            "/assets/app.css": ("assets/app.css", "text/css; charset=utf-8"),
            "/assets/ui.css": ("assets/ui.css", "text/css; charset=utf-8"),
            "/assets/app.js": ("assets/app.js", "application/javascript; charset=utf-8"),
            "/assets/favicon.ico": ("assets/favicon.ico", "image/x-icon"),
            "/fonts/Oswald-VariableFont_wght.ttf": (
                "fonts/Oswald-VariableFont_wght.ttf",
                "font/ttf",
            ),
            "/fonts/OpenSans-VariableFont_wdth,wght.ttf": (
                "fonts/OpenSans-VariableFont_wdth,wght.ttf",
                "font/ttf",
            ),
        }.items():
            path = os.path.join(web_dir, *relative.split("/"))
            with open(path, "rb") as handle:
                static_files[route] = (handle.read(), content_type)
    except OSError as error:
        raise InputError(f"cannot load web assets from {web_dir}: {error}") from error

    store = _ModelStore(
        args.data_dir, model, refresh_interval=args.refresh_interval
    )
    if args.auto_refresh:
        store.refresh_once()
    store.start()
    upstream_proxy = (
        args.proxy
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
    )
    market_service = _MarketService(
        store.get,
        proxy=upstream_proxy,
        timeout=args.market_timeout,
    )

    class Handler(BaseHTTPRequestHandler):
        server_version = "DraftGapModel/1"

        def log_message(self, format: str, *values: Any) -> None:
            sys.stderr.write(
                "%s - - [%s] %s\n"
                % (self.address_string(), self.log_date_time_string(), format % values)
            )

        def _cors_origin(self) -> str | None:
            allowed = args.cors
            origin = self.headers.get("Origin")
            if not allowed or not origin:
                return None
            if "*" in allowed:
                return "*"
            return origin if origin in allowed else None

        def _cors_headers(self) -> None:
            origin = self._cors_origin()
            if origin is None:
                return
            self.send_header("Access-Control-Allow-Origin", origin)
            if origin != "*":
                self.send_header("Vary", "Origin")
            if self.command == "OPTIONS":
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Max-Age", "86400")

        def _send(
            self,
            status: int,
            body: bytes,
            content_type: str,
            extra_headers: Mapping[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._cors_headers()
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def _json(
            self,
            status: int,
            payload: Any,
            extra_headers: Mapping[str, str] | None = None,
        ) -> None:
            body = json.dumps(
                payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            self._send(
                status,
                body,
                "application/json; charset=utf-8",
                extra_headers,
            )

        def _error(
            self,
            status: int,
            code: str,
            message: str,
            extra_headers: Mapping[str, str] | None = None,
        ) -> None:
            self._json(
                status,
                {"error": message, "code": code},
                extra_headers,
            )

        def do_OPTIONS(self) -> None:  # noqa: N802 (http.server API)
            self.send_response(204)
            self.send_header("Allow", "GET, POST, OPTIONS")
            self._cors_headers()
            self.end_headers()

        def _market_get(self) -> None:
            parsed = urllib.parse.urlsplit(self.path)
            params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            first = lambda name: (params.get(name) or [""])[0]
            try:
                if parsed.path == "/api/market/matches":
                    limit_raw = first("limit") or "5"
                    try:
                        limit = int(limit_raw)
                    except ValueError:
                        raise _MarketError(
                            400, "invalid_limit", "limit must be an integer"
                        )
                    if not 1 <= limit <= 40:
                        raise _MarketError(
                            400, "invalid_limit", "limit must be between 1 and 40"
                        )
                    page_raw = first("page") or "1"
                    try:
                        page = int(page_raw)
                    except ValueError:
                        raise _MarketError(
                            400, "invalid_page", "page must be an integer"
                        )
                    if page < 1:
                        raise _MarketError(
                            400, "invalid_page", "page must be at least 1"
                        )
                    refresh = first("refresh").lower() in ("1", "true", "yes")
                    self._json(
                        200,
                        market_service.matches(limit, page, refresh=refresh),
                    )
                    return
                if parsed.path == "/api/market/match":
                    slug = first("slug")
                    if not slug:
                        raise _MarketError(
                            400, "missing_slug", "slug query parameter is required"
                        )
                    self._json(200, market_service.match(slug))
                    return
                if parsed.path == "/api/market/lineup":
                    slug = first("slug")
                    if not slug:
                        raise _MarketError(
                            400, "missing_slug", "slug query parameter is required"
                        )
                    game_raw = first("game")
                    if not game_raw:
                        raise _MarketError(
                            400, "missing_game", "game query parameter is required"
                        )
                    try:
                        game = int(game_raw)
                    except ValueError:
                        raise _MarketError(
                            400, "invalid_game", "game must be an integer"
                        )
                    self._json(200, market_service.lineup(slug, game))
                    return
                self._error(404, "not_found", "not found")
            except _MarketError as error:
                self._json(error.status, error.payload())
            except Exception as error:  # keep upstream internals out of responses
                sys.stderr.write(
                    f"polymarket request failed: {type(error).__name__}\n"
                )
                self._error(500, "internal_error", "Market request failed")

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            if self.path.startswith("/api/market/"):
                self._market_get()
                return
            if self.path in ("/", "/index.html"):
                self._send(200, index_html, "text/html; charset=utf-8")
                return
            if self.path in static_files:
                body, content_type = static_files[self.path]
                self._send(200, body, content_type)
                return
            if self.path == "/health":
                health = store.snapshot()
                health["ok"] = True
                self._json(200, health)
                return
            if self.path == "/api/bootstrap":
                self._json(200, store.ui_payload())
                return
            if self.path == "/predict":
                self._error(
                    405,
                    "method_not_allowed",
                    "use POST /predict",
                    {"Allow": "POST, OPTIONS"},
                )
                return
            self._error(404, "not_found", "not found")

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/refresh":
                threading.Thread(
                    target=store.refresh_once, name="refresh-request", daemon=True
                ).start()
                self._json(200, {"ok": True, "refreshing": True})
                return
            if self.path != "/predict":
                self._error(404, "not_found", "not found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0:
                self._error(400, "empty_body", "empty request body")
                return
            if length > 2 * 1024 * 1024:
                self._error(413, "payload_too_large", "request body too large")
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                self._error(400, "invalid_json", f"invalid JSON: {error}")
                return
            try:
                result = store.get().analyze(payload)
            except InputError as error:
                self._error(400, "invalid_input", str(error))
                return
            except Exception as error:  # keep internals out of the response
                sys.stderr.write(f"prediction failed: {error!r}\n")
                self._error(500, "internal_error", "prediction failed")
                return
            try:
                body = json.dumps(
                    result,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError) as error:
                sys.stderr.write(f"serialization failed: {error!r}\n")
                self._error(
                    500, "serialization_error", "result could not be serialized"
                )
                return
            self._send(200, body, "application/json; charset=utf-8")

    server = ThreadingHTTPServer((host, port), Handler)
    actual_host, actual_port = server.server_address[:2]
    display_host = f"[{actual_host}]" if ":" in str(actual_host) else actual_host
    active_model = store.get()
    print(
        f"DraftGap model server on http://{display_host}:{actual_port}/ "
        f"(dataset {active_model.current.version} @ {active_model.current.date})",
        file=sys.stderr,
    )
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "warning: listening on a non-loopback address without authentication",
            file=sys.stderr,
        )
    if args.cors and "*" in args.cors:
        print(
            "warning: --cors '*' allows any website to call this service",
            file=sys.stderr,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        store.stop()
        server.server_close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reproducible DraftGap LoL draft winrate model. "
            "Reads a JSON draft, prints the prediction, or serves a local page."
        )
    )
    parser.add_argument("--draft", help="draft JSON file, or - for stdin")
    parser.add_argument(
        "--data-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
        help="directory containing current-patch.json and 30-days.json",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="re-download both datasets before doing anything else",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="download missing datasets and exit",
    )
    parser.add_argument(
        "--info", action="store_true", help="print dataset/model metadata and exit"
    )
    parser.add_argument(
        "--suggestions",
        type=int,
        default=None,
        metavar="N",
        help="include the top N suggestions per side (overrides the JSON value)",
    )
    parser.add_argument(
        "--risk",
        default=None,
        choices=sorted(RISK_PRIOR),
        help="DraftGap risk level (default: medium / 1000 prior games)",
    )
    parser.add_argument(
        "--prior-games",
        type=float,
        default=None,
        help="override the risk-level prior pseudo-games (extension)",
    )
    parser.add_argument(
        "--ignore-champion-winrates",
        action="store_true",
        help="hide champion base winrates from the calculation",
    )
    parser.add_argument(
        "--min-games",
        type=float,
        default=None,
        help="minimum weekly games for suggestions (default: 1000)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "pretty"),
        default="json",
        help="output format (default: json)",
    )
    parser.add_argument(
        "--compact", action="store_true", help="compact JSON output"
    )
    parser.add_argument(
        "--serve", action="store_true", help="serve the one-click prediction page"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--refresh-interval",
        type=float,
        default=300.0,
        metavar="SECONDS",
        help="check upstream dataset ETags in the background (0 disables; default 300)",
    )
    parser.add_argument(
        "--no-auto-refresh",
        dest="auto_refresh",
        action="store_false",
        help="do not check for a newer dataset on startup",
    )
    parser.add_argument(
        "--cors",
        action="append",
        default=None,
        metavar="ORIGIN",
        help=(
            "allow browser calls from ORIGIN (repeatable; use '*' for any "
            "origin; default: same-origin only)"
        ),
    )
    parser.add_argument(
        "--proxy",
        default=None,
        metavar="URL",
        help=(
            "HTTP(S) proxy for market and Leaguepedia calls "
            "(default: HTTPS_PROXY or HTTP_PROXY)"
        ),
    )
    parser.add_argument(
        "--market-timeout",
        type=float,
        default=20.0,
        metavar="SECONDS",
        help="upstream timeout for market and Leaguepedia (default: 20)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="show tracebacks for unexpected errors"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.draft and not args.serve and not args.download and not args.info:
        parser.error("one of --draft, --serve, --download, or --info is required")

    if args.download:
        try:
            ensure_datasets(args.data_dir, refresh=args.refresh)
        except (InputError, OSError, urllib.error.URLError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        print("datasets ready", file=sys.stderr)
        return 0

    try:
        model = load_model(args.data_dir, refresh=args.refresh)
    except (InputError, OSError, urllib.error.URLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.info:
        print(
            json.dumps(
                {
                    "currentPatch": {
                        "version": model.current.version,
                        "date": model.current.date,
                        "champions": len(model.current.champions),
                    },
                    "thirtyDay": {
                        "version": model.thirty.version,
                        "date": model.thirty.date,
                        "champions": len(model.thirty.champions),
                    },
                    "riskLevels": RISK_PRIOR,
                    "sourceBundle": MODEL_BUNDLE,
                    "sourceBundleSha256": MODEL_BUNDLE_SHA256,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.serve:
        if not 0 <= args.port <= 65535:
            print("error: --port must be between 0 and 65535", file=sys.stderr)
            return 2
        try:
            _serve(args, model)
        except OSError as error:
            print(f"error: cannot listen on {args.host}:{args.port}: {error}", file=sys.stderr)
            return 2
        return 0

    if args.suggestions is not None and args.suggestions < 0:
        print("error: --suggestions must be >= 0", file=sys.stderr)
        return 2
    if args.min_games is not None and args.min_games < 0:
        print("error: --min-games must be >= 0", file=sys.stderr)
        return 2
    if args.prior_games is not None and args.prior_games <= 0:
        print("error: --prior-games must be > 0", file=sys.stderr)
        return 2

    try:
        payload = _load_payload(args.draft)
        override: dict[str, Any] = {}
        if args.suggestions is not None:
            override["suggestions"] = min(args.suggestions, 100)
        if args.min_games is not None:
            override["minGames"] = args.min_games
        if args.risk is not None:
            override["riskLevel"] = args.risk
        if args.prior_games is not None:
            override["priorGames"] = args.prior_games
        if args.ignore_champion_winrates:
            override["ignoreChampionWinrates"] = True
        result = model.analyze(payload, override)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        if args.debug:
            raise
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.format == "pretty":
        _print_pretty(result)
    else:
        indent = None if args.compact else 2
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                indent=indent,
                separators=(",", ":") if args.compact else None,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
