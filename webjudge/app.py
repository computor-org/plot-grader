#!/usr/bin/env python3
"""plotcheck: blind human judging of student plots against a reference.

Python standard library only. Environment:
  PLOTCHECK_PACKAGE  dir with cases.json and img/ (scripts/build_judge_package.py)
  PLOTCHECK_DB       SQLite file (created on first start)
  PLOTCHECK_TOKENS   JSON {"judges": {"<token>": "<name>"}, "admin": "<token>"}
  PLOTCHECK_BIND     default 127.0.0.1:18790
  PLOTCHECK_INSECURE_COOKIE=1  drop the Secure flag (local tests over http)

Subcommands:
  app.py serve
  app.py tokens TOKENS.json LINKS.txt BASE_URL NAME [NAME ...]
  app.py backup DB DEST_DIR [KEEP_DAYS]
"""

import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
COOKIE = "pc_token"
VERDICTS = {"PASS", "FAIL", "UNSURE"}
CRITERIA = {"M1", "M2", "M3", "M4", "M5", "M6"}
IMG_RE = re.compile(r"^[0-9a-f]{8}[rs]\.png$")
STATIC_TYPES = {".js": "text/javascript", ".css": "text/css", ".html": "text/html"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
  judge TEXT NOT NULL, case_id TEXT NOT NULL, verdict TEXT, criteria TEXT,
  comment TEXT, first_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  n_changes INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (judge, case_id));
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, judge TEXT NOT NULL,
  case_id TEXT NOT NULL, position INTEGER, verdict TEXT, criteria TEXT,
  comment TEXT);
