"""dex_photo_secret_scan: each rule fires on what it names, strength follows the rules, and no matched text is ever written.

Every "secret" here is made up for the test.  Silas Reeve / DDL-3004 / 2026-10-10
"""
import json

import dex_photo_secret_scan as ss

FAKE_KEY = "sk-" + "TESTONLYnotarealkey0000"
MIXED = "Ab3dEf6hIj9kLm2nOp5q"                       # 20 characters, upper + lower + digits


def test_r1_labels_fire_alone_as_medium():
    assert ss.scan("Enter your password to continue", []) == (["R1"], "medium")
    assert ss.scan("Your recovery code is on the next screen", []) == (["R1"], "medium")
    assert ss.scan("turn on 2FA", [])[0] == ["R1"] and ss.scan("enter PIN", [])[0] == ["R1"]
    assert ss.scan("pinned chats and passwords", []) == ([], None)          # not the bare words
    assert ss.scan("a pinch of salt", []) == ([], None)


def test_r1_with_a_random_string_nearby_is_strong_and_far_away_is_not():
    assert ss.scan(f"Password: {MIXED}", []) == (["R1", "R3"], "strong")
    far = "password" + " filler" * 40 + " " + MIXED
    assert ss.scan(far, []) == (["R1", "R3"], "medium")


def test_r2_key_shapes_are_strong():
    for t in (FAKE_KEY, "ghp_" + "a1" * 10, "AKIA" + "ABCD1234EFGH", "-----BEGIN OPENSSH PRIVATE KEY-----",
              "Authorization: Bearer abc.def", "eyJ" + "a" * 40, "xoxb-12345-abc", "github_pat_11AAAA"):
        rules, strength = ss.scan(t, [])
        assert "R2" in rules and strength == "strong", t
    assert ss.scan("ask the bearer of bad news; risk-averse; pk", []) == ([], None)


def test_r2_prefix_inside_a_word_is_not_a_key():
    for t in ("src/modules/risk-register/TourStickyNav.tsx", "task-scheduler-service", "disk-management", "desk-booking-app_v2"):
        assert ss.scan(t, []) == ([], None), t
    for t in ("key=" + FAKE_KEY, "(" + FAKE_KEY + ")", "token: " + FAKE_KEY):          # after punctuation it still counts
        assert "R2" in ss.scan(t, [])[0], t


def test_spots_give_offsets_for_each_reading_rule_and_nothing_else():
    text = "Password: " + MIXED + "\nopen Bitwarden " + FAKE_KEY
    got = ss.spots(text)
    assert [(r, text[a:b]) for r, a, b in got if r != "R3"] == [("R1", "Password"), ("R6", "Bitwarden"), ("R2", FAKE_KEY)]
    assert ("R3", 10, 10 + len(MIXED)) in got
    assert all(isinstance(v, (str, int)) and (not isinstance(v, str) or v in ("R1", "R2", "R3", "R6")) for row in got for v in row)
    assert ss.spots("") == [] and ss.spots(None) == []


def test_r3_needs_all_three_kinds_sixteen_long_and_skips_ddl_ids():
    assert ss.scan(MIXED, []) == (["R3"], "medium")
    assert ss.scan(MIXED[:15], []) == ([], None)                             # fifteen is not sixteen
    assert ss.scan("abcdefghijklmnop1234", []) == ([], None)                 # no upper case
    assert ss.scan("0123456789abcdef0123456789abcdef01234567", []) == ([], None)   # a git hash: no upper case
    assert ss.scan("P-" + MIXED, []) == ([], None)
    assert ss.scan("ASSET-" + MIXED, []) == ([], None)
    assert ss.scan("C:\\Users\\Dexjr1\\Folder2\\Longname3", []) == ([], None)   # a path is broken up by its slashes


def test_r4_a_numbered_list_of_twelve_words():
    words = "apple brick candle dune ember fjord glint harbor ivory jolt kite lumen".split()
    assert ss.scan("\n".join(f"{i}. {w}" for i, w in enumerate(words, 1)), []) == (["R4"], "strong")
    assert ss.scan("\n".join(f"{i}. {w}" for i, w in enumerate(words[:11], 1)), []) == ([], None)
    assert ss.scan("\n".join(f"{i}. {w} and more words here" for i, w in enumerate(words, 1)), []) == ([], None)


def test_r5_and_r7_location_stands_on_its_own():
    assert ss.scan("some harmless words", ["process/ddlapp-password-files"]) == (["R5"], "strong")
    assert ss.scan("", ["icloud/Documents/Keeper export/shot.png"]) == (["R5", "R7"], "strong")
    assert ss.scan("   \n", ["x/login-screens/a.png"]) == (["R5", "R7"], "strong")
    assert ss.scan("", ["photos/2015", "google-takeout/Photos/img.jpg"]) == ([], None)


