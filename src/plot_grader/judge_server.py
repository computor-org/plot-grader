"""HTTP front of tolerant_judge for the Computor harness (docs/integration.md).

POST /judge with JSON {"student_png", "reference_png": base64 PNG,
"student_data", "reference_data": plot data as render.py / the harness
extracts it}; the reply is TolerantVerdict.to_dict() as JSON.

Usage: python -m plot_grader.judge_server [--bind 127.0.0.1:8095]
At most --parallel (default 8) model calls run at once; the endpoint is shared.
"""

import argparse
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from plot_grader.judges import DEFAULT_ENDPOINTS
from plot_grader.tolerant_judge import default_judge, judge_plot

MAX_BODY = 20 * 1024 * 1024


def make_server(bind: str, judge, parallel: int = 8) -> ThreadingHTTPServer:
    slots = threading.BoundedSemaphore(parallel)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path.rstrip("/") != "/judge":
                return self.reply(404, {"error": "POST /judge"})
            try:
                n = int(self.headers.get("Content-Length", 0))
                if not 0 < n <= MAX_BODY:
                    raise ValueError("body size")
                b = json.loads(self.rfile.read(n))
                args = (base64.b64decode(b["student_png"]),
                        base64.b64decode(b["reference_png"]),
                        b["student_data"], b["reference_data"])
            except (ValueError, KeyError, TypeError) as exc:
                return self.reply(400, {"error": f"bad request: {exc}"})
            with slots:
                verdict = judge_plot(*args, judge=judge)
            self.reply(200, verdict.to_dict())

        def reply(self, code: int, obj: dict):
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            pass

    host, port = bind.rsplit(":", 1)
    return ThreadingHTTPServer((host, int(port)), Handler)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--bind", default="127.0.0.1:8095")
    p.add_argument("--parallel", type=int, default=8)
    p.add_argument("--endpoints", default=str(DEFAULT_ENDPOINTS))
    args = p.parse_args()
    server = make_server(args.bind, default_judge(Path(args.endpoints)), args.parallel)
    print(f"plot judge on http://{args.bind}/judge", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
