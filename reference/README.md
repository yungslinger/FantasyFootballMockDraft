# Rankings (reference)

The FastAPI app loads the **master FantasyPros projections + ADP** CSV from this folder by default:

`FantasyPros_2025_Master_Projections_With_ADP.csv`

When a new season’s exports are available, replace this file (or point the API at another path via the room payload’s ranking override, if you wire that up in the client).

To rebuild this file from raw FantasyPros downloads, see `data/inputs/README.md` and `scripts/build_fantasypros_master.py`.
