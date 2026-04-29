## FantasyPros import CSVs

Put the **nine FantasyPros export CSVs** plus `nfl_player_ids.csv` in this folder.

The shipped **master** file the API loads by default is built from these inputs and written to:

`reference/FantasyPros_2025_Master_Projections_With_ADP.csv`

### Regenerate the master file (optional)

From the repo root (Python env with `pandas` installed):

```bash
python scripts/build_fantasypros_master.py
```

Defaults:

- reads from `data/inputs/`
- writes to `reference/FantasyPros_2025_Master_Projections_With_ADP.csv`
