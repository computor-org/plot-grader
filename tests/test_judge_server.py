"""judge_server: the HTTP contract the Computor harness uses (docs/integration.md).

Oracle: the same rule as test_tolerant_judge, observed over HTTP; a request
built the way the harness builds it (base64 PNGs plus plot data) must come
back with the round-4 verdict, a malformed one with HTTP 400.
"""

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from plot_grader.judge_server import make_server
from test_tolerant_judge import StubModel, plot


@pytest.fixture
def serve():
    servers = []

    def start(model):
        server = make_server("127.0.0.1:0", model)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}/judge"
    yield start
    for s in servers:
        s.shutdown()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def as_json(data):
    return json.loads(json.dumps(data, default=lambda o: o.tolist()))


def harness_request(stu, ref):
    return {"student_png": base64.b64encode(stu[0]).decode(),
            "reference_png": base64.b64encode(ref[0]).decode(),
            "student_data": as_json(stu[1]["plot_data"]),
            "reference_data": as_json(ref[1]["plot_data"])}


def test_missing_label_fails_over_http(serve):
    url = serve(StubModel("PASS"))
    v = post(url, harness_request(plot(ylabel="", color="g"), plot()))
    assert v["verdict"] == "FAIL" and v["criteria"] == ["M4"]


def test_same_content_passes_over_http(serve):
    url = serve(StubModel("PASS"))
    assert post(url, harness_request(plot(color="g"), plot()))["verdict"] == "PASS"


def test_malformed_request_is_rejected(serve):
    url = serve(StubModel("PASS"))
    with pytest.raises(urllib.error.HTTPError) as err:
        post(url, {"student_png": "x"})
    assert err.value.code == 400
