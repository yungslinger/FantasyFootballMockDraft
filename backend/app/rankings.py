from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from .schemas import PlayerPoolItem, ScoringPreset

try:
    import nflreadpy as nfl
except ImportError:  # pragma: no cover
    nfl = None


TEAM_RENAMES = {
    "JAC": "JAX",
    "WSH": "WAS",
    "LA": "LAR",
    "LVR": "LV",
}

_SCHEDULE_CACHE: dict[int, pd.DataFrame] = {}


def _clean_name(value: str) -> str:
    s = str(value or "").strip().lower()
    s = re.sub(r"[']", "", s)
    s = re.sub(r"[^a-z0-9\s.-]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _base_position(value: str) -> str:
    m = re.match(r"([A-Za-z]+)", str(value or "").strip())
    if not m:
        return ""
    return m.group(1).upper()


def _to_player_key(name: str, pos: str, team: str) -> str:
    slug = _clean_name(name).replace(" ", "-")
    return f"{slug}:{pos}:{team}"


def _team_bye_week(*, season: int, team: str) -> int | None:
    """
    Compute bye week from schedules: the first week 1-18 without a game.
    Used as a fallback when the ranking CSV does not include bye weeks.
    """
    if nfl is None:
        return None
    team_key = str(team or "").upper().strip()
    if team_key in {"", "FA", "NAN"}:
        return None
    if season not in _SCHEDULE_CACHE:
        try:
            sched = nfl.load_schedules([season]).to_pandas()
        except Exception:
            sched = pd.DataFrame()
        _SCHEDULE_CACHE[season] = sched
    sched = _SCHEDULE_CACHE.get(season)  # type: ignore[assignment]
    if sched is None or sched.empty:
        return None
    df = sched.copy()
    if "game_type" in df.columns:
        df = df[df["game_type"].astype(str).str.upper().isin(["REG", "REGULAR"])].copy()
    if "week" not in df.columns:
        return None
    df["week"] = pd.to_numeric(df["week"], errors="coerce").fillna(0).astype(int)
    df = df[df["week"].between(1, 18)].copy()
    if df.empty:
        return None
    home = df.get("home_team", "").astype(str).str.upper().str.strip()
    away = df.get("away_team", "").astype(str).str.upper().str.strip()
    played_weeks = set(df.loc[(home == team_key) | (away == team_key), "week"].tolist())
    for wk in range(1, 19):
        if wk not in played_weeks:
            return wk
    return None


@dataclass(frozen=True)
class RankingLoadResult:
    players: list[PlayerPoolItem]
    dropped_rows: int


class FantasyProsRankingRepository:
    def __init__(self, default_csv_path: str | Path) -> None:
        self.default_csv_path = Path(default_csv_path)

    @staticmethod
    def _score_cols(preset: ScoringPreset) -> tuple[str, str]:
        if preset == "standard":
            return "FPTS_STD", "ADP_STD"
        if preset == "half_ppr":
            return "FPTS_HPPR", "ADP_HPPR"
        return "FPTS_PPR", "ADP_PPR"

    def load(
        self,
        *,
        scoring_preset: ScoringPreset,
        csv_path_override: str | None = None,
    ) -> RankingLoadResult:
        path = Path(csv_path_override) if csv_path_override else self.default_csv_path
        if not path.exists():
            raise FileNotFoundError(f"Ranking file not found: {path}")

        df = pd.read_csv(path)
        fpts_col, adp_col = self._score_cols(scoring_preset)
        required = {"Player", "POS", "Team", fpts_col, adp_col}
        if not required.issubset(df.columns):
            missing = sorted(required - set(df.columns))
            raise ValueError(f"Ranking file missing columns: {missing}")

        cleaned = pd.DataFrame()
        cleaned["player_name"] = df["Player"].astype(str).str.strip()
        cleaned["position"] = df["POS"].map(_base_position)
        cleaned["team"] = df["Team"]
        cleaned["team"] = cleaned["team"].where(cleaned["team"].notna(), "FA")
        cleaned["team"] = (
            cleaned["team"].astype(str).str.upper().str.strip().replace(TEAM_RENAMES).replace({"NAN": "FA", "": "FA"})
        )
        cleaned["adp"] = pd.to_numeric(df[adp_col], errors="coerce")
        cleaned["fpts"] = pd.to_numeric(df[fpts_col], errors="coerce")
        cleaned["status_tag"] = ""
        cleaned["injury_note"] = ""
        cleaned["nflreadpy_id"] = (
            df["NFLREADPY_ID"].where(df["NFLREADPY_ID"].notna(), "").astype(str).str.strip()
            if "NFLREADPY_ID" in df.columns
            else ""
        )
        cleaned["headshot_url"] = (
            df["HEADSHOT"].where(df["HEADSHOT"].notna(), "").astype(str).str.strip() if "HEADSHOT" in df.columns else ""
        )
        # Optional bye week (FantasyPros ADP exports include this, but master may not).
        if "Bye" in df.columns:
            cleaned["bye_week"] = pd.to_numeric(df["Bye"], errors="coerce")
        elif "BYE" in df.columns:
            cleaned["bye_week"] = pd.to_numeric(df["BYE"], errors="coerce")
        else:
            cleaned["bye_week"] = pd.NA

        # DST rows sometimes have blank/FA team in projections; derive from NFLREADPY_ID like DST_DET.
        if "nflreadpy_id" in cleaned.columns:
            is_dst = cleaned["position"].astype(str).str.upper().eq("DST")
            dst_id = cleaned["nflreadpy_id"].astype(str).str.upper().str.strip()
            derived = dst_id.where(dst_id.str.startswith("DST_"), "").str.split("_").str[-1]
            needs_team = cleaned["team"].astype(str).str.upper().isin(["", "FA", "NAN"])
            cleaned.loc[is_dst & needs_team & (derived != ""), "team"] = derived

        before = len(cleaned)
        cleaned = cleaned.dropna(subset=["player_name", "position", "adp"]).copy()
        cleaned = cleaned[cleaned["position"].isin(["QB", "RB", "WR", "TE", "K", "DST"])].copy()
        cleaned = cleaned[cleaned["adp"] > 0].copy()
        cleaned = cleaned.sort_values(["adp", "player_name"], ascending=[True, True]).reset_index(drop=True)
        cleaned["rank"] = cleaned.index + 1
        cleaned["player_key"] = cleaned.apply(
            lambda r: _to_player_key(r["player_name"], r["position"], r["team"]),
            axis=1,
        )
        cleaned = cleaned.drop_duplicates(subset=["player_key"], keep="first")

        # Fallback bye weeks via schedules when not provided in the CSV.
        if cleaned["bye_week"].isna().any():
            # Try current-year schedule; if missing, fall back to last year.
            year = int(datetime.now().year)
            seasons = [year, year - 1, 2025]
            for s in seasons:
                if not cleaned["bye_week"].isna().any():
                    break
                if nfl is None:
                    break
                missing_mask = cleaned["bye_week"].isna()
                for idx, row in cleaned.loc[missing_mask, ["team"]].itertuples():  # type: ignore[misc]
                    bye = _team_bye_week(season=s, team=str(row))
                    if bye is not None:
                        cleaned.at[idx, "bye_week"] = bye

        players = [
            PlayerPoolItem(
                player_key=row.player_key,
                player_name=row.player_name,
                position=row.position,
                team=row.team,
                nflreadpy_id=row.nflreadpy_id or None,
                headshot_url=row.headshot_url or None,
                bye_week=int(row.bye_week) if pd.notna(getattr(row, "bye_week", pd.NA)) else None,
                adp=float(row.adp),
                rank=int(row.rank),
                fpts=float(row.fpts) if pd.notna(row.fpts) else None,
                status_tag=row.status_tag or None,
                injury_note=row.injury_note or None,
            )
            for row in cleaned.itertuples(index=False)
        ]
        return RankingLoadResult(players=players, dropped_rows=before - len(cleaned))