def test_r6_password_manager_screens():
    assert ss.scan("Keeper  My Vault  Record", []) == (["R6"], "medium")
    assert ss.scan("Sign-in & security", [])[0] == ["R6"]
    assert ss.scan("tap Copy Password", [])[0] == ["R1", "R6"]
    assert ss.scan("the gatekeepers and bookkeeper", []) == ([], None)


def make(tmp_path):
    lib, ocr = tmp_path / "lib", tmp_path / "ocr"
    (ocr / "text" / "aa").mkdir(parents=True)
    lib.mkdir()
    photos = [("aa1", ["process/systems"], ["x/a.png"], f"api key {FAKE_KEY}"), ("aa2", ["pc-snips"], ["x/b.png"], f"token {MIXED}"),
              ("aa3", ["photos/2015"], ["x/c.jpg"], ""), ("aa4", ["process/ddlapp-password-files"], ["x/d.png"], ""),
              ("aa5", ["chats"], ["x/e.png"], "enter your password")]
    (lib / "index.jsonl").write_text("".join(json.dumps({"sha256": s, "was_at": w}) + "\n" for s, _, w, _ in photos), encoding="utf-8")
    (lib / "labels.jsonl").write_text("".join(json.dumps({"sha256": s, "photo_id": "P-" + s, "albums": a}) + "\n" for s, a, _, _ in photos), encoding="utf-8")
    for s, _, _, t in photos:
        if t:
            (ocr / "text" / "aa" / f"{s}.txt").write_text(t + "\n", encoding="utf-8")
    return lib, ocr


def everything_written(lib):
    return "".join(p.read_text(encoding="utf-8") for p in lib.iterdir() if p.is_file())


def test_a_dry_run_counts_and_writes_nothing(tmp_path):
    lib, ocr = make(tmp_path)
    before = sorted(p.name for p in lib.iterdir())
    s = ss.run(lib, ocr, now="2026-10-10T23:00:00Z", log=lambda *a: None)
    assert s["by_strength"] == {"strong": 2, "medium": 2} and s["by_rule"] == {"R1": 1, "R2": 1, "R3": 2, "R5": 1, "R7": 1}   # the made-up key is itself a mixed run
    assert s["newly_hidden"] == 0 and sorted(p.name for p in lib.iterdir()) == before


def test_apply_hides_the_flagged_and_never_writes_what_matched(tmp_path):
    lib, ocr = make(tmp_path)
    s = ss.run(lib, ocr, apply=True, now="2026-10-10T23:00:00Z", log=lambda *a: None)
    assert s["newly_hidden"] == 4 and s["in_review_list"] == 4
    review = [json.loads(x) for x in (lib / "review.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["photo_id"], r["rules"], r["strength"]) for r in review] == [
        ("P-aa1", ["R2", "R3"], "strong"), ("P-aa4", ["R5", "R7"], "strong"), ("P-aa2", ["R3"], "medium"), ("P-aa5", ["R1"], "medium")]
    state = [json.loads(x) for x in (lib / "app-state.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(r["photo_id"] for r in state) == ["P-aa1", "P-aa2", "P-aa4", "P-aa5"] and all(r["hidden"] is True for r in state)
    written = everything_written(lib)
    for secret in (FAKE_KEY, MIXED, "TESTONLY", "enter your password"):
        assert secret not in written


def test_a_second_run_hides_nothing_new_and_a_decided_photo_is_left_alone(tmp_path):
    lib, ocr = make(tmp_path)
    ss.run(lib, ocr, apply=True, now="2026-10-10T23:00:00Z", log=lambda *a: None)
    with open(lib / "app-state.jsonl", "a", encoding="utf-8") as f:           # the Operator, in the app: not a secret
        f.write(json.dumps({"sha256": "aa2", "photo_id": "P-aa2", "at": "x", "review": "not-secret"}) + "\n")
        f.write(json.dumps({"sha256": "aa2", "photo_id": "P-aa2", "at": "x", "hidden": False}) + "\n")
    s = ss.run(lib, ocr, apply=True, now="2026-10-11T00:00:00Z", log=lambda *a: None)
    assert s["newly_hidden"] == 0 and s["in_review_list"] == 4
    rows = {r["photo_id"]: r for r in map(json.loads, (lib / "review.jsonl").read_text(encoding="utf-8").splitlines())}
    assert rows["P-aa1"]["flagged_at"] == "2026-10-10T23:00:00Z"              # the first flag time is kept


def test_strength_filter_lists_and_hides_only_that_strength(tmp_path):
    lib, ocr = make(tmp_path)
    s = ss.run(lib, ocr, apply=True, strength="strong", now="2026-10-10T23:00:00Z", log=lambda *a: None)
    assert s["newly_hidden"] == 2 and s["flagged_all_strengths"] == 4
    assert sorted(json.loads(x)["photo_id"] for x in (lib / "app-state.jsonl").read_text(encoding="utf-8").splitlines()) == ["P-aa1", "P-aa4"]
