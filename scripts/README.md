## Scripts (repo root)

Run these from the **repository root** (same folder as `backend/` and `frontend/`).

| Script | Purpose |
|--------|---------|
| `pull_recent_nflreadpy.py` | Refresh `nfl_player_ids.csv` from `nflreadpy` (used when rebuilding the master CSV). |
| `build_fantasypros_master.py` | Merge FantasyPros export CSVs + IDs into the master rankings file under `reference/`. |
| `compare_fantasypros_master.py` | Offline diff between the shipped master and a generated CSV (handy when 2026 data lands). |

### Refresh player IDs

```bash
python scripts/pull_recent_nflreadpy.py
```

Default output: `data/inputs/nfl_player_ids.csv`.

### Build master rankings CSV

```bash
python scripts/build_fantasypros_master.py
```

Defaults: read `data/inputs/`, write `reference/FantasyPros_2025_Master_Projections_With_ADP.csv`.

### Compare reference vs generated master

After building to a separate file (for example `data/generated/...`):

```bash
python scripts/compare_fantasypros_master.py
```

Defaults: `reference/FantasyPros_2025_Master_Projections_With_ADP.csv` vs `data/generated/FantasyPros_2025_Master_Projections_With_ADP.generated.csv`.
