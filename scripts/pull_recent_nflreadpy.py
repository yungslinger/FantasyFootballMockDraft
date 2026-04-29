import argparse
from pathlib import Path

import nflreadpy as nfl
import pandas as pd


def _default_output_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "data" / "inputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "nfl_player_ids.csv"


def main() -> int:
    p = argparse.ArgumentParser(description="Download nflreadpy player metadata into nfl_player_ids.csv.")
    p.add_argument(
        "--out",
        type=str,
        default=str(_default_output_path()),
        help="Output CSV path (defaults to data/inputs/nfl_player_ids.csv).",
    )
    args = p.parse_args()
    output_csv = Path(args.out)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    print("⏳ Loading player + team data...")

    # 1. Individual players
    players_pl = nfl.load_players()
    df_players = players_pl.to_pandas()

    # 2. Team info (for D/ST)
    teams_pl = nfl.load_teams()
    df_teams = teams_pl.to_pandas()

    print(f"✅ Loaded {len(df_players):,} players + {len(df_teams):,} teams")

    # === Keep the same player columns as before ===
    selected_cols = [
        "display_name",
        "first_name",
        "last_name",
        "football_name",
        "latest_team",
        "gsis_id",
        "espn_id",
        "headshot",
        "position",
        "status",
        "jersey_number",
        "birth_date",
        "college_name",
    ]

    available = [col for col in selected_cols if col in df_players.columns]
    simple_df = df_players[available].copy()

    simple_df = simple_df.rename(
        columns={
            "display_name": "player_name",
            "latest_team": "player_team",
            "gsis_id": "nflreadpy_id",
            "espn_id": "espn_id",
            "headshot": "headshot",
        }
    )

    # === ADD D/ST rows with ESPN-style headshots ===
    dst_rows = []
    for _, team in df_teams.iterrows():
        team_abbr = team["team_abbr"]  # e.g. "GB", "PHI", "SF"

        # Build the exact ESPN headshot URL you wanted
        headshot_url = f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nfl/500/{team_abbr.lower()}.png&h=200&w=200"

        dst_rows.append(
            {
                "player_name": f"{team['team_name']} D/ST",  # e.g. "Green Bay Packers D/ST"
                "player_team": team_abbr,
                "nflreadpy_id": f"DST_{team_abbr}",  # e.g. "DST_GB"
                "espn_id": None,
                "headshot": headshot_url,
                "position": "DST",
                "status": "Active",
            }
        )

    dst_df = pd.DataFrame(dst_rows)

    # Combine players + D/ST
    final_df = pd.concat([simple_df, dst_df], ignore_index=True)

    # Clean & sort (players first, then D/ST at the bottom)
    final_df = final_df.dropna(subset=["player_name", "nflreadpy_id"])
    final_df = final_df.sort_values(["player_team", "player_name"]).reset_index(drop=True)

    final_df.to_csv(output_csv, index=False)

    print(f"\n✅ DONE! Saved {len(final_df):,} total entries to {output_csv}")
    print(f"   → {len(df_players):,} players + {len(dst_df):,} D/ST units")
    print("\nD/ST sample (last 5 rows) — now with ESPN headshots:")
    print(final_df.tail(5)[["player_name", "player_team", "nflreadpy_id", "headshot"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())