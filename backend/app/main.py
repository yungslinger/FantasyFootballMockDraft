from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .draft_engine import DraftService
from .enrichment import PlayerEnrichmentService
from .rankings import FantasyProsRankingRepository
from .schemas import (
    CreateRoomRequest,
    CreateRoomResponse,
    MakePickRequest,
    OverrideCpuPickRequest,
    PlayerQueryResponse,
    RecommendationResponse,
    ScoringPreset,
    SimulateResponse,
)

app = FastAPI(title="Fantasy Mock Draft API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


repo = FantasyProsRankingRepository(
    default_csv_path=Path(__file__).resolve().parents[2]
    / "reference"
    / "FantasyPros_2025_Master_Projections_With_ADP.csv"
)
drafts = DraftService()
enrichment = PlayerEnrichmentService()


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/rooms", response_model=CreateRoomResponse)
def create_room(payload: CreateRoomRequest) -> CreateRoomResponse:
    try:
        loaded = repo.load(
            scoring_preset=payload.league.scoring_preset,
            csv_path_override=payload.ranking_file_path,
        )
        room = drafts.create_room(request=payload, players=loaded.players)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return CreateRoomResponse(state=room.to_state(), available_players=len(room.available_keys))


@app.get("/api/v1/rooms/{room_id}")
def get_room(room_id: str):
    try:
        room = drafts.get(room_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return room.to_state()


@app.post("/api/v1/rooms/{room_id}/simulate-until-user", response_model=SimulateResponse)
def simulate_until_user(room_id: str) -> SimulateResponse:
    try:
        room = drafts.get(room_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    made = room.simulate_until_user_turn()
    return SimulateResponse(state=room.to_state(), cpu_picks_made=made)


@app.post("/api/v1/rooms/{room_id}/simulate-cpu-pick", response_model=SimulateResponse)
def simulate_cpu_pick(room_id: str) -> SimulateResponse:
    try:
        room = drafts.get(room_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    did_pick = room.simulate_single_cpu_pick()
    return SimulateResponse(state=room.to_state(), cpu_picks_made=1 if did_pick else 0)


@app.post("/api/v1/rooms/{room_id}/pick")
def make_user_pick(room_id: str, payload: MakePickRequest):
    try:
        room = drafts.get(room_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    try:
        if room.current_slot != room.user_slot:
            raise ValueError("It is not the user team's turn.")
        room.make_pick(slot=room.user_slot, player_key=payload.player_key, is_cpu=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return room.to_state()


@app.post("/api/v1/rooms/{room_id}/override-cpu-pick", response_model=SimulateResponse)
def override_cpu_pick(room_id: str, payload: OverrideCpuPickRequest) -> SimulateResponse:
    try:
        room = drafts.get(room_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    try:
        room.override_cpu_pick(pick_no=payload.pick_no, player_key=payload.player_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return SimulateResponse(state=room.to_state(), cpu_picks_made=0)


@app.post("/api/v1/rooms/{room_id}/simulate-to-end", response_model=SimulateResponse)
def simulate_to_end(room_id: str) -> SimulateResponse:
    try:
        room = drafts.get(room_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    made = room.simulate_to_end()
    return SimulateResponse(state=room.to_state(), cpu_picks_made=made)


@app.get("/api/v1/rooms/{room_id}/players", response_model=PlayerQueryResponse)
def list_players(
    room_id: str,
    search: str | None = None,
    position: str | None = None,
    top_n: int = Query(default=200, ge=1, le=500),
) -> PlayerQueryResponse:
    try:
        room = drafts.get(room_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    players = [room.player_pool[k] for k in room.available_keys]
    players.sort(key=lambda p: (p.adp, p.rank))
    if search:
        q = search.lower().strip()
        players = [p for p in players if q in p.player_name.lower()]
    if position:
        players = [p for p in players if p.position.upper() == position.upper()]
    players = players[:top_n]
    return PlayerQueryResponse(players=players, total=len(players))


@app.get("/api/v1/rooms/{room_id}/recommendations", response_model=RecommendationResponse)
def recommendations(
    room_id: str,
    top_n: int = Query(default=10, ge=1, le=30),
) -> RecommendationResponse:
    try:
        room = drafts.get(room_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    recs = room.recommendation_scores(slot=room.user_slot, top_n=top_n)
    return RecommendationResponse(room_id=room_id, pick_no=room.pick_no, recommendations=recs)


@app.get("/api/v1/rooms/{room_id}/players/{player_key}/card")
def player_card(
    room_id: str,
    player_key: str,
    season: int = Query(default=2025, ge=2010, le=2035),
    scoring_preset: ScoringPreset | None = Query(default=None),
):
    try:
        room = drafts.get(room_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    player = room.player_pool.get(player_key)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found in room pool.")
    resolved_scoring = scoring_preset or room.league.scoring_preset
    return enrichment.build_player_card(player=player, season=season, scoring_preset=resolved_scoring)

