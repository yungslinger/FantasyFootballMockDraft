from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app, drafts


client = TestClient(app)


def _new_room(seed: int = 42) -> dict:
    res = client.post(
        "/api/v1/rooms",
        json={
            "league": {
                "teams": 12,
                "rounds": 16,
                "bench": 7,
                "scoring_preset": "ppr",
                "starters": {"qb": 1, "rb": 2, "wr": 2, "te": 1, "flex": 1, "superflex": 0, "k": 0, "dst": 0},
            },
            "user_slot": 10,
            "seed": seed,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_create_room_and_simulate_until_user() -> None:
    payload = _new_room(seed=123)
    room_id = payload["state"]["room_id"]
    # User slot=10 in snake, so CPU must make first 9 picks.
    sim = client.post(f"/api/v1/rooms/{room_id}/simulate-until-user")
    assert sim.status_code == 200, sim.text
    body = sim.json()
    assert body["cpu_picks_made"] == 9
    assert body["state"]["current_slot"] == 10
    assert body["state"]["pick_no"] == 10


def test_seeded_replay_deterministic_first_round() -> None:
    room_a = _new_room(seed=777)["state"]["room_id"]
    room_b = _new_room(seed=777)["state"]["room_id"]
    client.post(f"/api/v1/rooms/{room_a}/simulate-until-user")
    client.post(f"/api/v1/rooms/{room_b}/simulate-until-user")

    picks_a = client.get(f"/api/v1/rooms/{room_a}").json()["picks"]
    picks_b = client.get(f"/api/v1/rooms/{room_b}").json()["picks"]
    keys_a = [p["player_key"] for p in picks_a[:9]]
    keys_b = [p["player_key"] for p in picks_b[:9]]
    assert keys_a == keys_b


def test_full_draft_pick_count() -> None:
    room_id = _new_room(seed=31337)["state"]["room_id"]
    sim = client.post(f"/api/v1/rooms/{room_id}/simulate-to-end")
    assert sim.status_code == 200, sim.text
    state = sim.json()["state"]
    assert state["complete"] is True
    assert len(state["picks"]) == state["total_picks"] == 192


def test_early_round_adp_reasonable_band() -> None:
    room_id = _new_room(seed=43)["state"]["room_id"]
    sim = client.post(f"/api/v1/rooms/{room_id}/simulate-until-user")
    assert sim.status_code == 200, sim.text
    picks = sim.json()["state"]["picks"]
    # Early-round picks should not include extreme reaches.
    for p in picks[:12]:
        # player ADP encoded by order in source file; confidence bucket catches big reaches.
        assert p["confidence_bucket"] != "reach"


def test_single_cpu_pick_endpoint_advances_one_pick() -> None:
    room_id = _new_room(seed=99)["state"]["room_id"]
    res = client.post(f"/api/v1/rooms/{room_id}/simulate-cpu-pick")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cpu_picks_made"] in {0, 1}
    assert body["state"]["pick_no"] == 2


def test_early_picks_stay_near_adp() -> None:
    room_id = _new_room(seed=2026)["state"]["room_id"]
    sim = client.post(f"/api/v1/rooms/{room_id}/simulate-until-user")
    assert sim.status_code == 200, sim.text
    picks = sim.json()["state"]["picks"][:8]
    room = drafts.get(room_id)
    # Early picks should stay in a tight ADP band.
    for pick in picks:
        p = room.player_pool[pick["player_key"]]
        assert p.adp <= pick["pick_no"] + 2.8


def test_prevent_extreme_rank_outliers_early() -> None:
    room_id = _new_room(seed=17)["state"]["room_id"]
    sim = client.post(f"/api/v1/rooms/{room_id}/simulate-until-user")
    assert sim.status_code == 200, sim.text
    picks = sim.json()["state"]["picks"]
    room = drafts.get(room_id)
    # No ultra-deep outliers in first ~7 rounds.
    for pick in picks[:84]:
        p = room.player_pool[pick["player_key"]]
        assert p.rank <= 230


def test_cpu_finishes_with_qb_te_backup_depth() -> None:
    room_id = _new_room(seed=555)["state"]["room_id"]
    sim = client.post(f"/api/v1/rooms/{room_id}/simulate-to-end")
    assert sim.status_code == 200, sim.text
    state = sim.json()["state"]
    for roster in state["rosters"]:
        assert roster["counts"]["QB"] >= 2
        assert roster["counts"]["TE"] >= 2


def test_override_cpu_pick_rewinds_timeline() -> None:
    room_id = _new_room(seed=808)["state"]["room_id"]
    sim = client.post(f"/api/v1/rooms/{room_id}/simulate-until-user")
    assert sim.status_code == 200, sim.text
    before = sim.json()["state"]
    assert before["pick_no"] == 10
    target_pick = before["picks"][4]  # Pick 5 should be CPU in this setup.
    replacement = before["picks"][8]["player_key"]  # Player drafted later should be eligible after rewind.

    res = client.post(
        f"/api/v1/rooms/{room_id}/override-cpu-pick",
        json={"pick_no": target_pick["pick_no"], "player_key": replacement},
    )
    assert res.status_code == 200, res.text
    after = res.json()["state"]
    assert after["pick_no"] == target_pick["pick_no"] + 1
    assert len(after["picks"]) == target_pick["pick_no"]
    assert after["picks"][target_pick["pick_no"] - 1]["player_key"] == replacement

