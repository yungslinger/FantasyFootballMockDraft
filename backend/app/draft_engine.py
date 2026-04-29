from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .schemas import (
    CreateRoomRequest,
    DraftPick,
    LeagueConfig,
    PlayerPoolItem,
    RecommendationItem,
    RosterState,
    RoomState,
)


def snake_slot_for_pick(*, pick_no: int, teams: int) -> int:
    round_no = ((pick_no - 1) // teams) + 1
    in_round_idx = ((pick_no - 1) % teams) + 1
    if round_no % 2 == 1:
        return in_round_idx
    return teams - in_round_idx + 1


def round_for_pick(*, pick_no: int, teams: int) -> int:
    return ((pick_no - 1) // teams) + 1


def confidence_bucket(delta_adp: float) -> str:
    # delta_adp = pick_no - adp
    if delta_adp <= -18:
        return "reach"
    if delta_adp <= -8:
        return "slight_reach"
    if delta_adp < 10:
        return "adp_band"
    if delta_adp < 24:
        return "value"
    return "big_value"


@dataclass
class DraftRoom:
    room_id: str
    league: LeagueConfig
    user_slot: int
    rng: random.Random
    player_pool: dict[str, PlayerPoolItem]
    available_keys: set[str]
    picks: list[DraftPick] = field(default_factory=list)
    rosters: dict[int, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rosters:
            self._reset_state()

    def _empty_rosters(self) -> dict[int, dict[str, int]]:
        return {
            slot: {"QB": 0, "RB": 0, "WR": 0, "TE": 0, "K": 0, "DST": 0}
            for slot in range(1, self.league.teams + 1)
        }

    def _reset_state(self) -> None:
        self.picks = []
        self.rosters = self._empty_rosters()
        self.available_keys = set(self.player_pool.keys())

    @property
    def total_picks(self) -> int:
        return self.league.teams * self.league.rounds

    @property
    def pick_no(self) -> int:
        return len(self.picks) + 1

    @property
    def complete(self) -> bool:
        return len(self.picks) >= self.total_picks or len(self.available_keys) == 0

    @property
    def current_slot(self) -> int:
        if self.complete:
            return -1
        return snake_slot_for_pick(pick_no=self.pick_no, teams=self.league.teams)

    def roster_state(self) -> list[RosterState]:
        out: list[RosterState] = []
        for slot in range(1, self.league.teams + 1):
            counts = self.rosters.get(slot, {}).copy()
            out.append(
                RosterState(
                    team_slot=slot,
                    counts=counts,
                    total_players=int(sum(counts.values())),
                )
            )
        return out

    def to_state(self) -> RoomState:
        return RoomState(
            room_id=self.room_id,
            league=self.league,
            user_slot=self.user_slot,
            pick_no=self.pick_no,
            current_slot=self.current_slot,
            complete=self.complete,
            total_picks=self.total_picks,
            picks=self.picks,
            rosters=self.roster_state(),
        )

    def _max_for_position(self, position: str) -> int:
        starters = self.league.starters
        # ESPN-like lineup+bench caps. These are hard ceilings for team construction.
        if position == "QB":
            return min(4, max(2, starters.qb + starters.superflex + 3))
        if position == "RB":
            return min(8, max(4, starters.rb + starters.flex + starters.superflex + 5))
        if position == "WR":
            return min(8, max(4, starters.wr + starters.flex + starters.superflex + 5))
        if position == "TE":
            return min(3, max(2, starters.te + 2))
        if position == "K":
            return 1 if starters.k > 0 else 0
        if position == "DST":
            return 1 if starters.dst > 0 else 0
        return 2

    def _need_factor(self, *, slot: int, player: PlayerPoolItem) -> float:
        counts = self.rosters[slot]
        drafted = sum(counts.values())
        round_no = round_for_pick(pick_no=self.pick_no, teams=self.league.teams)
        pos = player.position
        if drafted >= self.league.rounds:
            return 0.0
        max_for_pos = self._max_for_position(pos)
        if counts.get(pos, 0) >= max_for_pos:
            return 0.0
        if pos in {"K", "DST"} and round_no < max(10, self.league.rounds - 4):
            return 0.05

        starters = self.league.starters
        need_targets = {
            "QB": starters.qb + starters.superflex,
            "RB": starters.rb + starters.flex,
            "WR": starters.wr + starters.flex,
            "TE": starters.te,
            "K": starters.k,
            "DST": starters.dst,
        }
        needed = max(0, need_targets.get(pos, 0) - counts.get(pos, 0))
        if needed > 0:
            return 1.45 + 0.2 * min(needed, 2)

        # After core starters, prioritize at least one QB/TE backup before late rounds.
        late_start_round = max(8, self.league.rounds - 6)
        if pos == "QB" and counts.get("QB", 0) < min(self._max_for_position("QB"), starters.qb + starters.superflex + 1):
            if round_no >= late_start_round:
                return 1.55
        if pos == "TE" and counts.get("TE", 0) < min(self._max_for_position("TE"), starters.te + 1):
            if round_no >= late_start_round:
                return 1.45

        # Prefer balancing RB/WR depth over overloading QB/TE early.
        if pos in {"RB", "WR"}:
            return 1.05
        if pos in {"QB", "TE"}:
            return 0.85
        return 0.75

    def _scoring_strictness_multiplier(self) -> float:
        # PPR leagues are typically tighter at the very top; standard is slightly looser.
        preset = self.league.scoring_preset
        if preset == "ppr":
            return 0.85
        if preset == "half_ppr":
            return 0.92
        return 1.0

    def _adp_factor(self, player: PlayerPoolItem) -> float:
        # pick_minus_adp > 0 => value available later than expected
        # pick_minus_adp < 0 => reach (player being taken early)
        pick_minus_adp = float(self.pick_no) - player.adp
        round_no = round_for_pick(pick_no=self.pick_no, teams=self.league.teams)
        abs_delta = abs(pick_minus_adp)
        base = math.exp(-abs_delta / 16.0)

        # Strong anti-reach pressure, especially in early rounds.
        if pick_minus_adp <= -20:
            base *= 0.02 if round_no <= 3 else 0.06
        elif pick_minus_adp <= -10:
            base *= 0.12 if round_no <= 3 else 0.30
        elif pick_minus_adp <= -5:
            base *= 0.50
        # Moderate reward for value falls.
        elif pick_minus_adp >= 30:
            base *= 1.85
        elif pick_minus_adp >= 20:
            base *= 1.55
        elif pick_minus_adp >= 10:
            base *= 1.30
        # Elite ADP safeguard: avoid unrealistic drops for top tiers.
        if player.adp <= 8 and pick_minus_adp >= 6:
            base *= 5.5
        elif player.adp <= 16 and pick_minus_adp >= 9:
            base *= 3.8
        elif player.adp <= 24 and pick_minus_adp >= 12:
            base *= 2.9
        elif player.adp <= 36 and pick_minus_adp >= 15:
            base *= 2.0
        elif player.adp <= 60 and pick_minus_adp >= 20:
            base *= 1.5
        return max(0.005, base)

    def _round_adp_window(self) -> float:
        r = round_for_pick(pick_no=self.pick_no, teams=self.league.teams)
        strict = self._scoring_strictness_multiplier()
        if r == 1:
            return 3.0 * strict
        if r == 2:
            return 5.5 * strict
        if r == 3:
            return 8.0 * strict
        if r <= 6:
            return 12.5 * strict
        if r <= 10:
            return 18.0 * strict
        return 25.0 * strict

    def _max_rank_for_pick(self) -> int:
        # Guard against extreme outlier selections in earlier phases.
        p = self.pick_no
        t = self.league.teams
        if p <= t * 2:
            return 60
        if p <= t * 4:
            return 120
        if p <= t * 6:
            return 170
        if p <= t * 8:
            return 220
        if p <= t * 10:
            return 275
        return 999

    def _early_pick_max_adp(self) -> float | None:
        # Very strict top-of-draft realism; gradually loosens through round 1.
        r = round_for_pick(pick_no=self.pick_no, teams=self.league.teams)
        if r > 1:
            return None
        p = self.pick_no
        slack = 0.0
        if self.league.scoring_preset == "standard":
            slack = 0.4
        elif self.league.scoring_preset == "half_ppr":
            slack = 0.2
        if p <= 3:
            return p + 0.45 + slack
        if p <= 5:
            return p + 0.9 + slack
        if p <= 8:
            return p + 1.5 + slack
        if p <= 12:
            return p + 2.6 + slack
        return None

    def _same_position_bye_overlap_penalty(self, *, slot: int, player: PlayerPoolItem) -> float:
        # Soft bye-overlap proxy: avoid same-team backups at same position.
        # (Exact bye-week data may be unavailable in source rankings.)
        if player.position not in {"QB", "TE"}:
            return 1.0
        existing = [
            p for p in self.picks if p.team_slot == slot and p.position == player.position
        ]
        if not existing:
            return 1.0
        if any(p.team == player.team for p in existing):
            return 0.45
        return 1.0

    def recommendation_scores(self, *, slot: int, top_n: int = 12) -> list[RecommendationItem]:
        candidates = [self.player_pool[k] for k in self.available_keys]
        scored: list[tuple[PlayerPoolItem, float, str]] = []
        rank_floor = self._max_rank_for_pick()
        for p in candidates:
            if p.rank > rank_floor and p.position not in {"K", "DST"}:
                continue
            need = self._need_factor(slot=slot, player=p)
            if need <= 0:
                continue
            adp = self._adp_factor(p)
            bye_penalty = self._same_position_bye_overlap_penalty(slot=slot, player=p)
            score = need * adp * bye_penalty
            rationale = f"need={need:.2f}, adp_factor={adp:.2f}, bye_penalty={bye_penalty:.2f}, adp={p.adp:.1f}"
            scored.append((p, score, rationale))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            RecommendationItem(player=item[0], score=float(item[1]), rationale=item[2])
            for item in scored[:top_n]
        ]

    def _cpu_select_player_key(self, *, slot: int) -> str:
        recommendations = self.recommendation_scores(slot=slot, top_n=24)
        if not recommendations:
            return sorted(self.available_keys)[0]

        # Moderate realism: keep early picks near ADP while preserving variance.
        max_reach = self._round_adp_window()
        bounded = [
            rec
            for rec in recommendations
            if (rec.player.adp - float(self.pick_no)) <= max_reach
        ]
        pool = bounded if bounded else recommendations[:8]
        max_adp = self._early_pick_max_adp()
        if max_adp is not None:
            early_pool = [rec for rec in pool if rec.player.adp <= max_adp]
            if early_pool:
                pool = early_pool
        # If elite players are materially past ADP, force them into the active pool.
        overdue_elites = [
            rec
            for rec in recommendations
            if (rec.player.adp <= 12 and (float(self.pick_no) - rec.player.adp) >= 8)
            or (rec.player.adp <= 24 and (float(self.pick_no) - rec.player.adp) >= 12)
            or (rec.player.adp <= 36 and (float(self.pick_no) - rec.player.adp) >= 15)
            or (rec.player.adp <= 60 and (float(self.pick_no) - rec.player.adp) >= 20)
        ]
        if overdue_elites:
            elite_keys = {r.player.player_key for r in overdue_elites}
            for rec in recommendations:
                if rec.player.player_key in elite_keys and all(p.player.player_key != rec.player.player_key for p in pool):
                    pool.append(rec)

        # Gumbel-style noisy utility to keep drafts non-deterministic but logical.
        best_key = pool[0].player.player_key
        best_u = -1e9
        for rec in pool:
            noise = self.rng.gammavariate(2.0, 0.15) - 0.25
            utility = math.log(max(rec.score, 1e-6)) + noise
            if utility > best_u:
                best_u = utility
                best_key = rec.player.player_key
        return best_key

    def make_pick(self, *, slot: int, player_key: str, is_cpu: bool) -> DraftPick:
        if self.complete:
            raise ValueError("Draft is complete.")
        if slot != self.current_slot:
            raise ValueError(f"It is team_slot={self.current_slot}'s turn, not team_slot={slot}.")
        if player_key not in self.available_keys:
            raise ValueError("Player is already drafted or unavailable.")

        p = self.player_pool[player_key]
        self.available_keys.remove(player_key)
        self.rosters[slot][p.position] = self.rosters[slot].get(p.position, 0) + 1

        delta_adp = float(self.pick_no) - p.adp
        pick = DraftPick(
            pick_no=self.pick_no,
            round_no=round_for_pick(pick_no=self.pick_no, teams=self.league.teams),
            team_slot=slot,
            player_key=p.player_key,
            player_name=p.player_name,
            position=p.position,
            team=p.team,
            bye_week=p.bye_week,
            is_cpu=is_cpu,
            confidence_bucket=confidence_bucket(delta_adp),
            drafted_at=datetime.now(tz=timezone.utc),
        )
        self.picks.append(pick)
        return pick

    def simulate_until_user_turn(self) -> int:
        cpu_picks = 0
        while (not self.complete) and self.current_slot != self.user_slot:
            slot = self.current_slot
            chosen = self._cpu_select_player_key(slot=slot)
            self.make_pick(slot=slot, player_key=chosen, is_cpu=True)
            cpu_picks += 1
        return cpu_picks

    def simulate_single_cpu_pick(self) -> bool:
        """
        Execute exactly one CPU pick if it's a CPU turn.
        Returns True when a CPU pick was made, else False.
        """
        if self.complete:
            return False
        slot = self.current_slot
        if slot == self.user_slot:
            return False
        chosen = self._cpu_select_player_key(slot=slot)
        self.make_pick(slot=slot, player_key=chosen, is_cpu=True)
        return True

    def simulate_to_end(self) -> int:
        cpu_picks = 0
        while not self.complete:
            slot = self.current_slot
            if slot == self.user_slot:
                recs = self.recommendation_scores(slot=slot, top_n=1)
                chosen = recs[0].player.player_key if recs else sorted(self.available_keys)[0]
                self.make_pick(slot=slot, player_key=chosen, is_cpu=False)
            else:
                chosen = self._cpu_select_player_key(slot=slot)
                self.make_pick(slot=slot, player_key=chosen, is_cpu=True)
                cpu_picks += 1
        return cpu_picks

    def override_cpu_pick(self, *, pick_no: int, player_key: str) -> None:
        if pick_no < 1 or pick_no > len(self.picks):
            raise ValueError("pick_no must reference an existing drafted pick.")
        if player_key not in self.player_pool:
            raise ValueError("Selected override player does not exist in the room player pool.")

        original_picks = list(self.picks)
        target = original_picks[pick_no - 1]

        prefix = original_picks[: pick_no - 1]
        prefix_keys = {p.player_key for p in prefix}
        if player_key in prefix_keys:
            raise ValueError("Selected override player was already drafted before this pick.")

        self._reset_state()
        for p in prefix:
            self.make_pick(slot=p.team_slot, player_key=p.player_key, is_cpu=p.is_cpu)
        self.make_pick(slot=target.team_slot, player_key=player_key, is_cpu=True)


class DraftService:
    def __init__(self) -> None:
        self.rooms: dict[str, DraftRoom] = {}

    def create_room(self, *, request: CreateRoomRequest, players: list[PlayerPoolItem]) -> DraftRoom:
        if request.user_slot > request.league.teams:
            raise ValueError("user_slot cannot exceed number of teams.")
        room = DraftRoom(
            room_id=str(uuid.uuid4()),
            league=request.league,
            user_slot=request.user_slot,
            rng=random.Random(request.seed if request.seed is not None else random.randrange(1_000_000_000)),
            player_pool={p.player_key: p for p in players},
            available_keys={p.player_key for p in players},
        )
        self.rooms[room.room_id] = room
        return room

    def get(self, room_id: str) -> DraftRoom:
        room = self.rooms.get(room_id)
        if room is None:
            raise KeyError(f"Unknown room_id: {room_id}")
        return room

