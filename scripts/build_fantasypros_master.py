from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


TEAM_RENAMES = {
    "JAC": "JAX",
    "WSH": "WAS",
    "LA": "LAR",
    "LVR": "LV",
}


MASTER_COLS = [
    "Player",
    "Team",
    "POS",
    "FPTS_STD",
    "FPTS_PPR",
    "FPTS_HPPR",
    "ADP_STD",
    "ADP_PPR",
    "ADP_HPPR",
    "RUSH_ATT",
    "RUSH_YDS",
    "RUSH_TDS",
    "REC",
    "REC_YDS",
    "REC_TDS",
    "FUM_LOST",
    "QB_ATT",
    "QB_CMP",
    "QB_YDS",
    "QB_TDS",
    "QB_INTS",
    "K_FG",
    "K_FGA",
    "K_XPT",
    "DST_SACK",
    "DST_INT",
    "DST_FR",
    "DST_FF",
    "DST_TD",
    "DST_SAFETY",
    "DST_PA",
    "DST_YDS_AGN",
    "ESPN_ID",
    "NFLREADPY_ID",
    "HEADSHOT",
]


def _clean_name(value: str) -> str:
    s = str(value or "").strip().lower()
    s = re.sub(r"[']", "", s)
    s = re.sub(r"[^a-z0-9\s.-]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_suffixes(name: str) -> str:
    """
    Normalize for lenient joining across vendors.
    """
    parts = [p for p in _clean_name(name).replace("-", " ").split(" ") if p]
    if not parts:
        return ""
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    while parts and parts[-1] in suffixes:
        parts = parts[:-1]
    return " ".join(parts)


def _base_position(value: str) -> str:
    m = re.match(r"([A-Za-z]+)", str(value or "").strip())
    return m.group(1).upper() if m else ""


def _norm_team(value: str) -> str:
    t = str(value or "").upper().strip()
    t = TEAM_RENAMES.get(t, t)
    if t in {"", "NAN", "NONE"}:
        return ""
    return t


def _to_num(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.replace(",", "", regex=False)
    s = s.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NONE": pd.NA, "NaN": pd.NA})
    return pd.to_numeric(s, errors="coerce")


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _col(df: pd.DataFrame, *names: str) -> pd.Series:
    """
    Return the first column found from a list of candidate names.
    Handles pandas' default duplicate-column mangling (e.g. YDS.1, TDS.1).
    """
    for n in names:
        if n in df.columns:
            return df[n]
    raise KeyError(f"Missing expected column. Tried: {list(names)}. Found: {list(df.columns)}")


def _load_qb(path: Path) -> pd.DataFrame:
    df = _read_csv(path)
    required = {"Player", "Team", "ATT", "CMP", "YDS", "TDS", "INTS", "FL", "FPTS"}
    if not required.issubset(df.columns):
        raise ValueError(f"QB file missing columns: {sorted(required - set(df.columns))}")

    out = pd.DataFrame()
    out["Player"] = df["Player"].astype(str).str.strip()
    out["Team"] = df["Team"].map(_norm_team)
    out["POS"] = "QB"
    out["QB_ATT"] = _to_num(_col(df, "ATT"))
    out["QB_CMP"] = _to_num(_col(df, "CMP"))
    out["QB_YDS"] = _to_num(_col(df, "YDS"))
    out["QB_TDS"] = _to_num(_col(df, "TDS"))
    out["QB_INTS"] = _to_num(_col(df, "INTS"))
    out["RUSH_ATT"] = _to_num(_col(df, "ATT.1", "ATT_1", "RUSH_ATT"))
    out["RUSH_YDS"] = _to_num(_col(df, "YDS.1", "YDS_1", "RUSH_YDS"))
    out["RUSH_TDS"] = _to_num(_col(df, "TDS.1", "TDS_1", "RUSH_TDS"))
    out["FUM_LOST"] = _to_num(df["FL"])
    fpts = _to_num(df["FPTS"])
    out["FPTS_STD"] = fpts
    out["FPTS_PPR"] = fpts
    out["FPTS_HPPR"] = fpts
    return out


def _load_flex(path: Path, *, scoring: str) -> pd.DataFrame:
    df = _read_csv(path)
    required = {"Player", "Team", "POS", "ATT", "YDS", "TDS", "REC", "FL", "FPTS"}
    if not required.issubset(df.columns):
        raise ValueError(f"FLEX file missing columns: {sorted(required - set(df.columns))}")

    out = pd.DataFrame()
    out["Player"] = df["Player"].astype(str).str.strip()
    out["Team"] = df["Team"].map(_norm_team)
    out["POS"] = df["POS"].astype(str).str.strip()
    out["POS_BASE"] = out["POS"].map(_base_position)
    out["RUSH_ATT"] = _to_num(df["ATT"])
    out["RUSH_YDS"] = _to_num(_col(df, "YDS"))
    out["RUSH_TDS"] = _to_num(_col(df, "TDS"))
    out["REC"] = _to_num(df["REC"])
    out["REC_YDS"] = _to_num(_col(df, "YDS.1", "YDS_1", "REC_YDS"))
    out["REC_TDS"] = _to_num(_col(df, "TDS.1", "TDS_1", "REC_TDS"))
    out["FUM_LOST"] = _to_num(df["FL"])
    out[f"FPTS_{scoring}"] = _to_num(df["FPTS"])
    return out


def _load_k(path: Path) -> pd.DataFrame:
    df = _read_csv(path)
    required = {"Player", "Team", "FG", "FGA", "XPT", "FPTS"}
    if not required.issubset(df.columns):
        raise ValueError(f"K file missing columns: {sorted(required - set(df.columns))}")

    out = pd.DataFrame()
    out["Player"] = df["Player"].astype(str).str.strip()
    out["Team"] = df["Team"].map(_norm_team)
    out["POS"] = "K"
    out["K_FG"] = _to_num(df["FG"])
    out["K_FGA"] = _to_num(df["FGA"])
    out["K_XPT"] = _to_num(df["XPT"])
    fpts = _to_num(df["FPTS"])
    out["FPTS_STD"] = fpts
    out["FPTS_PPR"] = fpts
    out["FPTS_HPPR"] = fpts
    return out


def _load_dst(path: Path) -> pd.DataFrame:
    df = _read_csv(path)
    required = {"Player", "Team", "SACK", "INT", "FR", "FF", "TD", "SAFETY", "PA", "YDS_AGN", "FPTS"}
    if not required.issubset(df.columns):
        raise ValueError(f"DST file missing columns: {sorted(required - set(df.columns))}")

    out = pd.DataFrame()
    out["Player"] = df["Player"].astype(str).str.strip()
    # FantasyPros DST projection export often has blank Team; master keeps it blank.
    out["Team"] = ""
    out["POS"] = "DST"
    out["DST_SACK"] = _to_num(df["SACK"])
    out["DST_INT"] = _to_num(df["INT"])
    out["DST_FR"] = _to_num(df["FR"])
    out["DST_FF"] = _to_num(df["FF"])
    out["DST_TD"] = _to_num(df["TD"])
    out["DST_SAFETY"] = _to_num(df["SAFETY"])
    out["DST_PA"] = _to_num(df["PA"])
    out["DST_YDS_AGN"] = _to_num(df["YDS_AGN"])
    fpts = _to_num(df["FPTS"])
    out["FPTS_STD"] = fpts
    out["FPTS_PPR"] = fpts
    out["FPTS_HPPR"] = fpts
    return out


def _load_adp(path: Path, *, scoring: str) -> pd.DataFrame:
    df = _read_csv(path)
    required = {"Player", "Team", "POS", "AVG"}
    if not required.issubset(df.columns):
        raise ValueError(f"ADP file missing columns: {sorted(required - set(df.columns))}")

    out = pd.DataFrame()
    out["Player"] = df["Player"].astype(str).str.strip()
    out["Team"] = df["Team"].map(_norm_team)
    out["POS"] = df["POS"].astype(str).str.strip()
    out["POS_BASE"] = out["POS"].map(_base_position)
    out[f"ADP_{scoring}"] = _to_num(df["AVG"])
    return out


def _merge_flex(std: pd.DataFrame, ppr: pd.DataFrame, hppr: pd.DataFrame) -> pd.DataFrame:
    # POS rank differs by scoring preset (e.g. RB1 vs RB2); join using base position.
    key = ["Player", "Team", "POS_BASE"]
    std_base = std.copy()
    ppr_base = ppr.copy()
    hppr_base = hppr.copy()

    merged = std_base.merge(ppr_base[key + ["FPTS_PPR"]], how="outer", on=key)
    merged = merged.merge(hppr_base[key + ["FPTS_HPPR"]], how="outer", on=key)

    # If a row only exists in PPR/HPPR (unlikely), keep a stable POS value.
    if "POS" not in merged.columns:
        merged["POS"] = ""
    merged["POS"] = merged["POS"].where(merged["POS"].astype(str).str.len() > 0, merged["POS_BASE"])

    merged = merged.drop(columns=["POS_BASE"], errors="ignore")
    return merged


def _merge_adp(master: pd.DataFrame, adp_std: pd.DataFrame, adp_ppr: pd.DataFrame, adp_hppr: pd.DataFrame) -> pd.DataFrame:
    out = master.copy()
    out["POS_BASE"] = out["POS"].map(_base_position)
    key = ["Player", "Team", "POS_BASE"]
    out = out.merge(
        adp_std[key + ["ADP_STD", "POS"]].rename(columns={"POS": "POS_STD"}),
        how="left",
        on=key,
    )
    out = out.merge(adp_ppr[key + ["ADP_PPR"]], how="left", on=key)
    out = out.merge(adp_hppr[key + ["ADP_HPPR"]], how="left", on=key)

    # Canonical POS label for QB/K/DST: use STD ADP positional label (e.g. QB7, K12, DST3).
    is_unranked = out["POS_BASE"].eq(out["POS"].astype(str).str.upper().str.strip())
    has_std_pos = out["POS_STD"].astype(str).str.len().gt(0)
    out.loc[is_unranked & has_std_pos, "POS"] = out.loc[is_unranked & has_std_pos, "POS_STD"]

    # DST join: master keeps Team blank; ADP has team. Fill missing ADP by Player+POS match.
    is_dst = out["POS"].map(_base_position).eq("DST")
    if is_dst.any():
        dst_keys = ["Player", "POS_BASE"]
        dst_adp = (
            adp_std[dst_keys + ["ADP_STD", "POS"]].rename(columns={"POS": "POS_STD_dst"})
            .merge(adp_ppr[dst_keys + ["ADP_PPR"]], how="outer", on=dst_keys)
            .merge(adp_hppr[dst_keys + ["ADP_HPPR"]], how="outer", on=dst_keys)
        )
        out = out.merge(
            dst_adp.rename(
                columns={
                    "ADP_STD": "ADP_STD_dst",
                    "ADP_PPR": "ADP_PPR_dst",
                    "ADP_HPPR": "ADP_HPPR_dst",
                }
            ),
            how="left",
            on=dst_keys,
        )
        for c in ["ADP_STD", "ADP_PPR", "ADP_HPPR"]:
            out.loc[is_dst, c] = out.loc[is_dst, c].fillna(out.loc[is_dst, f"{c}_dst"])
        # POS rank for DST where Team mismatch prevented the main merge.
        needs_pos_rank = is_dst & out["POS_BASE"].eq("DST") & out["POS"].astype(str).str.upper().eq("DST")
        if "POS_STD_dst" in out.columns:
            out.loc[needs_pos_rank, "POS"] = out.loc[needs_pos_rank, "POS"].where(
                out.loc[needs_pos_rank, "POS_STD_dst"].astype(str).str.len().eq(0),
                out.loc[needs_pos_rank, "POS_STD_dst"],
            )
        out = out.drop(columns=["ADP_STD_dst", "ADP_PPR_dst", "ADP_HPPR_dst"])
    out = out.drop(columns=["POS_BASE"], errors="ignore")
    out = out.drop(columns=["POS_STD"], errors="ignore")
    return out


def _enrich_with_nfl_player_ids(master: pd.DataFrame, nfl_player_ids_path: Path) -> pd.DataFrame:
    ids = _read_csv(nfl_player_ids_path)
    required = {"player_name", "player_team", "nflreadpy_id", "espn_id", "headshot", "position"}
    if not required.issubset(ids.columns):
        raise ValueError(f"nfl_player_ids missing columns: {sorted(required - set(ids.columns))}")

    ids = ids.copy()
    ids["team"] = ids["player_team"].map(_norm_team)
    ids["pos"] = ids["position"].map(_base_position)
    ids["name_key"] = ids["player_name"].map(_strip_suffixes)
    ids["name_key_full"] = ids["player_name"].map(_clean_name)

    # Non-DST enrichment by (name_key, team, pos).
    base = master.copy()
    base["pos_base"] = base["POS"].map(_base_position)
    base["team_key"] = base["Team"].map(_norm_team)
    base["name_key"] = base["Player"].map(_strip_suffixes)
    base["name_key_full"] = base["Player"].map(_clean_name)

    ids_non_dst = ids[ids["pos"].ne("DST")].copy()
    lookup = ids_non_dst[["name_key", "team", "pos", "espn_id", "nflreadpy_id", "headshot"]].drop_duplicates(
        subset=["name_key", "team", "pos"], keep="first"
    )
    out = base.merge(
        lookup,
        how="left",
        left_on=["name_key", "team_key", "pos_base"],
        right_on=["name_key", "team", "pos"],
    )

    # Fallback: full cleaned name if suffix-stripped didn't match.
    lookup_full = ids_non_dst[
        ["name_key_full", "team", "pos", "espn_id", "nflreadpy_id", "headshot"]
    ].drop_duplicates(subset=["name_key_full", "team", "pos"], keep="first")
    out = out.merge(
        lookup_full.rename(
            columns={
                "espn_id": "espn_id_full",
                "nflreadpy_id": "nflreadpy_id_full",
                "headshot": "headshot_full",
            }
        ),
        how="left",
        left_on=["name_key_full", "team_key", "pos_base"],
        right_on=["name_key_full", "team", "pos"],
    )
    for c in ["espn_id", "nflreadpy_id", "headshot"]:
        out[c] = out[c].where(out[c].astype(str).str.len() > 0, pd.NA)
    out["espn_id"] = out["espn_id"].fillna(out["espn_id_full"])
    out["nflreadpy_id"] = out["nflreadpy_id"].fillna(out["nflreadpy_id_full"])
    out["headshot"] = out["headshot"].fillna(out["headshot_full"])
    out = out.drop(columns=["espn_id_full", "nflreadpy_id_full", "headshot_full"])

    # DST enrichment by matching team name (projection 'Player') to DST 'player_name' without 'D/ST'.
    ids_dst = ids[ids["pos"].eq("DST")].copy()
    if not ids_dst.empty:
        ids_dst["dst_key"] = ids_dst["player_name"].map(
            lambda s: _clean_name(str(s).replace("D/ST", "").replace("Dst", "").replace("DST", "")).strip()
        )
        dst_lookup = ids_dst[["dst_key", "espn_id", "nflreadpy_id", "headshot"]].drop_duplicates(
            subset=["dst_key"], keep="first"
        )
        out["dst_key"] = out.apply(
            lambda r: _clean_name(r["Player"]) if str(r.get("pos_base", "")).upper() == "DST" else "",
            axis=1,
        )
        out = out.merge(
            dst_lookup.rename(
                columns={
                    "espn_id": "espn_id_dst",
                    "nflreadpy_id": "nflreadpy_id_dst",
                    "headshot": "headshot_dst",
                }
            ),
            how="left",
            on="dst_key",
        )
        is_dst = out["pos_base"].astype(str).str.upper().eq("DST")
        out.loc[is_dst, "espn_id"] = out.loc[is_dst, "espn_id"].fillna(out.loc[is_dst, "espn_id_dst"])
        out.loc[is_dst, "nflreadpy_id"] = out.loc[is_dst, "nflreadpy_id"].fillna(out.loc[is_dst, "nflreadpy_id_dst"])
        out.loc[is_dst, "headshot"] = out.loc[is_dst, "headshot"].fillna(out.loc[is_dst, "headshot_dst"])
        out = out.drop(columns=["espn_id_dst", "nflreadpy_id_dst", "headshot_dst", "dst_key"])

    out = out.rename(
        columns={
            "espn_id": "ESPN_ID",
            "nflreadpy_id": "NFLREADPY_ID",
            "headshot": "HEADSHOT",
        }
    )
    out = out.drop(columns=["team", "pos", "pos_base", "team_key", "name_key", "name_key_full"], errors="ignore")
    return out


def build_master(
    *,
    inputs_dir: Path,
    nfl_player_ids_path: Path,
) -> pd.DataFrame:
    qb = _load_qb(inputs_dir / "FantasyPros_Fantasy_Football_Projections_QB.csv")
    k = _load_k(inputs_dir / "FantasyPros_Fantasy_Football_Projections_K.csv")
    dst = _load_dst(inputs_dir / "FantasyPros_Fantasy_Football_Projections_DST.csv")

    flex_std = _load_flex(
        inputs_dir / "FantasyPros_Fantasy_Football_Projections_FLX_STD.csv",
        scoring="STD",
    )
    flex_ppr = _load_flex(
        inputs_dir / "FantasyPros_Fantasy_Football_Projections_FLX_PPR.csv",
        scoring="PPR",
    )
    flex_hppr = _load_flex(
        inputs_dir / "FantasyPros_Fantasy_Football_Projections_FLX_HPPR.csv",
        scoring="HPPR",
    )
    flex = _merge_flex(flex_std, flex_ppr, flex_hppr)

    master = pd.concat([flex, qb, k, dst], ignore_index=True, sort=False)

    adp_std = _load_adp(inputs_dir / "FantasyPros_2025_Overall_ADP_Rankings_STD.csv", scoring="STD")
    adp_ppr = _load_adp(inputs_dir / "FantasyPros_2025_Overall_ADP_Rankings_PPR.csv", scoring="PPR")
    adp_hppr = _load_adp(inputs_dir / "FantasyPros_2025_Overall_ADP_Rankings_HPPR.csv", scoring="HPPR")
    master = _merge_adp(master, adp_std=adp_std, adp_ppr=adp_ppr, adp_hppr=adp_hppr)

    # Canonicalize POS ranks for QB/K/DST within the projected-player subset.
    # FantasyPros ADP files include more players than projections; the reference master
    # uses ranks within this master table (not the ADP file's POS labels).
    if {"POS", "ADP_PPR", "ADP_STD", "ADP_HPPR"}.issubset(master.columns):
        base = master["POS"].map(_base_position)
        for pos in ["QB", "K", "DST"]:
            m = base.eq(pos)
            if not m.any():
                continue
            adp = pd.to_numeric(master.loc[m, "ADP_PPR"], errors="coerce")
            adp = adp.where(adp.notna(), pd.to_numeric(master.loc[m, "ADP_STD"], errors="coerce"))
            adp = adp.where(adp.notna(), pd.to_numeric(master.loc[m, "ADP_HPPR"], errors="coerce"))
            # Deterministic ordering:
            # - primary: ADP ascending (missing ADP goes to bottom)
            # - secondary: cleaned name (stable tie-breaker)
            order_df = pd.DataFrame(
                {
                    "idx": adp.index,
                    "adp_fill": adp.fillna(1e9),
                    "name_key": master.loc[m, "Player"].map(_strip_suffixes),
                }
            )
            order_df = order_df.sort_values(["adp_fill", "name_key"], ascending=[True, True])

            ranks = pd.Series(index=order_df["idx"], data=range(1, len(order_df) + 1))
            master.loc[m, "POS"] = master.loc[m].index.map(lambda i: f"{pos}{int(ranks.get(i))}")

    master = _enrich_with_nfl_player_ids(master, nfl_player_ids_path=nfl_player_ids_path)

    # Canonicalize column set/order.
    for c in MASTER_COLS:
        if c not in master.columns:
            master[c] = pd.NA
    master = master[MASTER_COLS].copy()

    # Ensure Team/POS formatting matches reference style.
    master["Player"] = master["Player"].astype(str).str.strip()
    master["Team"] = master["Team"].astype(str).str.strip()
    master["POS"] = master["POS"].astype(str).str.strip()

    return master


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recreate FantasyPros master projections CSV from FantasyPros import CSVs + nfl_player_ids.csv."
    )
    parser.add_argument(
        "--inputs-dir",
        type=str,
        default=None,
        help="Directory containing the 9 FantasyPros CSVs + nfl_player_ids.csv (defaults to repo_root/data/inputs).",
    )
    parser.add_argument(
        "--fantasyfiles-dir",
        type=str,
        default=None,
        help="Deprecated alias for --inputs-dir (kept for backwards compatibility).",
    )
    parser.add_argument(
        "--nfl-player-ids",
        type=str,
        default=None,
        help="Path to nfl_player_ids.csv (defaults to <inputs-dir>/nfl_player_ids.csv).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output CSV path (defaults to reference/FantasyPros_2025_Master_Projections_With_ADP.csv).",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    inputs_dir = Path(args.inputs_dir) if args.inputs_dir else None
    if inputs_dir is None and args.fantasyfiles_dir:
        inputs_dir = Path(args.fantasyfiles_dir)
    if inputs_dir is None:
        inputs_dir = repo_root / "data" / "inputs"
    nfl_player_ids_path = Path(args.nfl_player_ids) if args.nfl_player_ids else (inputs_dir / "nfl_player_ids.csv")
    out_path = (
        Path(args.out)
        if args.out
        else (repo_root / "reference" / "FantasyPros_2025_Master_Projections_With_ADP.csv")
    )

    master = build_master(inputs_dir=inputs_dir, nfl_player_ids_path=nfl_player_ids_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(out_path, index=False)

    print(f"Wrote master file: {out_path}")
    print(f"Rows: {len(master):,} | Columns: {len(master.columns):,}")
    missing_ids = int(master["NFLREADPY_ID"].isna().sum())
    print(f"Missing NFLREADPY_ID: {missing_ids:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

