## Generated outputs (local only)

This folder is **intentionally** part of the repo so paths stay stable, but it normally has **no CSVs** in git.

- **`scripts/compare_fantasypros_master.py`** defaults to reading a rebuilt master from  
  `FantasyPros_2025_Master_Projections_With_ADP.generated.csv` in this directory (after you build with `--out` pointing here, or copy a file in for a diff).
- Any `*.csv` you drop here is **ignored by git** (see root `.gitignore`: `data/generated/*.csv`).

You do **not** need this folder to run the app; it is only for optional offline checks when refreshing rankings.