CREATE TABLE IF NOT EXISTS progress (
  judge TEXT PRIMARY KEY, position INTEGER NOT NULL, updated_at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Store:
    """All judge state; one connection guarded by a lock (tiny load)."""

    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def save(self, judge: str, case_id: str, verdict, criteria: list, comment: str,
             position=None):
        ts = now()
        crit = json.dumps(sorted(criteria))
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO events (ts, judge, case_id, position, verdict, criteria,"
                " comment) VALUES (?,?,?,?,?,?,?)",
                (ts, judge, case_id, position, verdict, crit, comment))
            self.db.execute(
                "INSERT INTO answers (judge, case_id, verdict, criteria, comment,"
                " first_at, updated_at) VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT (judge, case_id) DO UPDATE SET verdict=excluded.verdict,"
                " criteria=excluded.criteria, comment=excluded.comment,"
                " updated_at=excluded.updated_at, n_changes=n_changes+1",
                (judge, case_id, verdict, crit, comment, ts, ts))
            if position is not None:
                self._position(judge, position, ts)
        return ts

    def _position(self, judge: str, position: int, ts: str):
        self.db.execute(
            "INSERT INTO progress VALUES (?,?,?) ON CONFLICT (judge) DO UPDATE"
            " SET position=excluded.position, updated_at=excluded.updated_at",
            (judge, position, ts))

    def set_position(self, judge: str, position: int):
        with self.lock, self.db:
            self._position(judge, position, now())

    def state(self, judge: str) -> dict:
        with self.lock:
            rows = self.db.execute(
                "SELECT case_id, verdict, criteria, comment, updated_at FROM answers"
                " WHERE judge=?", (judge,)).fetchall()
            pos = self.db.execute("SELECT position FROM progress WHERE judge=?",
                                  (judge,)).fetchone()
        answers = {c: {"verdict": v, "criteria": json.loads(k or "[]"),
                       "comment": m or "", "updated_at": u}
                   for c, v, k, m, u in rows}
        return {"answers": answers, "position": pos[0] if pos else None}

    def export(self, what: str) -> list:
        table = "events" if what == "events" else "answers"
        with self.lock:
            cur = self.db.execute(f"SELECT * FROM {table} ORDER BY 1, 2")
            names = [d[0] for d in cur.description]
            rows = [dict(zip(names, r)) for r in cur.fetchall()]
        for r in rows:
            r["criteria"] = json.loads(r["criteria"] or "[]")
        return rows


def load_package(path: Path) -> dict:
    pkg = json.loads((path / "cases.json").read_text())
    pkg["ids"] = {c["id"] for c in pkg["cases"]}
    pkg["files"] = {Path(c[s]).name for k in ("cases", "examples")
                    for c in pkg[k] for s in ("ref", "stu")}
    return pkg


DENIED = ("<!doctype html><meta charset=utf-8><title>plotcheck</title>"
          "<p>Kein Zugang. Bitte den persönlichen Link aus der E-Mail verwenden.</p>")


class App:
    def __init__(self, package: Path, db: str, tokens: dict, secure: bool = True):
        self.package_dir = package
        self.pkg = load_package(package)
        self.store = Store(db)
        self.judges = dict(tokens.get("judges", {}))
        self.admin = tokens.get("admin") or None
        self.secure = secure

    def judge_of(self, token):
        if not token:
            return None
        for t, name in self.judges.items():
            if secrets.compare_digest(t, token):
                return name
        return None

    def is_admin(self, token) -> bool:
        return bool(self.admin and token and secrets.compare_digest(self.admin, token))


class Handler(BaseHTTPRequestHandler):
    app: App = None  # set by make_server
    server_version = "plotcheck"
    sys_version = ""

    def log_message(self, fmt, *args):  # no URLs (tokens) in the journal
        pass

    # -- responses -------------------------------------------------------
    def send(self, code: int, body: bytes, ctype: str, headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, obj, code=200):
        self.send(code, json.dumps(obj).encode(), "application/json")

    def deny(self):
        self.send(403, DENIED.encode(), "text/html; charset=utf-8")

    def redirect(self, where: str, headers=()):
        self.send(303, b"", "text/plain", [("Location", where), *headers])

    def token(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        return c[COOKIE].value if COOKIE in c else None

    def admin_token(self, q):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        return (q.get("token") or [None])[0]

    # -- routing ---------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlsplit(self.path)
        path, q = url.path, parse_qs(url.query)
        app = self.app
        if path == "/robots.txt":
            return self.send(200, b"User-agent: *\nDisallow: /\n", "text/plain")
        if path == "/healthz":
            return self.send(200, b"ok\n", "text/plain")
        if path.startswith("/j/"):
            tok = path[3:]
            judge = app.judge_of(tok)
            if not judge:
                return self.deny()
            flags = "; Secure" if app.secure else ""
            cookie = (f"{COOKIE}={tok}; Path=/; HttpOnly; SameSite=Lax"
                      f"; Max-Age=7776000{flags}")
            start = "/" if app.store.state(judge)["answers"] else "/anleitung"
            return self.redirect(start, [("Set-Cookie", cookie)])
        if path == "/admin/export":
            if not app.is_admin(self.admin_token(q)):
                return self.deny()
            what = (q.get("what") or ["answers"])[0]
            body = "".join(json.dumps(r, ensure_ascii=False) + "\n"
                           for r in app.store.export(what))
            return self.send(200, body.encode(), "application/x-ndjson")
        judge = app.judge_of(self.token())
        if not judge:
            return self.deny()
        if path in ("/", "/index.html"):
            return self.static("index.html")
        if path == "/anleitung":
            return self.static("anleitung.html")
        if path.startswith("/static/"):
            return self.static(path[8:])
        if path.startswith("/img/"):
            name = path[5:]
            if not IMG_RE.match(name) or name not in app.pkg["files"]:
                return self.send(404, b"not found", "text/plain")
            data = (app.package_dir / "img" / name).read_bytes()
            return self.send(200, data, "image/png")
        if path == "/api/state":
            st = app.store.state(judge)
            return self.send_json({"judge": judge, "cases": app.pkg["cases"],
                                   "examples": app.pkg["examples"], **st})
        self.send(404, b"not found", "text/plain")

    def static(self, name: str):
        f = (STATIC / name).resolve()
        if f.parent != STATIC.resolve() or not f.is_file():
            return self.send(404, b"not found", "text/plain")
        ctype = STATIC_TYPES.get(f.suffix, "application/octet-stream")
        self.send(200, f.read_bytes(), ctype + "; charset=utf-8")

    def do_POST(self):
        path = urlsplit(self.path).path
        judge = self.app.judge_of(self.token())
        if not judge:
            return self.deny()
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 20000:
                raise ValueError("too large")
            body = json.loads(self.rfile.read(n) or b"{}")
            if path == "/api/answer":
                return self.post_answer(judge, body)
            if path == "/api/position":
                self.app.store.set_position(judge, self.check_pos(body["position"]))
                return self.send_json({"ok": True})
        except (ValueError, KeyError, TypeError) as e:
            return self.send_json({"error": str(e)}, 400)
        self.send(404, b"not found", "text/plain")

    def check_pos(self, pos) -> int:
        if not isinstance(pos, int) or not 0 <= pos <= len(self.app.pkg["cases"]):
            raise ValueError("bad position")
        return pos

    def post_answer(self, judge: str, b: dict):
        cid = b["case_id"]
        if cid not in self.app.pkg["ids"]:
            raise ValueError("unknown case")
        verdict = b.get("verdict")
        if verdict is not None and verdict not in VERDICTS:
            raise ValueError("bad verdict")
        crit = list(b.get("criteria") or [])
        if not set(crit) <= CRITERIA:
            raise ValueError("bad criteria")
        comment = str(b.get("comment") or "")[:4000]
        pos = b.get("position")
        pos = None if pos is None else self.check_pos(pos)
        ts = self.app.store.save(judge, cid, verdict, crit, comment, pos)
        self.send_json({"ok": True, "saved_at": ts})


def make_server(package: Path, db: str, tokens: dict, bind: str = "127.0.0.1:18790",
                secure: bool = True) -> ThreadingHTTPServer:
    host, port = bind.rsplit(":", 1)
    handler = type("BoundHandler", (Handler,), {"app": App(package, db, tokens, secure)})
    return ThreadingHTTPServer((host, int(port)), handler)


def make_tokens(tokens_path: str, links_path: str, base_url: str, names: list):
    """Create tokens once; never overwrite existing ones."""
    p = Path(tokens_path)
    tok = json.loads(p.read_text()) if p.exists() else {"judges": {}, "admin": None}
    have = set(tok["judges"].values())
    for name in names:
        if name not in have:
            tok["judges"][secrets.token_urlsafe(24)] = name
    tok["admin"] = tok["admin"] or secrets.token_urlsafe(32)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(tok, indent=1))
    p.chmod(0o600)
    base = base_url.rstrip("/")
    lines = [f"{name}: {base}/j/{t}" for t, name in tok["judges"].items()]
    lines += [f"admin token: {tok['admin']}",
              f"export: curl -H 'Authorization: Bearer <admin token>' "
              f"{base}/admin/export"]
    Path(links_path).write_text("\n".join(lines) + "\n")
    Path(links_path).chmod(0o600)


def backup(db: str, dest: str, keep_days: int = 30):
    """Consistent copy via the SQLite backup API, one file per day."""
    d = Path(dest)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"judge-{datetime.now(timezone.utc):%Y%m%d}.sqlite"
    src, dst = sqlite3.connect(db), sqlite3.connect(out)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    cutoff = time.time() - keep_days * 86400
    for f in d.glob("judge-*.sqlite"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "tokens":
        return make_tokens(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])
    if cmd == "backup":
        keep = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        return print(backup(sys.argv[2], sys.argv[3], keep))
    env = os.environ
    tokens = json.loads(Path(env["PLOTCHECK_TOKENS"]).read_text())
    srv = make_server(Path(env["PLOTCHECK_PACKAGE"]), env["PLOTCHECK_DB"], tokens,
                      env.get("PLOTCHECK_BIND", "127.0.0.1:18790"),
                      env.get("PLOTCHECK_INSECURE_COOKIE") != "1")
    print(f"plotcheck on {srv.server_address}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
