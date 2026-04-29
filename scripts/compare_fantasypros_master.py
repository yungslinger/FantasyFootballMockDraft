from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


def _base_pos(value: str) -> str:
    m = re.match(r"([A-Za-z]+)", str(value or "").strip())
    return m.group(1).upper() if m else ""


def _clean_name(value: str) -> str:
    s = str(value or "").lower().strip()
    s = re.sub(r"[']", "", s)
    s = re.sub(r"[^a-z0-9\s.\-]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_suffix(name: str) -> str:
    parts = [p for p in _clean_name(name).replace("-", " ").split(" ") if p]
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    while parts and parts[-1] in suffixes:
        parts = parts[:-1]
    return " ".join(parts)


def _identity_key(df: pd.DataFrame) -> pd.Series:
    name = df["Player"].fillna("").map(_strip_suffix)
    team = df["Team"].fillna("").astype(str)
    posb = df["POS"].fillna("").map(_base_pos)
    return name + "|" + team + "|" + posb


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description="Compare rebuilt FantasyPros master CSV vs reference.")
    p.add_argument(
        "--ref",
        type=str,
        default=None,
        help="Reference master CSV (defaults to reference/FantasyPros_2025_Master_Projections_With_ADP.csv).",
    )
    p.add_argument(
        "--out",
        type=str,
        default=None,
        help="Generated master CSV to compare (defaults to data/generated/FantasyPros_2025_Master_Projections_With_ADP.generated.csv).",
    )
    args = p.parse_args()

    ref_path = Path(args.ref) if args.ref else (repo_root / "reference" / "FantasyPros_2025_Master_Projections_With_ADP.csv")
    out_path = (
        Path(args.out)
        if args.out
        else (repo_root / "data" / "generated" / "FantasyPros_2025_Master_Projections_With_ADP.generated.csv")
    )
    df_ref = pd.read_csv(ref_path)
    df_out = pd.read_csv(out_path)

    print(f"ref: {ref_path} rows={len(df_ref):,} cols={len(df_ref.columns):,}")
    print(f"out: {out_path} rows={len(df_out):,} cols={len(df_out.columns):,}")
    if set(df_ref.columns) != set(df_out.columns):
        print("Column set differs!")
        print("only in ref:", sorted(set(df_ref.columns) - set(df_out.columns)))
        print("only in out:", sorted(set(df_out.columns) - set(df_ref.columns)))

    # Strict key compare (Player|POS|Team)
    key_cols = ["Player", "POS", "Team"]
    refk = df_ref[key_cols].fillna("").astype(str).agg("|".join, axis=1)
    outk = df_out[key_cols].fillna("").astype(str).agg("|".join, axis=1)
    ref_set = set(refk)
    out_set = set(outk)
    print("\nStrict key (Player|POS|Team)")
    print("overlap:", len(ref_set & out_set))
    print("only_ref:", len(ref_set - out_set))
    print("only_out:", len(out_set - ref_set))

    # Identity key compare (clean_name|Team|base_pos)
    ref_id = _identity_key(df_ref)
    out_id = _identity_key(df_out)
    ref_id_set = set(ref_id)
    out_id_set = set(out_id)
    print("\nIdentity key (cleaned_name|Team|base_pos)")
    print("overlap:", len(ref_id_set & out_id_set))
    print("only_ref:", len(ref_id_set - out_id_set))
    print("only_out:", len(out_id_set - ref_id_set))

    # POS-rank diffs for identities that overlap
    ref_map = (
        pd.DataFrame({"id": ref_id, "pos": df_ref["POS"].fillna("")})
        .groupby("id")["pos"]
        .agg(lambda s: sorted(set(map(str, s)))[:5])
    )
    out_map = (
        pd.DataFrame({"id": out_id, "pos": df_out["POS"].fillna("")})
        .groupby("id")["pos"]
        .agg(lambda s: sorted(set(map(str, s)))[:5])
    )
    diffs = []
    for k in (ref_id_set & out_id_set):
        if ref_map.get(k) != out_map.get(k):
            diffs.append((k, ref_map.get(k), out_map.get(k)))
    diffs.sort(key=lambda x: x[0])
    print("\nPOS label diffs for matching identities:", len(diffs))
    for row in diffs[:25]:
        print(" -", row)

    # Missing enrichment
    if "NFLREADPY_ID" in df_out.columns:
        print("\nMissing enrichment in out:")
        print("NFLREADPY_ID missing:", int(df_out["NFLREADPY_ID"].isna().sum()))
        print("ESPN_ID missing:", int(df_out["ESPN_ID"].isna().sum()) if "ESPN_ID" in df_out.columns else "n/a")
        print("HEADSHOT missing:", int(df_out["HEADSHOT"].isna().sum()) if "HEADSHOT" in df_out.columns else "n/a")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

