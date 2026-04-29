"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Player = {
  player_key: string;
  player_name: string;
  position: string;
  team: string;
  bye_week?: number | null;
  adp: number;
  rank: number;
  fpts?: number | null;
  status_tag?: string | null;
  injury_note?: string | null;
};

type Pick = {
  pick_no: number;
  round_no: number;
  team_slot: number;
  player_key: string;
  player_name: string;
  position: string;
  team: string;
  bye_week?: number | null;
  is_cpu: boolean;
  confidence_bucket: string;
};

type Roster = {
  team_slot: number;
  counts: Record<string, number>;
  total_players: number;
};

type RoomState = {
  room_id: string;
  user_slot: number;
  pick_no: number;
  current_slot: number;
  complete: boolean;
  total_picks: number;
  picks: Pick[];
  rosters: Roster[];
  league: {
    teams: number;
    rounds: number | null;
    bench: number;
    ai_think_seconds: number;
    scoring_preset: "standard" | "half_ppr" | "ppr";
    starters: { qb: number; rb: number; wr: number; te: number; flex: number; superflex: number; k: number; dst: number };
  };
};

type Recommendation = { player: Player; score: number; rationale: string };

type ScoringPreset = "standard" | "half_ppr" | "ppr";

type GameLogEntry = {
  week: number;
  opponent?: string | null;
  fantasy_points?: number | null;
  passing_completions?: number | null;
  passing_attempts?: number | null;
  passing_yards?: number | null;
  passing_tds?: number | null;
  interceptions?: number | null;
  rushing_attempts?: number | null;
  rushing_yards?: number | null;
  rushing_tds?: number | null;
  receptions?: number | null;
  targets?: number | null;
  receiving_yards?: number | null;
  receiving_tds?: number | null;
  misc_tds?: number | null;
  field_goals_made?: number | null;
  field_goals_attempted?: number | null;
  extra_points_made?: number | null;
  sacks?: number | null;
  fumble_recoveries?: number | null;
  defensive_interceptions?: number | null;
  defensive_tds?: number | null;
  safeties?: number | null;
  points_allowed?: number | null;
};

