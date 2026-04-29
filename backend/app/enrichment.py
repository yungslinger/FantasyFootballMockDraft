from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from .schemas import GameLogEntry, PlayerCardResponse, PlayerPoolItem, ScoringPreset

try:
    import nflreadpy as nfl
except ImportError:  # pragma: no cover
    nfl = None


def _clean_name(value: str) -> str:
    s = str(value or "").lower().strip()
    s = re.sub(r"[']", "", s)
    s = re.sub(r"[^a-z0-9.\s-]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _series(df: pd.DataFrame, col: str, default: str = "") -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def _to_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_stat(row: pd.Series, *names: str) -> float | None:
    for name in names:
        if name in row.index:
            value = _to_float(row.get(name))
            if value is not None:
                return value
    return None


def _sum_stats(row: pd.Series, *names: str) -> float | None:
    total = 0.0
    seen = False
    for name in names:
        if name in row.index:
            value = _to_float(row.get(name))
            if value is not None:
                seen = True
                total += value
    if not seen:
        return None
    return total


def _fantasy_points_row(row: pd.Series, scoring_preset: ScoringPreset) -> float:
    reception_mult = 1.0 if scoring_preset == "ppr" else 0.5 if scoring_preset == "half_ppr" else 0.0

    # Kicking: nflreadpy uses fg_made/fg_att plus distance buckets, and pat_made/pat_att.
    # Default ESPN-like scoring:
    # - FG: 3 (0-39), 4 (40-49), 5 (50+)
    # - Missed FG: -1
    # - PAT made: +1, PAT missed: -1
    fg_0_39 = _sum_stats(row, "fg_made_0_19", "fg_made_20_29", "fg_made_30_39") or 0.0
    fg_40_49 = _pick_stat(row, "fg_made_40_49") or 0.0
    fg_50_plus = _sum_stats(row, "fg_made_50_59", "fg_made_60_", "fg_made_60_plus") or 0.0
    fg_made = _pick_stat(row, "fg_made", "field_goals_made", "fgm") or 0.0
    fg_att = _pick_stat(row, "fg_att", "field_goals_attempted", "fga") or 0.0
    fg_missed = _pick_stat(row, "fg_missed") or 0.0
    if fg_att <= 0 and fg_missed > 0 and fg_made > 0:
        fg_att = fg_made + fg_missed
    if fg_missed <= 0 and fg_att > 0:
        fg_missed = max(0.0, fg_att - fg_made)

    pat_made = _pick_stat(row, "pat_made", "extra_points_made", "xpm", "patmade") or 0.0
    pat_att = _pick_stat(row, "pat_att") or 0.0
    pat_missed = _pick_stat(row, "pat_missed") or 0.0
    if pat_missed <= 0 and pat_att > 0:
        pat_missed = max(0.0, pat_att - pat_made)

    # If distance buckets are present, prefer them; otherwise treat FG as flat 3 points.
    has_fg_buckets = (fg_0_39 + fg_40_49 + fg_50_plus) > 0
    kicking_points = 0.0
    if has_fg_buckets:
        kicking_points += 3.0 * fg_0_39 + 4.0 * fg_40_49 + 5.0 * fg_50_plus
        # Account for any remaining makes not represented in buckets (rare schema mismatch).
        bucket_total = fg_0_39 + fg_40_49 + fg_50_plus
        if fg_made > bucket_total:
            kicking_points += 3.0 * (fg_made - bucket_total)
    else:
        kicking_points += 3.0 * fg_made
    kicking_points -= 1.0 * fg_missed
    kicking_points += 1.0 * pat_made
    kicking_points -= 1.0 * pat_missed

    return (
        0.04 * (_pick_stat(row, "passing_yards") or 0.0)
        + 4.0 * (_pick_stat(row, "passing_tds") or 0.0)
        - 2.0 * (_pick_stat(row, "interceptions") or 0.0)
        + 0.10 * (_pick_stat(row, "rushing_yards") or 0.0)
        + 6.0 * (_pick_stat(row, "rushing_tds") or 0.0)
        + reception_mult * (_pick_stat(row, "receptions") or 0.0)
        + 0.10 * (_pick_stat(row, "receiving_yards") or 0.0)
        + 6.0 * (_pick_stat(row, "receiving_tds") or 0.0)
        + 6.0
        * (
            _sum_stats(
                row,
                "misc_tds",
                "special_teams_tds",
                "return_tds",
                "kick_return_tds",
                "punt_return_tds",
            )
            or 0.0
        )
        - 2.0 * (_pick_stat(row, "fumbles_lost") or 0.0)
        + kicking_points
        + 1.0 * (_pick_stat(row, "sacks", "def_sacks") or 0.0)
        + 2.0 * (_pick_stat(row, "fumble_recoveries", "def_fumble_recoveries") or 0.0)
        + 2.0 * (_pick_stat(row, "defensive_interceptions", "interceptions_gained", "def_interceptions") or 0.0)
        + 6.0 * (_pick_stat(row, "defensive_tds", "def_tds", "dst_tds") or 0.0)
        + 2.0 * (_pick_stat(row, "safeties", "def_safeties") or 0.0)
    )


@dataclass
class PlayerEnrichmentService:
    def build_player_card(
        self,
        *,
        player: PlayerPoolItem,
        season: int,
        scoring_preset: ScoringPreset,
    ) -> PlayerCardResponse:
        if nfl is None:
            return PlayerCardResponse(
                player_key=player.player_key,
                player_name=player.player_name,
                position=player.position,
                team=player.team,
                headshot_url=player.headshot_url,
                season=season,
                scoring_preset=scoring_preset,
                status_tag=player.status_tag,
                injury_note=player.injury_note,
                adp=player.adp,
                fpts=player.fpts,
                game_log=[],
            )

        game_log = self._game_log(player=player, season=season, scoring_preset=scoring_preset)
        status_tag, injury_note = self._injury_tag(player=player, season=season)
        return PlayerCardResponse(
            player_key=player.player_key,
            player_name=player.player_name,
            position=player.position,
            team=player.team,
            headshot_url=player.headshot_url,
            season=season,
            scoring_preset=scoring_preset,
            status_tag=status_tag or player.status_tag,
            injury_note=injury_note or player.injury_note,
            adp=player.adp,
            fpts=player.fpts,
            game_log=game_log,
        )

    def _game_log(self, *, player: PlayerPoolItem, season: int, scoring_preset: ScoringPreset) -> list[GameLogEntry]:
        if player.position == "DST":
            return self._dst_game_log(player=player, season=season)

        try:
            stats = nfl.load_player_stats([season]).to_pandas()
        except Exception:
            return []
        if stats.empty:
            return []
        if "season_type" in stats.columns:
            stats = stats[_series(stats, "season_type").astype(str).str.upper().isin(["REG", "REGULAR"])].copy()
        stats["week"] = pd.to_numeric(_series(stats, "week", "0"), errors="coerce").fillna(0).astype(int)
        stats = stats[stats["week"] > 0].copy()
        if stats.empty:
            return []

        stats["player_name_key"] = _series(stats, "player_name", "").map(_clean_name)
        stats["position_key"] = _series(stats, "position", "").astype(str).str.upper()
        team_col = _series(stats, "recent_team", "").astype(str)
        fallback_team_col = _series(stats, "team", "").astype(str)
        stats["team_key"] = team_col.where(team_col.str.strip() != "", fallback_team_col).str.upper().str.strip()
        stats["player_id_key"] = _series(stats, "player_id", "").astype(str).str.strip()

        target_name_key = _clean_name(player.player_name)
        subset = pd.DataFrame(columns=stats.columns)

        if player.nflreadpy_id:
            player_id = player.nflreadpy_id.strip()
            if player.position == "DST":
                dst_team = player.team
                if player_id.upper().startswith("DST_"):
                    dst_team = player_id.split("_", 1)[1].upper().strip() or dst_team
                subset = stats[stats["team_key"] == dst_team].copy()
                if not subset.empty and (subset["position_key"] == "DST").any():
                    subset = subset[subset["position_key"] == "DST"].copy()
            else:
                subset = stats[stats["player_id_key"] == player_id].copy()

        if subset.empty:
            subset = stats[
                (stats["position_key"] == player.position)
                & (stats["team_key"] == player.team)
                & (stats["player_name_key"] == target_name_key)
            ].copy()
        if subset.empty:
            subset = stats[
                (stats["position_key"] == player.position)
                & (stats["player_name_key"] == target_name_key)
            ].copy()
        if subset.empty:
            return []

        subset = subset.sort_values("week", ascending=True)

        # Build schedule-backed weeks (1-18) so BYE and no-stats weeks show up.
        schedule = self._team_schedule(season=season, team=player.team)
        if schedule:
            # Index player stats rows by week for quick lookup.
            by_week: dict[int, pd.Series] = {}
            for _, row in subset.iterrows():
                wk = int(row.get("week", 0) or 0)
                if wk > 0 and wk not in by_week:
                    by_week[wk] = row
            out: list[GameLogEntry] = []
            for wk in range(1, 19):
                opp = schedule.get(wk, "BYE")
                row = by_week.get(wk)
                if row is None:
                    out.append(GameLogEntry(week=wk, opponent=opp, fantasy_points=None))
                    continue
                out.append(self._row_to_entry(row=row, week=wk, opponent=opp, scoring_preset=scoring_preset))
            return out

        out: list[GameLogEntry] = []
        for _, row in subset.iterrows():
            wk = int(row.get("week", 0) or 0)
            out.append(
                self._row_to_entry(
                    row=row,
                    week=wk,
                    opponent=str(row.get("opponent_team") or row.get("opponent") or "").strip() or None,
                    scoring_preset=scoring_preset,
                )
            )
        return out

    @staticmethod
    def _dst_points_allowed_bonus(points_allowed: int | float | None) -> float:
        if points_allowed is None:
            return 0.0
        try:
            pa = int(points_allowed)
        except Exception:
            return 0.0
        if pa == 0:
            return 5.0
        if 1 <= pa <= 6:
            return 4.0
        if 7 <= pa <= 13:
            return 3.0
        if 14 <= pa <= 17:
            return 1.0
        if 18 <= pa <= 27:
            return 0.0
        if 28 <= pa <= 34:
            return -1.0
        if 35 <= pa <= 45:
            return -3.0
        return -5.0

    def _dst_fantasy_points_row(self, row: pd.Series, *, points_allowed: int | None) -> float:
        sacks = _pick_stat(row, "def_sacks") or 0.0
        interceptions = _pick_stat(row, "def_interceptions") or 0.0
        fumble_recoveries = _pick_stat(row, "fumble_recovery_opp") or 0.0
        # TD components: defensive + special teams + fumble recovery TDs (if present).
        defensive_tds = _pick_stat(row, "def_tds") or 0.0
        special_teams_tds = _pick_stat(row, "special_teams_tds") or 0.0
        fumble_recovery_tds = _pick_stat(row, "fumble_recovery_tds") or 0.0
        tds = defensive_tds + special_teams_tds + fumble_recovery_tds
        safeties = _pick_stat(row, "def_safeties") or 0.0
        blocked_kicks = (_pick_stat(row, "fg_blocked") or 0.0) + (_pick_stat(row, "pat_blocked") or 0.0)
        return (
            1.0 * sacks
            + 2.0 * interceptions
            + 2.0 * fumble_recoveries
            + 6.0 * tds
            + 2.0 * safeties
            + 2.0 * blocked_kicks
            + self._dst_points_allowed_bonus(points_allowed)
        )

    def _dst_game_log(self, *, player: PlayerPoolItem, season: int) -> list[GameLogEntry]:
        if nfl is None:
            return []

        dst_team = player.team
        if player.nflreadpy_id and str(player.nflreadpy_id).upper().startswith("DST_"):
            dst_team = str(player.nflreadpy_id).split("_", 1)[1].upper().strip() or dst_team

        schedule = self._team_schedule(season=season, team=dst_team)
        schedule_scores = self._team_schedule_scores(season=season, team=dst_team)

        try:
            team_stats = nfl.load_team_stats([season], summary_level="week").to_pandas()
        except Exception:
            team_stats = pd.DataFrame()

        if not team_stats.empty:
            team_stats = team_stats[team_stats.get("season_type", "").astype(str).str.upper().isin(["REG", "REGULAR"])].copy()
            team_stats["week"] = pd.to_numeric(_series(team_stats, "week", "0"), errors="coerce").fillna(0).astype(int)
            team_stats["team_key"] = _series(team_stats, "team", "").astype(str).str.upper().str.strip()
            team_stats = team_stats[
                (team_stats["team_key"] == str(dst_team).upper().strip())
                & (team_stats["week"].between(1, 18))
            ].copy()

        # Index by week (one row per team/week).
        by_week: dict[int, pd.Series] = {}
        if not team_stats.empty:
            for _, row in team_stats.iterrows():
                wk = int(row.get("week", 0) or 0)
                if 1 <= wk <= 18 and wk not in by_week:
                    by_week[wk] = row

        out: list[GameLogEntry] = []
        for wk in range(1, 19):
            opp = schedule.get(wk, "BYE")
            points_allowed = schedule_scores.get(wk)
            row = by_week.get(wk)
            if row is None:
                out.append(GameLogEntry(week=wk, opponent=opp, fantasy_points=None, points_allowed=points_allowed))
                continue
            out.append(
                GameLogEntry(
                    week=wk,
                    opponent=opp,
                    fantasy_points=round(self._dst_fantasy_points_row(row, points_allowed=points_allowed), 2),
                    sacks=_pick_stat(row, "def_sacks"),
                    defensive_interceptions=_pick_stat(row, "def_interceptions"),
                    fumble_recoveries=_pick_stat(row, "fumble_recovery_opp"),
                    defensive_tds=_pick_stat(row, "def_tds"),
                    safeties=_pick_stat(row, "def_safeties"),
                    points_allowed=float(points_allowed) if points_allowed is not None else None,
                )
            )
        return out

    def _row_to_entry(
        self,
        *,
        row: pd.Series,
        week: int,
        opponent: str | None,
        scoring_preset: ScoringPreset,
    ) -> GameLogEntry:
        return GameLogEntry(
            week=week,
            opponent=opponent,
            fantasy_points=round(_fantasy_points_row(row, scoring_preset), 2),
            passing_completions=_pick_stat(row, "completions", "passing_completions"),
            passing_attempts=_pick_stat(row, "attempts", "passing_attempts"),
            passing_yards=_pick_stat(row, "passing_yards"),
            passing_tds=_pick_stat(row, "passing_tds"),
            interceptions=_pick_stat(row, "interceptions"),
            rushing_attempts=_pick_stat(row, "carries", "rushing_attempts"),
            rushing_yards=_pick_stat(row, "rushing_yards"),
            rushing_tds=_pick_stat(row, "rushing_tds"),
            receptions=_pick_stat(row, "receptions"),
            targets=_pick_stat(row, "targets"),
            receiving_yards=_pick_stat(row, "receiving_yards"),
            receiving_tds=_pick_stat(row, "receiving_tds"),
            misc_tds=_sum_stats(
                row,
                "misc_tds",
                "special_teams_tds",
                "return_tds",
                "kick_return_tds",
                "punt_return_tds",
            ),
            field_goals_made=_pick_stat(row, "fg_made", "field_goals_made", "fgm"),
            field_goals_attempted=_pick_stat(row, "fg_att", "field_goals_attempted", "fga"),
            extra_points_made=_pick_stat(row, "pat_made", "extra_points_made", "xpm", "patmade"),
            sacks=_pick_stat(row, "sacks", "def_sacks"),
            fumble_recoveries=_pick_stat(row, "fumble_recoveries", "def_fumble_recoveries"),
            defensive_interceptions=_pick_stat(row, "defensive_interceptions", "interceptions_gained", "def_interceptions"),
            defensive_tds=_pick_stat(row, "defensive_tds", "def_tds", "dst_tds"),
            safeties=_pick_stat(row, "safeties", "def_safeties"),
            points_allowed=_pick_stat(row, "points_allowed"),
        )

    def _team_schedule(self, *, season: int, team: str) -> dict[int, str]:
        if nfl is None:
            return {}
        try:
            sched = nfl.load_schedules([season]).to_pandas()
        except Exception:
            return {}
        if sched.empty:
            return {}
        sched = sched[sched.get("game_type", "").astype(str).str.upper().isin(["REG", "REGULAR"])].copy()
        sched["week"] = pd.to_numeric(_series(sched, "week", "0"), errors="coerce").fillna(0).astype(int)
        sched = sched[sched["week"].between(1, 18)].copy()
        if sched.empty:
            return {}
        sched["home_team"] = _series(sched, "home_team", "").astype(str).str.upper().str.strip()
        sched["away_team"] = _series(sched, "away_team", "").astype(str).str.upper().str.strip()
        team_key = str(team or "").upper().strip()

        out: dict[int, str] = {}
        for _, r in sched.iterrows():
            wk = int(r.get("week", 0) or 0)
            if wk <= 0:
                continue
            home = str(r.get("home_team", "") or "").upper().strip()
            away = str(r.get("away_team", "") or "").upper().strip()
            if home == team_key:
                out[wk] = away
            elif away == team_key:
                out[wk] = f"@{home}"
        return out

    def _team_schedule_scores(self, *, season: int, team: str) -> dict[int, int]:
        if nfl is None:
            return {}
        try:
            sched = nfl.load_schedules([season]).to_pandas()
        except Exception:
            return {}
        if sched.empty:
            return {}
        sched = sched[sched.get("game_type", "").astype(str).str.upper().isin(["REG", "REGULAR"])].copy()
        sched["week"] = pd.to_numeric(_series(sched, "week", "0"), errors="coerce").fillna(0).astype(int)
        sched = sched[sched["week"].between(1, 18)].copy()
        if sched.empty:
            return {}
        sched["home_team"] = _series(sched, "home_team", "").astype(str).str.upper().str.strip()
        sched["away_team"] = _series(sched, "away_team", "").astype(str).str.upper().str.strip()

        home_score = pd.to_numeric(_series(sched, "home_score", None), errors="coerce")
        away_score = pd.to_numeric(_series(sched, "away_score", None), errors="coerce")

        team_key = str(team or "").upper().strip()
        out: dict[int, int] = {}
        for idx, r in sched.iterrows():
            wk = int(r.get("week", 0) or 0)
            if wk <= 0:
                continue
            home = str(r.get("home_team", "") or "").upper().strip()
            away = str(r.get("away_team", "") or "").upper().strip()
            if home == team_key:
                val = away_score.loc[idx]
            elif away == team_key:
                val = home_score.loc[idx]
            else:
                continue
            if pd.notna(val):
                out[wk] = int(val)
        return out

    def _injury_tag(self, *, player: PlayerPoolItem, season: int) -> tuple[str | None, str | None]:
        try:
            injuries = nfl.load_injuries(seasons=[season]).to_pandas()
        except Exception:
            return None, None
        if injuries.empty:
            return None, None
        if "report_status" not in injuries.columns:
            return None, None

        full_name_col = _series(injuries, "full_name", "").astype(str)
        player_name_col = _series(injuries, "player_name", "").astype(str)
        injuries["name_key"] = full_name_col.where(full_name_col.str.strip() != "", player_name_col).map(_clean_name)
        target = injuries[injuries["name_key"] == _clean_name(player.player_name)].copy()
        if target.empty:
            return None, None
        target["week"] = pd.to_numeric(_series(target, "week", "0"), errors="coerce").fillna(0)
        target = target.sort_values("week").tail(1)
        row = target.iloc[0]
        status = str(row.get("report_status", "")).strip()
        if not status:
            return None, None
        body_part = str(row.get("injury", "")).strip()
        return status.upper(), body_part or None

