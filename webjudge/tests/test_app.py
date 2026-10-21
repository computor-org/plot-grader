"""Save, resume, access control and export of the judging app (stdlib server)."""

import json
import sqlite3
import sys
import threading
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as webjudge  # noqa: E402

JUDGE, ADMIN = "judge-token-123", "admin-token-456"


@pytest.fixture
def server(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "img").mkdir(parents=True)
    cases = []
    for cid in ("aaaaaaaa", "bbbbbbbb", "cccccccc"):
        for s in "rs":
            (pkg / "img" / f"{cid}{s}.png").write_bytes(b"\x89PNG" + cid.encode())
        cases.append({"id": cid, "ref": f"img/{cid}r.png", "stu": f"img/{cid}s.png"})
    (pkg / "cases.json").write_text(json.dumps({"cases": cases, "examples": []}))
    db = tmp_path / "judge.sqlite"
    tokens = {"judges": {JUDGE: "rater1"}, "admin": ADMIN}
    srv = webjudge.make_server(pkg, str(db), tokens, "127.0.0.1:0", secure=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, db, pkg, tokens
    srv.shutdown()
    srv.server_close()


def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def get(op, url, headers=None):
    try:
        r = op.open(urllib.request.Request(url, headers=headers or {}))
        return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def post(op, url, obj):
    req = urllib.request.Request(url, json.dumps(obj).encode(),
                                 {"Content-Type": "application/json"})
    try:
        r = op.open(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def login(base):
    op = client()
    code, body, _ = get(op, base + "/j/" + JUDGE)
    assert code == 200 and b"<h1>Anleitung</h1>" in body  # first visit lands on instructions
    return op


def test_everything_needs_the_token(server):
    base = server[0]
    op = client()
    for path in ("/", "/anleitung", "/api/state", "/img/aaaaaaaar.png",
                 "/static/app.js", "/j/wrong", "/admin/export"):
        code, _, headers = get(op, base + path)
        assert code == 403, path
        assert headers["X-Robots-Tag"] == "noindex, nofollow"
    assert post(op, base + "/api/answer", {"case_id": "aaaaaaaa"})[0] == 403
    code, body, _ = get(op, base + "/robots.txt")
    assert code == 200 and b"Disallow: /" in body


def test_images_only_from_package(server):
    op = login(server[0])
    assert get(op, server[0] + "/img/aaaaaaaar.png")[1] == b"\x89PNGaaaaaaaa"
    for bad in ("/img/../cases.json", "/img/dddddddds.png", "/static/../app.py"):
        assert get(op, server[0] + bad)[0] == 404, bad


def test_save_resume_and_change(server):
    base, db = server[0], server[1]
    op = login(base)
    assert post(op, base + "/api/answer",
                {"case_id": "aaaaaaaa", "verdict": "PASS", "position": 0})[0] == 200
    assert post(op, base + "/api/answer",
                {"case_id": "bbbbbbbb", "verdict": "FAIL", "criteria": ["M3"],
                 "comment": "log", "position": 1})[0] == 200
    assert post(op, base + "/api/position", {"position": 2})[0] == 200
    # A fresh browser session (cookie from the link again) resumes at case 3.
    op2 = client()
    code, body, _ = get(op2, base + "/j/" + JUDGE)
    assert code == 200 and b"<h1>Anleitung</h1>" not in body  # has answers -> main screen
    st = json.loads(get(op2, base + "/api/state")[1])
    assert st["position"] == 2 and st["judge"] == "rater1"
    assert st["answers"]["bbbbbbbb"]["criteria"] == ["M3"]
    assert st["answers"]["bbbbbbbb"]["comment"] == "log"
    # Going back and changing an earlier answer keeps one row, logs every click.
    post(op2, base + "/api/answer", {"case_id": "aaaaaaaa", "verdict": "UNSURE",
                                     "position": 0})
    st = json.loads(get(op2, base + "/api/state")[1])
    assert st["answers"]["aaaaaaaa"]["verdict"] == "UNSURE" and st["position"] == 0
    con = sqlite3.connect(db)
    assert con.execute("SELECT count(*) FROM answers").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM events").fetchone()[0] == 3
    assert con.execute("SELECT n_changes FROM answers WHERE case_id='aaaaaaaa'"
                       ).fetchone()[0] == 2


def test_rejects_bad_input(server):
    base = server[0]
    op = login(base)
    for body in ({"case_id": "zzzzzzzz", "verdict": "PASS"},
                 {"case_id": "aaaaaaaa", "verdict": "maybe"},
                 {"case_id": "aaaaaaaa", "criteria": ["M9"]},
                 {"case_id": "aaaaaaaa", "position": 99},
                 {"verdict": "PASS"}):
        assert post(op, base + "/api/answer", body)[0] == 400, body


def test_export_needs_admin_and_returns_jsonl(server):
    base = server[0]
    op = login(base)
    post(op, base + "/api/answer", {"case_id": "cccccccc", "verdict": "FAIL",
                                    "criteria": ["M1", "M2"], "comment": "ä"})
    assert get(client(), base + "/admin/export?token=" + JUDGE)[0] == 403
    code, body, _ = get(client(), base + "/admin/export",
                        {"Authorization": "Bearer " + ADMIN})
    rows = [json.loads(line) for line in body.decode().splitlines()]
    assert code == 200 and len(rows) == 1
    r = rows[0]
    assert (r["judge"], r["case_id"], r["verdict"], r["criteria"], r["comment"]) == (
        "rater1", "cccccccc", "FAIL", ["M1", "M2"], "ä")
    assert r["first_at"] and r["updated_at"]
    code, body, _ = get(client(), base + "/admin/export?what=events&token=" + ADMIN)
    assert code == 200 and len(body.decode().splitlines()) == 1


def test_backup_copy(server, tmp_path):
    base, db = server[0], server[1]
    op = login(base)
    post(op, base + "/api/answer", {"case_id": "aaaaaaaa", "verdict": "PASS"})
    out = webjudge.backup(str(db), str(tmp_path / "bak"))
    con = sqlite3.connect(out)
    assert con.execute("SELECT verdict FROM answers").fetchone()[0] == "PASS"


def test_tokens_are_created_once(tmp_path):
    t, links = tmp_path / "p" / "tokens.json", tmp_path / "p" / "links.txt"
    webjudge.make_tokens(str(t), str(links), "https://x.example", ["rater1"])
    first = json.loads(t.read_text())
    webjudge.make_tokens(str(t), str(links), "https://x.example", ["rater1", "test"])
    second = json.loads(t.read_text())
    assert second["admin"] == first["admin"]
    assert set(first["judges"].items()) <= set(second["judges"].items())
    assert sorted(second["judges"].values()) == ["rater1", "test"]
    assert "https://x.example/j/" in links.read_text()