type PlayerCard = {
  player_key: string;
  player_name: string;
  position: string;
  team: string;
  headshot_url?: string | null;
  season: number;
  scoring_preset: ScoringPreset;
  status_tag?: string | null;
  injury_note?: string | null;
  adp?: number | null;
  fpts?: number | null;
  game_log: GameLogEntry[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function formatPickLabel(pickNo: number, teams: number): string {
  const roundNo = Math.floor((pickNo - 1) / teams) + 1;
  const pickInRound = ((pickNo - 1) % teams) + 1;
  return `${roundNo}.${String(pickInRound).padStart(2, "0")}`;
}

function splitDisplayName(name: string): { first: string; last: string } {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return { first: name, last: "" };
  return { first: parts[0], last: parts.slice(1).join(" ") };
}

function positionClass(position: string): string {
  const p = position.toUpperCase();
  if (p === "QB") return "pos-qb";
  if (p === "RB") return "pos-rb";
  if (p === "WR") return "pos-wr";
  if (p === "TE") return "pos-te";
  if (p === "K") return "pos-k";
  if (p === "DST") return "pos-dst";
  return "";
}

const NFL_TEAM_NAMES: Record<string, string> = {
  ARI: "Arizona Cardinals",
  ATL: "Atlanta Falcons",
  BAL: "Baltimore Ravens",
  BUF: "Buffalo Bills",
  CAR: "Carolina Panthers",
  CHI: "Chicago Bears",
  CIN: "Cincinnati Bengals",
  CLE: "Cleveland Browns",
  DAL: "Dallas Cowboys",
  DEN: "Denver Broncos",
  DET: "Detroit Lions",
  GB: "Green Bay Packers",
  HOU: "Houston Texans",
  IND: "Indianapolis Colts",
  JAX: "Jacksonville Jaguars",
  KC: "Kansas City Chiefs",
  LV: "Las Vegas Raiders",
  LAC: "Los Angeles Chargers",
  LAR: "Los Angeles Rams",
  MIA: "Miami Dolphins",
  MIN: "Minnesota Vikings",
  NE: "New England Patriots",
  NO: "New Orleans Saints",
  NYG: "New York Giants",
  NYJ: "New York Jets",
  PHI: "Philadelphia Eagles",
  PIT: "Pittsburgh Steelers",
  SEA: "Seattle Seahawks",
  SF: "San Francisco 49ers",
  TB: "Tampa Bay Buccaneers",
  TEN: "Tennessee Titans",
  WAS: "Washington Commanders"
};

function teamDisplayName(team: string): string {
  const key = (team ?? "").toUpperCase().trim();
  return NFL_TEAM_NAMES[key] ?? team;
}

function formatMetric(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return digits > 0 ? value.toFixed(digits) : value.toFixed(0);
}

function safeAverage(numerator: number | null | undefined, denominator: number | null | undefined): number | null {
  if (numerator === null || numerator === undefined || denominator === null || denominator === undefined || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

type CardColumn = {
  key: string;
  label: string;
  render: (row: GameLogEntry) => string;
};

function sumStat(rows: GameLogEntry[], key: keyof GameLogEntry): number {
  let total = 0;
  for (const r of rows) {
    const v = r[key];
    if (typeof v === "number" && !Number.isNaN(v)) total += v;
  }
  return total;
}

function totalsRowForPosition(position: string, rows: GameLogEntry[]): GameLogEntry {
  const pos = position.toUpperCase();
  const base: GameLogEntry = { week: 0, opponent: "TOTAL" };

  if (pos === "QB") {
    return {
      ...base,
      passing_completions: sumStat(rows, "passing_completions"),
      passing_attempts: sumStat(rows, "passing_attempts"),
      passing_yards: sumStat(rows, "passing_yards"),
      passing_tds: sumStat(rows, "passing_tds"),
      interceptions: sumStat(rows, "interceptions"),
      rushing_attempts: sumStat(rows, "rushing_attempts"),
      rushing_yards: sumStat(rows, "rushing_yards"),
      rushing_tds: sumStat(rows, "rushing_tds"),
      fantasy_points: sumStat(rows, "fantasy_points")
    };
  }

  if (pos === "RB") {
    return {
      ...base,
      rushing_attempts: sumStat(rows, "rushing_attempts"),
      rushing_yards: sumStat(rows, "rushing_yards"),
      rushing_tds: sumStat(rows, "rushing_tds"),
      receptions: sumStat(rows, "receptions"),
      receiving_yards: sumStat(rows, "receiving_yards"),
      receiving_tds: sumStat(rows, "receiving_tds"),
      misc_tds: sumStat(rows, "misc_tds"),
      fantasy_points: sumStat(rows, "fantasy_points")
    };
  }

  if (pos === "WR" || pos === "TE") {
    return {
      ...base,
      receptions: sumStat(rows, "receptions"),
      receiving_yards: sumStat(rows, "receiving_yards"),
      receiving_tds: sumStat(rows, "receiving_tds"),
      rushing_attempts: sumStat(rows, "rushing_attempts"),
      rushing_yards: sumStat(rows, "rushing_yards"),
      rushing_tds: sumStat(rows, "rushing_tds"),
      misc_tds: sumStat(rows, "misc_tds"),
      fantasy_points: sumStat(rows, "fantasy_points")
    };
  }

  if (pos === "K") {
    return {
      ...base,
      field_goals_made: sumStat(rows, "field_goals_made"),
      field_goals_attempted: sumStat(rows, "field_goals_attempted"),
      extra_points_made: sumStat(rows, "extra_points_made"),
      fantasy_points: sumStat(rows, "fantasy_points")
    };
  }

  if (pos === "DST") {
    return {
      ...base,
      sacks: sumStat(rows, "sacks"),
      defensive_interceptions: sumStat(rows, "defensive_interceptions"),
      fumble_recoveries: sumStat(rows, "fumble_recoveries"),
      defensive_tds: sumStat(rows, "defensive_tds"),
      safeties: sumStat(rows, "safeties"),
      points_allowed: sumStat(rows, "points_allowed"),
      fantasy_points: sumStat(rows, "fantasy_points")
    };
  }

  return { ...base, fantasy_points: sumStat(rows, "fantasy_points") };
}

function cardColumnsForPosition(position: string): CardColumn[] {
  const pos = position.toUpperCase();
  if (pos === "QB") {
    return [
      { key: "cmp_att", label: "CMP/ATT", render: (g) => `${formatMetric(g.passing_completions)}/${formatMetric(g.passing_attempts)}` },
      { key: "pass_yds", label: "PASS YDS", render: (g) => formatMetric(g.passing_yards) },
      { key: "pass_td", label: "PASS TD", render: (g) => formatMetric(g.passing_tds) },
      { key: "int", label: "INT", render: (g) => formatMetric(g.interceptions) },
      { key: "rush_car", label: "RUSH CAR", render: (g) => formatMetric(g.rushing_attempts) },
      { key: "rush_yds", label: "RUSH YDS", render: (g) => formatMetric(g.rushing_yards) },
      { key: "rush_td", label: "RUSH TD", render: (g) => formatMetric(g.rushing_tds) },
      { key: "fpts", label: "FPTS", render: (g) => formatMetric(g.fantasy_points, 1) }
    ];
  }
  if (pos === "RB") {
    return [
      { key: "car", label: "CAR", render: (g) => formatMetric(g.rushing_attempts) },
      { key: "rush_yds", label: "YDS", render: (g) => formatMetric(g.rushing_yards) },
      { key: "rush_avg", label: "AVG", render: (g) => formatMetric(safeAverage(g.rushing_yards, g.rushing_attempts), 1) },
      { key: "rush_td", label: "TD", render: (g) => formatMetric(g.rushing_tds) },
      { key: "rec", label: "REC", render: (g) => formatMetric(g.receptions) },
      { key: "rec_yds", label: "REC YDS", render: (g) => formatMetric(g.receiving_yards) },
      { key: "rec_td", label: "REC TD", render: (g) => formatMetric(g.receiving_tds) },
      { key: "misc_td", label: "MISC TD", render: (g) => formatMetric(g.misc_tds) },
      { key: "fpts", label: "FPTS", render: (g) => formatMetric(g.fantasy_points, 1) }
    ];
  }
  if (pos === "WR" || pos === "TE") {
    return [
      { key: "rec", label: "REC", render: (g) => formatMetric(g.receptions) },
      { key: "rec_yds", label: "YDS", render: (g) => formatMetric(g.receiving_yards) },
      { key: "rec_avg", label: "AVG", render: (g) => formatMetric(safeAverage(g.receiving_yards, g.receptions), 1) },
      { key: "rec_td", label: "TD", render: (g) => formatMetric(g.receiving_tds) },
      { key: "car", label: "CAR", render: (g) => formatMetric(g.rushing_attempts) },
      { key: "rush_yds", label: "RUSH YDS", render: (g) => formatMetric(g.rushing_yards) },
      { key: "rush_td", label: "RUSH TD", render: (g) => formatMetric(g.rushing_tds) },
      { key: "misc_td", label: "MISC TD", render: (g) => formatMetric(g.misc_tds) },
      { key: "fpts", label: "FPTS", render: (g) => formatMetric(g.fantasy_points, 1) }
    ];
  }
  if (pos === "K") {
    return [
      { key: "fg", label: "FG", render: (g) => formatMetric(g.field_goals_made) },
      { key: "fga", label: "FGA", render: (g) => formatMetric(g.field_goals_attempted) },
      { key: "xpt", label: "XPT", render: (g) => formatMetric(g.extra_points_made) },
      { key: "fpts", label: "FPTS", render: (g) => formatMetric(g.fantasy_points, 1) }
    ];
  }
  if (pos === "DST") {
    return [
      { key: "sack", label: "SACK", render: (g) => formatMetric(g.sacks) },
      { key: "int", label: "INT", render: (g) => formatMetric(g.defensive_interceptions) },
      { key: "fr", label: "FR", render: (g) => formatMetric(g.fumble_recoveries) },
      { key: "td", label: "TD", render: (g) => formatMetric(g.defensive_tds) },
      { key: "saf", label: "SAF", render: (g) => formatMetric(g.safeties) },
      { key: "pa", label: "PA", render: (g) => formatMetric(g.points_allowed) },
      { key: "fpts", label: "FPTS", render: (g) => formatMetric(g.fantasy_points, 1) }
    ];
  }
  return [{ key: "fpts", label: "FPTS", render: (g) => formatMetric(g.fantasy_points, 1) }];
}

async function jget<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

async function jpost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Request failed (${res.status}): ${text}`);
  }
  return (await res.json()) as T;
}

export default function Page() {
  const [teamsInput, setTeamsInput] = useState("10");
  const [userSlotInput, setUserSlotInput] = useState("1");
  const [clockInput, setClockInput] = useState("60");
  const [aiThinkInput, setAiThinkInput] = useState("0.5");
  const [benchInput, setBenchInput] = useState("7");
  const [startersInput, setStartersInput] = useState({
    qb: "1",
    rb: "2",
    wr: "2",
    te: "1",
    flex: "1",
    superflex: "0",
    k: "1",
    dst: "1"
  });
  const [scoringPreset, setScoringPreset] = useState("ppr");
  const [pickClockSec, setPickClockSec] = useState(60);
  const [aiThinkSeconds, setAiThinkSeconds] = useState(0);
  const [timeRemaining, setTimeRemaining] = useState(60);
  const [timerPaused, setTimerPaused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isAutoFinishing, setIsAutoFinishing] = useState(false);
  const [room, setRoom] = useState<RoomState | null>(null);
  const [players, setPlayers] = useState<Player[]>([]);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [query, setQuery] = useState("");
  const [positionFilter, setPositionFilter] = useState("ALL");
  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);
  const [selectedCard, setSelectedCard] = useState<PlayerCard | null>(null);
  const [cardSeason, setCardSeason] = useState<2024 | 2025>(2025);
  const [overrideTargetPick, setOverrideTargetPick] = useState<Pick | null>(null);
  const [overridePool, setOverridePool] = useState<Player[]>([]);
  const [overrideChoiceKey, setOverrideChoiceKey] = useState("");
  const [error, setError] = useState("");
  const [isCpuThinking, setIsCpuThinking] = useState(false);
  const [selectedTeamSlot, setSelectedTeamSlot] = useState(0);
  const cpuLoopingRef = useRef(false);
  const autoPickRef = useRef(false);
  const turnDeadlineRef = useRef<number | null>(null);
  const timerPausedAtRef = useRef<number | null>(null);
  const queryRef = useRef(query);
  const positionFilterRef = useRef(positionFilter);

  const selectedTeamPicks = useMemo(() => {
    if (!room) return [];
    const slot = selectedTeamSlot > 0 ? selectedTeamSlot : room.user_slot;
    return room.picks.filter((p) => p.team_slot === slot).sort((a, b) => a.pick_no - b.pick_no);
  }, [room, selectedTeamSlot]);

  const selectedRoster = useMemo(() => {
    if (!room) return null;
    const slot = selectedTeamSlot > 0 ? selectedTeamSlot : room.user_slot;
    return room.rosters.find((r) => r.team_slot === slot) ?? null;
  }, [room, selectedTeamSlot]);

  const selectedTeamName = useMemo(() => {
    if (!room) return "";
    const slot = selectedTeamSlot > 0 ? selectedTeamSlot : room.user_slot;
    return slot === room.user_slot ? `Team ${slot} (You)` : `Team ${slot}`;
  }, [room, selectedTeamSlot]);

  const isResultsMode = !!room?.complete;

  const timerUrgency = useMemo(() => {
    if (!room || room.complete || room.current_slot !== room.user_slot) return "normal";
    if (timeRemaining <= 10) return "critical";
    if (timeRemaining <= 20) return "warning";
    return "normal";
  }, [room, timeRemaining]);

  const derivedRoundsPreview = useMemo(() => {
    const toInt = (v: string) => (v.trim() === "" ? 0 : Number(v));
    const total =
      toInt(startersInput.qb) +
      toInt(startersInput.rb) +
      toInt(startersInput.wr) +
      toInt(startersInput.te) +
      toInt(startersInput.flex) +
      toInt(startersInput.superflex) +
      toInt(startersInput.k) +
      toInt(startersInput.dst) +
      toInt(benchInput);
    return Math.max(8, Math.min(30, total || 0));
  }, [startersInput, benchInput]);

  const totalRounds = room?.league.rounds ?? derivedRoundsPreview;

  const eligiblePositions = useMemo(() => {
    if (!room) return new Set(["QB", "RB", "WR", "TE", "K", "DST"]);
    const s = room.league.starters;
    const out = new Set<string>();
    if (s.qb > 0 || s.superflex > 0) out.add("QB");
    if (s.rb > 0 || s.flex > 0 || s.superflex > 0) out.add("RB");
    if (s.wr > 0 || s.flex > 0 || s.superflex > 0) out.add("WR");
    if (s.te > 0 || s.flex > 0 || s.superflex > 0) out.add("TE");
    if (s.k > 0) out.add("K");
    if (s.dst > 0) out.add("DST");
    return out;
  }, [room]);

  const visiblePlayers = useMemo(
    () => players.filter((p) => eligiblePositions.has(p.position)),
    [players, eligiblePositions]
  );

  const visibleRecs = useMemo(
    () => recs.filter((r) => eligiblePositions.has(r.player.position)),
    [recs, eligiblePositions]
  );

  const lineupView = useMemo(() => {
    if (!room) {
      return { starters: [] as Array<{ slot: string; player: Pick | null }>, bench: [] as Pick[] };
    }
    const s = room.league.starters;
    const startersTemplate: Array<{ slot: string; accepts: Array<Pick["position"]> }> = [];
    for (let i = 1; i <= s.qb; i++) startersTemplate.push({ slot: s.qb === 1 ? "QB" : `QB${i}`, accepts: ["QB"] });
    for (let i = 1; i <= s.rb; i++) startersTemplate.push({ slot: s.rb === 1 ? "RB" : `RB${i}`, accepts: ["RB"] });
    for (let i = 1; i <= s.wr; i++) startersTemplate.push({ slot: s.wr === 1 ? "WR" : `WR${i}`, accepts: ["WR"] });
    for (let i = 1; i <= s.te; i++) startersTemplate.push({ slot: s.te === 1 ? "TE" : `TE${i}`, accepts: ["TE"] });
    for (let i = 1; i <= s.flex; i++) startersTemplate.push({ slot: s.flex === 1 ? "FLEX" : `FLEX${i}`, accepts: ["RB", "WR", "TE"] });
    for (let i = 1; i <= s.superflex; i++) startersTemplate.push({ slot: s.superflex === 1 ? "S-FLEX" : `S-FLEX${i}`, accepts: ["QB", "RB", "WR", "TE"] });
    for (let i = 1; i <= s.k; i++) startersTemplate.push({ slot: s.k === 1 ? "K" : `K${i}`, accepts: ["K"] });
    for (let i = 1; i <= s.dst; i++) startersTemplate.push({ slot: s.dst === 1 ? "DST" : `DST${i}`, accepts: ["DST"] });

    const filled: Array<{ slot: string; player: Pick | null; accepts: Array<Pick["position"]> }> = startersTemplate.map((x) => ({
      ...x,
      player: null
    }));
    const bench: Pick[] = [];
    for (const pick of selectedTeamPicks) {
      const idx = filled.findIndex((f) => f.player === null && f.accepts.includes(pick.position));
      if (idx >= 0) {
        filled[idx].player = pick;
      } else {
        bench.push(pick);
      }
    }
    return {
      starters: filled.map((f) => ({ slot: f.slot, player: f.player })),
      bench
    };
  }, [room, selectedTeamPicks]);

  const rosterLimits = useMemo(() => {
    if (!room || !selectedRoster) return [];
    const s = room.league.starters;
    const capQB = Math.min(4, Math.max(2, s.qb + s.superflex + 3));
    const capRB = Math.min(8, Math.max(4, s.rb + s.flex + s.superflex + 5));
    const capWR = Math.min(8, Math.max(4, s.wr + s.flex + s.superflex + 5));
    const capTE = Math.min(3, Math.max(2, s.te + 2));
    const capK = s.k > 0 ? 1 : 0;
    const capDST = s.dst > 0 ? 1 : 0;
    const limits = [
      { key: "QB", cur: selectedRoster.counts.QB ?? 0, limit: capQB },
      { key: "RB", cur: selectedRoster.counts.RB ?? 0, limit: capRB },
      { key: "WR", cur: selectedRoster.counts.WR ?? 0, limit: capWR },
      { key: "TE", cur: selectedRoster.counts.TE ?? 0, limit: capTE },
      { key: "K", cur: selectedRoster.counts.K ?? 0, limit: capK },
      { key: "DST", cur: selectedRoster.counts.DST ?? 0, limit: capDST }
    ];
    const startersTarget = s.qb + s.rb + s.wr + s.te + s.flex + s.superflex + s.k + s.dst;
    const benchCurrent = Math.max(0, selectedRoster.total_players - startersTarget);
    limits.push({ key: "BN", cur: benchCurrent, limit: room.league.bench });
    limits.push({ key: "Total", cur: selectedRoster.total_players, limit: totalRounds });
    return limits;
  }, [room, selectedRoster, totalRounds]);

  async function refreshRoomViews(nextRoom: RoomState, opts?: { search?: string; position?: string }) {
    const effectiveSearch = opts?.search ?? queryRef.current;
    const effectivePosition = opts?.position ?? positionFilterRef.current;
    const [playerRes, recRes] = await Promise.all([
      jget<{ players: Player[] }>(
        `${API_BASE}/api/v1/rooms/${nextRoom.room_id}/players?top_n=300&search=${encodeURIComponent(effectiveSearch)}&position=${
          effectivePosition === "ALL" ? "" : encodeURIComponent(effectivePosition)
        }`
      ),
      jget<{ recommendations: Recommendation[] }>(
        `${API_BASE}/api/v1/rooms/${nextRoom.room_id}/recommendations?top_n=12`
      )
    ]);
    setPlayers(playerRes.players);
    setRecs(recRes.recommendations);
  }

  function parsePositiveInt(value: string, options: { label: string; min: number; max: number }): number {
    const { label, min, max } = options;
    if (value.trim() === "") {
      throw new Error(`${label} is required.`);
    }
    if (!/^\d+$/.test(value.trim())) {
      throw new Error(`${label} must be a whole number.`);
    }
    const parsed = Number(value);
    if (parsed < min || parsed > max) {
      throw new Error(`${label} must be between ${min} and ${max}.`);
    }
    return parsed;
  }

  function parseNonNegativeInt(value: string, options: { label: string; min: number; max: number }): number {
    const { label, min, max } = options;
    if (value.trim() === "") {
      throw new Error(`${label} is required.`);
    }
    if (!/^\d+$/.test(value.trim())) {
      throw new Error(`${label} must be a whole number.`);
    }
    const parsed = Number(value);
    if (parsed < min || parsed > max) {
      throw new Error(`${label} must be between ${min} and ${max}.`);
    }
    return parsed;
  }

  function parseBoundedDecimal(value: string, options: { label: string; min: number; max: number }): number {
    const { label, min, max } = options;
    if (value.trim() === "") {
      throw new Error(`${label} is required.`);
    }
    if (!/^\d+(\.\d+)?$/.test(value.trim())) {
      throw new Error(`${label} must be a number.`);
    }
    const parsed = Number(value);
    if (Number.isNaN(parsed) || parsed < min || parsed > max) {
      throw new Error(`${label} must be between ${min} and ${max}.`);
    }
    return parsed;
  }

  async function runCpuPacing(roomId: string) {
    if (cpuLoopingRef.current) return;
    cpuLoopingRef.current = true;
    setIsCpuThinking(true);
    try {
      while (cpuLoopingRef.current) {
        const current = await jget<RoomState>(`${API_BASE}/api/v1/rooms/${roomId}`);
        if (!cpuLoopingRef.current) break;
        if (current.complete || current.current_slot === current.user_slot) {
          setRoom(current);
          await refreshRoomViews(current);
          break;
        }
        const effectiveThink = current.league.ai_think_seconds ?? aiThinkSeconds;
        const delayMs =
          effectiveThink <= 0
            ? 0
            : Math.round(effectiveThink * 1000) +
              randomInt(
                -Math.min(300, Math.round(effectiveThink * 100)),
                Math.min(300, Math.round(effectiveThink * 100))
              );
        if (delayMs > 0) {
          await sleep(delayMs);
        }
        const step = await jpost<{ state: RoomState; cpu_picks_made: number }>(
          `${API_BASE}/api/v1/rooms/${roomId}/simulate-cpu-pick`,
          {}
        );
        if (!cpuLoopingRef.current) break;
        setRoom(step.state);
        await refreshRoomViews(step.state);
        if (step.cpu_picks_made === 0) {
          break;
        }
      }
    } finally {
      setIsCpuThinking(false);
      cpuLoopingRef.current = false;
    }
  }

  async function createRoom() {
    setLoading(true);
    setError("");
    try {
      const teams = parsePositiveInt(teamsInput, { label: "Teams", min: 4, max: 16 });
      const userSlot = parsePositiveInt(userSlotInput, { label: "Draft Position", min: 1, max: teams });
      const clock = parseNonNegativeInt(clockInput, { label: "Clock (seconds)", min: 0, max: 120 });
      const aiThink = parseBoundedDecimal(aiThinkInput, { label: "AI think (seconds)", min: 0, max: 5 });
      const bench = parseNonNegativeInt(benchInput, { label: "Bench", min: 0, max: 20 });
      const starters = {
        qb: parseNonNegativeInt(startersInput.qb, { label: "QB starters", min: 0, max: 3 }),
        rb: parseNonNegativeInt(startersInput.rb, { label: "RB starters", min: 0, max: 5 }),
        wr: parseNonNegativeInt(startersInput.wr, { label: "WR starters", min: 0, max: 5 }),
        te: parseNonNegativeInt(startersInput.te, { label: "TE starters", min: 0, max: 3 }),
        flex: parseNonNegativeInt(startersInput.flex, { label: "FLEX starters", min: 0, max: 4 }),
        superflex: parseNonNegativeInt(startersInput.superflex, { label: "Superflex starters", min: 0, max: 2 }),
        k: parseNonNegativeInt(startersInput.k, { label: "K starters", min: 0, max: 2 }),
        dst: parseNonNegativeInt(startersInput.dst, { label: "DST starters", min: 0, max: 2 })
      };
      setPickClockSec(clock);
      setAiThinkSeconds(aiThink);
      setIsAutoFinishing(false);
      setTimeRemaining(clock);
      turnDeadlineRef.current = null;
      timerPausedAtRef.current = null;
      setTimerPaused(false);
      const payload = await jpost<{ state: RoomState }>(`${API_BASE}/api/v1/rooms`, {
        league: {
          teams,
          rounds: derivedRoundsPreview,
          bench,
          ai_think_seconds: aiThink,
          scoring_preset: scoringPreset,
          starters
        },
        user_slot: userSlot
      });
      setSelectedTeamSlot(userSlot);
      setRoom(payload.state);
      await refreshRoomViews(payload.state);
      await runCpuPacing(payload.state.room_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create room");
    } finally {
      setLoading(false);
    }
  }

  function exitToLobby() {
    cpuLoopingRef.current = false;
    setIsCpuThinking(false);
    setRoom(null);
    setPlayers([]);
    setRecs([]);
    setQuery("");
    setPositionFilter("ALL");
    setError("");
    setSelectedPlayer(null);
    setSelectedCard(null);
    setCardSeason(2025);
    turnDeadlineRef.current = null;
    timerPausedAtRef.current = null;
    setTimerPaused(false);
    setTimeRemaining(pickClockSec);
  }

  async function makePick(playerKey: string) {
    if (!room) return;
    setLoading(true);
    setError("");
    try {
      setIsAutoFinishing(false);
      const updated = await jpost<RoomState>(`${API_BASE}/api/v1/rooms/${room.room_id}/pick`, { player_key: playerKey });
      setRoom(updated);
      await refreshRoomViews(updated);
      turnDeadlineRef.current = null;
      timerPausedAtRef.current = null;
      setTimeRemaining(pickClockSec);
      setTimerPaused(false);
      await runCpuPacing(updated.room_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to make pick");
    } finally {
      setLoading(false);
    }
  }

  async function openPlayer(player: Player) {
    if (!room) return;
    setSelectedPlayer(player);
    setSelectedCard(null);
    await loadPlayerCard(player, cardSeason);
  }

  async function loadPlayerCard(player: Player, season: 2024 | 2025) {
    if (!room) return;
    const params = new URLSearchParams({
      season: String(season),
      scoring_preset: room.league.scoring_preset
    });
    try {
      const card = await jget<PlayerCard>(
        `${API_BASE}/api/v1/rooms/${room.room_id}/players/${encodeURIComponent(player.player_key)}/card?${params.toString()}`
      );
      setSelectedCard(card);
    } catch {
      setSelectedCard({
        player_key: player.player_key,
        player_name: player.player_name,
        position: player.position,
        team: player.team,
        headshot_url: null,
        season,
        scoring_preset: room.league.scoring_preset,
        adp: player.adp,
        fpts: player.fpts ?? null,
        game_log: []
      });
    }
  }

  async function openPick(pick: Pick) {
    await openPlayer({
      player_key: pick.player_key,
      player_name: pick.player_name,
      position: pick.position,
      team: pick.team,
      bye_week: pick.bye_week ?? null,
      adp: pick.pick_no,
      rank: pick.pick_no
    });
  }

  async function openOverrideModal(pick: Pick) {
    if (!room) return;
    const availableRes = await jget<{ players: Player[] }>(
      `${API_BASE}/api/v1/rooms/${room.room_id}/players?top_n=500&search=&position=`
    );
    const laterDraftable = room.picks
      .filter((p) => p.pick_no >= pick.pick_no)
      .map((p) => ({
        player_key: p.player_key,
        player_name: p.player_name,
        position: p.position,
        team: p.team,
        adp: p.pick_no,
        rank: p.pick_no
      }));
    const merged = [...availableRes.players, ...laterDraftable];
    const dedup = new Map<string, Player>();
    for (const p of merged) {
      if (!dedup.has(p.player_key)) dedup.set(p.player_key, p);
    }
    const sorted = Array.from(dedup.values()).sort((a, b) => a.adp - b.adp);
    setOverridePool(sorted);
    setOverrideTargetPick(pick);
    setOverrideChoiceKey(pick.player_key);
  }

  async function applyOverridePick() {
    if (!room || !overrideTargetPick || !overrideChoiceKey) return;
    setLoading(true);
    setError("");
    try {
      setIsAutoFinishing(false);
      const res = await jpost<{ state: RoomState }>(`${API_BASE}/api/v1/rooms/${room.room_id}/override-cpu-pick`, {
        pick_no: overrideTargetPick.pick_no,
        player_key: overrideChoiceKey
      });
      setRoom(res.state);
      setOverrideTargetPick(null);
      setOverridePool([]);
      setOverrideChoiceKey("");
      await refreshRoomViews(res.state);
      await runCpuPacing(res.state.room_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to override pick");
    } finally {
      setLoading(false);
    }
  }

  async function handleAutoFinishDraft() {
    if (!room || room.complete || isAutoFinishing) return;
    setLoading(true);
    setIsAutoFinishing(true);
    setError("");
    cpuLoopingRef.current = false;
    setIsCpuThinking(false);
    try {
      const res = await jpost<{ state: RoomState }>(`${API_BASE}/api/v1/rooms/${room.room_id}/simulate-to-end`, {});
      const fresh = await jget<RoomState>(`${API_BASE}/api/v1/rooms/${room.room_id}`);
      const next = fresh.complete ? fresh : res.state;
      setRoom(next);
      await refreshRoomViews(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to auto-finish draft");
    } finally {
      setLoading(false);
      setIsAutoFinishing(false);
    }
  }

  useEffect(() => {
    if (!room) return;
    setSelectedTeamSlot((prev) => (prev > 0 ? prev : room.user_slot));
  }, [room?.room_id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    queryRef.current = query;
  }, [query]);

  useEffect(() => {
    positionFilterRef.current = positionFilter;
  }, [positionFilter]);

  useEffect(() => {
    if (!selectedPlayer) return;
    loadPlayerCard(selectedPlayer, cardSeason).catch(() => undefined);
  }, [cardSeason]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!room) return;
    const t = setTimeout(() => {
      refreshRoomViews(room, { search: query, position: positionFilter }).catch(() => undefined);
    }, 150);
    return () => clearTimeout(t);
  }, [query, positionFilter, room]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!room || room.complete) return;
    if (room.current_slot !== room.user_slot) {
      turnDeadlineRef.current = null;
      timerPausedAtRef.current = null;
      setTimerPaused(false);
      return;
    }
    if (turnDeadlineRef.current === null) {
      turnDeadlineRef.current = Date.now() + pickClockSec * 1000;
      timerPausedAtRef.current = null;
      setTimeRemaining(pickClockSec);
    }
    const timer = setInterval(() => {
      if (turnDeadlineRef.current === null) return;
      if (timerPaused) return;
      const remaining = Math.max(0, Math.ceil((turnDeadlineRef.current - Date.now()) / 1000));
      setTimeRemaining(remaining);
      if (remaining === 0 && !autoPickRef.current && !loading) {
        autoPickRef.current = true;
        const best = visibleRecs[0]?.player?.player_key ?? visiblePlayers[0]?.player_key;
        if (best) {
          makePick(best).finally(() => {
            autoPickRef.current = false;
          });
        } else {
          autoPickRef.current = false;
        }
      }
    }, 250);
    return () => clearInterval(timer);
  }, [room?.pick_no, room?.current_slot, room?.complete, pickClockSec, visibleRecs, visiblePlayers, loading, timerPaused]); // eslint-disable-line react-hooks/exhaustive-deps

  function onDigitsOnlyChange(value: string, setter: (v: string) => void) {
    if (/^\d*$/.test(value)) {
      setter(value);
    }
  }

  function onDecimalChange(value: string, setter: (v: string) => void) {
    if (/^\d*(\.\d*)?$/.test(value)) {
      setter(value);
    }
  }

  function toggleTimerPause() {
    if (!room || room.complete || room.current_slot !== room.user_slot) return;
    if (!timerPaused) {
      timerPausedAtRef.current = Date.now();
      setTimerPaused(true);
      return;
    }
    if (turnDeadlineRef.current !== null && timerPausedAtRef.current !== null) {
      const pausedForMs = Date.now() - timerPausedAtRef.current;
      turnDeadlineRef.current += pausedForMs;
    }
    timerPausedAtRef.current = null;
    setTimerPaused(false);
  }

  return (
    <div className="app-wrap">
      <div className="top-bar">
        <h1>{isResultsMode ? "Fantasy Football Mock Draft Results" : "Fantasy Football Mock Draft"}</h1>
        <div className="meta">
          {room
            ? isResultsMode
              ? `Room ${room.room_id.slice(0, 8)} | Draft complete | ${room.total_picks} picks finalized`
              : `Room ${room.room_id.slice(0, 8)} | Pick ${room.pick_no}/${room.total_picks} | On the clock: Team ${room.current_slot}`
            : "Create a room to begin"}
          {room && !room.complete && room.current_slot === room.user_slot && (
            <button
              type="button"
              className={`clock-badge clock-${timerUrgency} ${timerUrgency === "critical" && !timerPaused ? "clock-flash" : ""}`}
              onClick={toggleTimerPause}
              title="Pause/resume draft timer"
            >
              {timerPaused ? "Paused" : `Your clock: ${timeRemaining}s`}
            </button>
          )}
          {isCpuThinking && <span className="ai-thinking-chip">AI thinking...</span>}
        </div>
      </div>
      <div className="main-grid">
        <aside className="panel">
          <h2>Roster / Setup</h2>
          <div className="panel-content">
            {!room && (
              <div className="lobby-wrap">
                <div className="lobby-section">
                  <div className="lobby-section-title">Draft Settings</div>
                  <div className="lobby-grid">
                    <label className="lobby-field">
                      <span>Teams</span>
                      <input
                        className="input-compact"
                        type="text"
                        inputMode="numeric"
                        placeholder="12"
                        value={teamsInput}
                        onChange={(e) => onDigitsOnlyChange(e.target.value, setTeamsInput)}
                      />
                    </label>
                    <label className="lobby-field">
                      <span>Draft Position</span>
                      <input
                        className="input-compact"
                        type="text"
                        inputMode="numeric"
                        placeholder="10"
                        value={userSlotInput}
                        onChange={(e) => onDigitsOnlyChange(e.target.value, setUserSlotInput)}
                      />
                    </label>
                    <label className="lobby-field">
                      <span>Scoring</span>
                      <select value={scoringPreset} onChange={(e) => setScoringPreset(e.target.value)}>
                        <option value="standard">Standard</option>
                        <option value="half_ppr">Half-PPR</option>
                        <option value="ppr">PPR</option>
                      </select>
                    </label>
                    <label className="lobby-field">
                      <span>User clock (seconds)</span>
                      <input
                        className="input-compact"
                        type="text"
                        inputMode="numeric"
                        placeholder="60"
                        value={clockInput}
                        onChange={(e) => onDigitsOnlyChange(e.target.value, setClockInput)}
                      />
                    </label>
                    <label className="lobby-field">
                      <span>AI think (seconds)</span>
                      <input
                        className="input-compact"
                        type="text"
                        inputMode="decimal"
                        placeholder="0"
                        value={aiThinkInput}
                        onChange={(e) => onDecimalChange(e.target.value, setAiThinkInput)}
                      />
                    </label>
                  </div>
                </div>

                <div className="lobby-section">
                  <div className="lobby-section-title">Roster Settings</div>
                  <div className="lobby-roster-grid">
                    {(
                      [
                        ["QB", "qb"],
                        ["RB", "rb"],
                        ["WR", "wr"],
                        ["TE", "te"],
                      ["FLX", "flex"],
                      ["SFL", "superflex"],
                        ["K", "k"],
                        ["DST", "dst"],
                      ["BN", "bench"]
                      ] as const
                    ).map(([label, key]) => (
                      <label className="lobby-field lobby-mini-field" key={key}>
                        <span>{label}</span>
                        <input
                          className="input-mini"
                          type="text"
                          inputMode="numeric"
                          value={key === "bench" ? benchInput : startersInput[key]}
                          onChange={(e) =>
                            onDigitsOnlyChange(e.target.value, (v) =>
                              key === "bench"
                                ? setBenchInput(v)
                                : setStartersInput((prev) => ({ ...prev, [key]: v }))
                            )
                          }
                        />
                      </label>
                    ))}
                  </div>
                </div>
                <div className="lobby-derived muted">Derived rounds: {derivedRoundsPreview}</div>
                <button className="lobby-create-btn" onClick={createRoom} disabled={loading}>
                  {loading ? "Starting..." : "Create Draft Room"}
                </button>
              </div>
            )}
            {room && selectedRoster && (
              <>
                <button className="btn-secondary" style={{ width: "100%", marginBottom: 10 }} onClick={exitToLobby}>
                  Exit Draft to Lobby
                </button>
                <label className="muted" style={{ display: "block", marginBottom: 6 }}>
                  Team Name: {selectedTeamName}
                </label>
                <select
                  value={selectedTeamSlot}
                  onChange={(e) => setSelectedTeamSlot(Number(e.target.value))}
                  style={{ marginBottom: 10, width: "100%" }}
                >
                  {Array.from({ length: room.league.teams }).map((_, idx) => {
                    const slot = idx + 1;
                    const label = slot === room.user_slot ? `Team ${slot} (You)` : `Team ${slot}`;
                    return (
                      <option key={slot} value={slot}>
                        {label}
                      </option>
                    );
                  })}
                </select>
                <div className="roster-card">
                  <div className="roster-section-title roster-section-title--split">
                    <span>Starters</span>
                    <span className="roster-bye-header">BYE</span>
                  </div>
                  {lineupView.starters.map((s) => (
                    <div className="roster-row" key={s.slot}>
                      <span className="roster-slot">{s.slot}</span>
                      <span className="roster-player">
                        {s.player ? (
                          <button type="button" className="roster-player-btn" onClick={() => openPick(s.player as Pick)}>
                            <span className="roster-player-name">
                              {s.player.player_name} ({s.player.position})
                            </span>
                            {typeof (s.player as Pick).bye_week === "number" && (
                              <span className="roster-bye">{(s.player as Pick).bye_week}</span>
                            )}
                          </button>
                        ) : (
                          "-"
                        )}
                      </span>
                    </div>
                  ))}
                  <div className="roster-section-title" style={{ marginTop: 10 }}>
                    Bench
                  </div>
                  {lineupView.bench.length === 0 && (
                    <div className="roster-row">
                      <span className="roster-slot">BN</span>
                      <span className="roster-player">-</span>
                    </div>
                  )}
                  {lineupView.bench.map((p, idx) => (
                    <div className="roster-row" key={`bench-${p.player_key}-${idx}`}>
                      <span className="roster-slot">BN{idx + 1}</span>
                      <span className="roster-player">
                        <button type="button" className="roster-player-btn" onClick={() => openPick(p)}>
                          <span className="roster-player-name">
                            {p.player_name} ({p.position})
                          </span>
                          {typeof p.bye_week === "number" && <span className="roster-bye">{p.bye_week}</span>}
                        </button>
                      </span>
                    </div>
                  ))}
                </div>
                <div className="roster-footer">
                  <div className="roster-section-title">Roster Limits</div>
                  <div className="limits-grid">
                    {rosterLimits.map((x) => (
                      <div key={x.key} className="limits-cell">
                        <span className="limits-key">{x.key}</span>
                        <span className="limits-val">
                          {x.cur}/{x.limit}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
            {error && <p className="muted">{error}</p>}
          </div>
        </aside>

        <main className="panel">
          <h2>{isResultsMode ? "Post-Draft Results Room" : "Draft Board"}</h2>
          <div className="panel-content">
            {room && (
              <>
                {isResultsMode && (
                  <div className="results-banner">
                    Your team has been drafted. Review final results and inspect any team roster.
                  </div>
                )}
                {!isResultsMode && (
                  <div className="controls">
                    <button
                      className="btn-secondary"
                      onClick={handleAutoFinishDraft}
                      disabled={isResultsMode || loading || isCpuThinking || isAutoFinishing}
                    >
                      {isAutoFinishing ? "Finishing..." : "Auto-finish draft"}
                    </button>
                  </div>
                )}

                <div className={`draft-board ${isResultsMode ? "draft-board-results" : ""}`}>
                  <table className="board-table">
                    <thead>
                      <tr>
                        {Array.from({ length: room.league.teams }).map((_, i) => (
                          <th key={i}>Team {i + 1}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Array.from({ length: totalRounds }).map((_, roundIdx) => (
                        <tr key={roundIdx}>
                          {Array.from({ length: room.league.teams }).map((__, teamIdx) => {
                            const slot = teamIdx + 1;
                            const pick = room.picks.find((p) => p.round_no === roundIdx + 1 && p.team_slot === slot);
                            return (
                              <td key={`${roundIdx}-${teamIdx}`}>
                                {pick ? (
                                  <div className={`pick-card ${positionClass(pick.position)}`}>
                                    <button type="button" className="pick-card-main" onClick={() => openPick(pick)}>
                                      <span className="pick-label">{formatPickLabel(pick.pick_no, room.league.teams)}</span>
                                      <span className="pick-name-row">
                                        <strong className="pick-name pick-first-name">{splitDisplayName(pick.player_name).first}</strong>
                                        <strong className="pick-name pick-last-name">{splitDisplayName(pick.player_name).last || "\u00A0"}</strong>
                                      </span>
                                      <span className="pick-chip">
                                        {pick.position} | {pick.team}
                                      </span>
                                    </button>
                                    {!isResultsMode && (
                                      <button
                                        type="button"
                                        className="pick-card-override"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          openOverrideModal(pick);
                                        }}
                                      >
                                        Override
                                      </button>
                                    )}
                                  </div>
                                ) : (
                                  <div className="pick-card pick-empty">
                                    <span className="muted">-</span>
                                  </div>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {!isResultsMode && <div className="lower-grid">
                  <div className="lower-col">
                    <div className="players-header-row">
                      <h3>Available Players</h3>
                      <div className="players-controls">
                        <select value={positionFilter} onChange={(e) => setPositionFilter(e.target.value)}>
                          <option value="ALL">All Pos</option>
                          <option value="QB">QB</option>
                          <option value="RB">RB</option>
                          <option value="WR">WR</option>
                          <option value="TE">TE</option>
                          <option value="K">K</option>
                          <option value="DST">DST</option>
                        </select>
                        <input
                          placeholder="Search player..."
                          value={query}
                          onChange={(e) => setQuery(e.target.value)}
                          className="player-search-input"
                        />
                      </div>
                    </div>
                    <div className="players-scroll">
                      <table className="players-table">
                        <thead>
                          <tr>
                            <th>RK</th>
                            <th>PLAYER</th>
                            <th>POS</th>
                            <th>TEAM</th>
                            <th>ADP</th>
                            <th>FPTS</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {visiblePlayers.map((p) => (
                            <tr key={p.player_key} onClick={() => openPlayer(p)}>
                              <td>{p.rank}</td>
                              <td>{p.player_name}</td>
                              <td>{p.position}</td>
                              <td>{p.team}</td>
                              <td>{p.adp.toFixed(1)}</td>
                              <td>{p.fpts ? p.fpts.toFixed(1) : "-"}</td>
                              <td>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    makePick(p.player_key);
                                  }}
                                  disabled={!room || room.current_slot !== room.user_slot || room.complete}
                                >
                                  Draft
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="lower-col best-picks-col">
                    <h3>Best Picks</h3>
                    <div className="players-scroll">
                      <table className="players-table">
                        <thead>
                          <tr>
                            <th>Player</th>
                            <th>Score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleRecs.map((r) => (
                            <tr
                              key={r.player.player_key}
                              className={!room || room.current_slot !== room.user_slot || room.complete ? "" : "best-pick-action"}
                              onClick={() => {
                                if (!room || room.current_slot !== room.user_slot || room.complete) return;
                                makePick(r.player.player_key);
                              }}
                            >
                              <td>
                                {r.player.player_name}
                                <span className="pick-chip">
                                  {r.player.position} {r.player.team}
                                </span>
                              </td>
                              <td>{r.score.toFixed(2)}</td>
                            </tr>
                          ))}
                          {visibleRecs.length === 0 && (
                            <tr>
                              <td colSpan={2} className="muted">
                                No recommendations yet.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>}
              </>
            )}
            {!room && <p className="muted">Configure your league and click "Create Draft Room".</p>}
          </div>
        </main>
      </div>

      {overrideTargetPick && (
        <div className="modal-backdrop" onClick={() => setOverrideTargetPick(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>
              Override Pick {formatPickLabel(overrideTargetPick.pick_no, room?.league.teams ?? 12)}
            </h2>
            <p className="muted">
              Original pick: {overrideTargetPick.player_name} ({overrideTargetPick.position} {overrideTargetPick.team})
            </p>
            <label className="muted">Replacement player</label>
            <select
              value={overrideChoiceKey}
              onChange={(e) => setOverrideChoiceKey(e.target.value)}
              style={{ width: "100%", marginTop: 6, marginBottom: 12 }}
            >
              {overridePool.map((p) => (
                <option key={p.player_key} value={p.player_key}>
                  {p.player_name} ({p.position} {p.team}) - ADP {p.adp.toFixed(1)}
                </option>
              ))}
            </select>
            <div className="controls">
              <button className="btn-secondary" onClick={() => setOverrideTargetPick(null)}>
                Cancel
              </button>
              <button onClick={applyOverridePick} disabled={loading || !overrideChoiceKey}>
                {loading ? "Applying..." : "Apply Override and Rewind"}
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedPlayer && (
        <div className="modal-backdrop" onClick={() => setSelectedPlayer(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="player-card-top">
              <div className="player-card-photo-col">
                {selectedCard?.headshot_url ? (
                  <img
                    className="player-card-headshot player-card-headshot--lg"
                    src={selectedCard.headshot_url}
                    alt={`${selectedPlayer.player_name} headshot`}
                  />
                ) : (
                  <div className="player-card-headshot player-card-headshot--lg player-card-headshot-empty" />
                )}
              </div>

              <div className="player-card-info-col">
                <div className="player-card-identity">
                  <div className="player-card-name">{selectedPlayer.player_name}</div>
                  <div className="player-card-subline player-card-team">{teamDisplayName(selectedPlayer.team)}</div>
                  <div className="player-card-kv">
                    <span className="player-card-kv-label">POS</span>
                    <span className="player-card-kv-value">{selectedPlayer.position}</span>
                  </div>
                  <div className="player-card-kv">
                    <span className="player-card-kv-label">STATUS</span>
                    <span className="player-card-kv-value">{selectedCard?.status_tag ?? "NAN"}</span>
                  </div>
                </div>

                <div className="player-card-right-col">
                  <button
                    type="button"
                    className="modal-close"
                    onClick={() => setSelectedPlayer(null)}
                    aria-label="Close player card"
                    title="Close"
                  >
                    ×
                  </button>

                  <div className="player-card-metrics">
                    <div className="player-card-metric">
                      <span className="player-card-metric-label">League</span>
                      <span className="player-card-metric-value">
                        {(selectedCard?.scoring_preset ?? room?.league.scoring_preset ?? "ppr").replace("_", "-").toUpperCase()}
                      </span>
                    </div>
                    <div className="player-card-metric">
                      <span className="player-card-metric-label">ADP</span>
                      <span className="player-card-metric-value">{(selectedCard?.adp ?? selectedPlayer.adp).toFixed(1)}</span>
                    </div>
                    <div className="player-card-metric">
                      <span className="player-card-metric-label">{cardSeason} Proj</span>
                      <span className="player-card-metric-value">{selectedCard?.fpts ?? selectedPlayer.fpts ?? "--"}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {selectedCard?.injury_note && <p className="muted">Injury note: {selectedCard.injury_note}</p>}

            <div className="player-card-log-header">
              <div className="player-card-log-title">
                <h3>Weekly Game Log:</h3>
                <select
                  className="player-card-season-select"
                  value={cardSeason}
                  onChange={(e) => setCardSeason(Number(e.target.value) as 2024 | 2025)}
                >
                  <option value={2024}>2024</option>
                  <option value={2025}>2025</option>
                </select>
              </div>
            </div>
            <div className="player-card-game-log">
              <table className="players-table player-card-table">
                <thead>
                  <tr>
                    <th>WK</th>
                    <th>OPP</th>
                    {cardColumnsForPosition(selectedPlayer.position).map((col) => (
                      <th key={col.key}>{col.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(selectedCard?.game_log ?? []).map((g) => (
                    <tr key={`${g.week}-${g.opponent ?? "na"}`}>
                      <td>{g.week}</td>
                      <td>{g.opponent ?? "--"}</td>
                      {cardColumnsForPosition(selectedPlayer.position).map((col) => (
                        <td key={col.key}>{col.render(g)}</td>
                      ))}
                    </tr>
                  ))}
                  {(selectedCard?.game_log ?? []).length > 0 && (
                    <tr className="player-card-totals-row">
                      <td colSpan={2}>TOTAL</td>
                      {cardColumnsForPosition(selectedPlayer.position).map((col) => (
                        <td key={col.key}>
                          {col.render(totalsRowForPosition(selectedPlayer.position, selectedCard?.game_log ?? []))}
                        </td>
                      ))}
                    </tr>
                  )}
                  {(selectedCard?.game_log ?? []).length === 0 && (
                    <tr>
                      <td colSpan={2 + cardColumnsForPosition(selectedPlayer.position).length} className="muted">
                        No game log available.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

