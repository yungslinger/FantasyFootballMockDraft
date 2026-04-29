from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ScoringPreset = Literal["standard", "half_ppr", "ppr"]


class StartersConfig(BaseModel):
    qb: int = 1
    rb: int = 2
    wr: int = 2
    te: int = 1
    flex: int = 1
    superflex: int = 0
    k: int = 0
    dst: int = 0


class LeagueConfig(BaseModel):
    teams: int = Field(default=12, ge=4, le=16)
    rounds: int | None = Field(default=None, ge=8, le=30)
    bench: int = Field(default=7, ge=0, le=20)
    ai_think_seconds: float = Field(default=3.0, ge=0.0, le=10.0)
    scoring_preset: ScoringPreset = "ppr"
    starters: StartersConfig = Field(default_factory=StartersConfig)

    @model_validator(mode="after")
    def derive_rounds(self) -> "LeagueConfig":
        starters_total = (
            self.starters.qb
            + self.starters.rb
            + self.starters.wr
            + self.starters.te
            + self.starters.flex
            + self.starters.superflex
            + self.starters.k
            + self.starters.dst
        )
        computed = starters_total + self.bench
        computed = max(8, min(30, int(computed)))
        if self.rounds is None:
            self.rounds = computed
        return self


class PlayerPoolItem(BaseModel):
    player_key: str
    player_name: str
    position: str
    team: str
    nflreadpy_id: str | None = None
    headshot_url: str | None = None
    bye_week: int | None = None
    adp: float
    rank: int
    fpts: float | None = None
    status_tag: str | None = None
    injury_note: str | None = None


class DraftPick(BaseModel):
    pick_no: int
    round_no: int
    team_slot: int
    player_key: str
    player_name: str
    position: str
    team: str
    bye_week: int | None = None
    is_cpu: bool
    confidence_bucket: str
    drafted_at: datetime


class RosterState(BaseModel):
    team_slot: int
    counts: dict[str, int]
    total_players: int


class RoomState(BaseModel):
    room_id: str
    league: LeagueConfig
    user_slot: int
    pick_no: int
    current_slot: int
    complete: bool
    total_picks: int
    picks: list[DraftPick]
    rosters: list[RosterState]


class CreateRoomRequest(BaseModel):
    league: LeagueConfig = Field(default_factory=LeagueConfig)
    user_slot: int = Field(default=1, ge=1, le=16)
    seed: int | None = None
    ranking_file_path: str | None = None


class CreateRoomResponse(BaseModel):
    state: RoomState
    available_players: int


class PlayerQueryResponse(BaseModel):
    players: list[PlayerPoolItem]
    total: int


class RecommendationItem(BaseModel):
    player: PlayerPoolItem
    score: float
    rationale: str


class RecommendationResponse(BaseModel):
    room_id: str
    pick_no: int
    recommendations: list[RecommendationItem]


class MakePickRequest(BaseModel):
    player_key: str


class OverrideCpuPickRequest(BaseModel):
    pick_no: int = Field(ge=1)
    player_key: str


class SimulateResponse(BaseModel):
    state: RoomState
    cpu_picks_made: int


class GameLogEntry(BaseModel):
    week: int
    opponent: str | None = None
    fantasy_points: float | None = None
    passing_completions: float | None = None
    passing_attempts: float | None = None
    passing_yards: float | None = None
    passing_tds: float | None = None
    interceptions: float | None = None
    rushing_attempts: float | None = None
    rushing_yards: float | None = None
    rushing_tds: float | None = None
    receptions: float | None = None
    targets: float | None = None
    receiving_yards: float | None = None
    receiving_tds: float | None = None
    misc_tds: float | None = None
    field_goals_made: float | None = None
    field_goals_attempted: float | None = None
    extra_points_made: float | None = None
    sacks: float | None = None
    fumble_recoveries: float | None = None
    defensive_interceptions: float | None = None
    defensive_tds: float | None = None
    safeties: float | None = None
    points_allowed: float | None = None


class PlayerCardResponse(BaseModel):
    player_key: str
    player_name: str
    position: str
    team: str
    headshot_url: str | None = None
    season: int
    scoring_preset: ScoringPreset
    status_tag: str | None = None
    injury_note: str | None = None
    adp: float | None = None
    fpts: float | None = None
    game_log: list[GameLogEntry]

