"""Vision judges behind HTTP endpoints: chat completions and JEV /v1/systemone.

Both judges answer the same question for one student plot: PASS or FAIL.
`view="student"` repeats the round-1 setup (student image only, no reference);
`view="pair"` shows the reference image first and the student image second;
`view="pair_tolerant"` does the same with the acceptance criteria of
docs/criteria.md (content must match, style and wording may differ).
"""

import base64
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Round-1 prompt from commit 8b5dd66 (student image only).
PROMPT_STUDENT = """You are grading a student's matplotlib plot.

Examine this plot and tell me:
1. Does it appear to be a correct, well-formed matplotlib plot?
2. IF NO, what specific issues do you see (missing elements, wrong colors, wrong linestyles, incorrect data, poor labeling)?

IMPORTANT: Respond with JSON ONLY. No other text.

JSON format:
{
  "verdict": "PASS" or "FAIL",
  "has_differences": true or false,
  "differences": ["specific issue 1", "specific issue 2"],
  "overall_assessment": "brief summary",
  "hint": "How to fix using matplotlib (if FAIL)"
}"""

PROMPT_PAIR = """You are grading a student's matplotlib plot against the reference solution.

The first image is the reference solution. The second image is the student's plot.
The student passes only if the plot matches the reference in every graded aspect:
number of curves, plotted data, colors, line styles, markers, legend labels,
axis labels and title. Plotting order and code style do not matter.

IMPORTANT: Respond with JSON ONLY. No other text.

JSON format:
{
  "verdict": "PASS" or "FAIL",
  "has_differences": true or false,
  "differences": ["specific difference 1", "specific difference 2"],
  "overall_assessment": "brief summary",
  "hint": "How to fix using matplotlib (if FAIL)"
}"""

# Round 4: accept what shows the same content (docs/criteria.md).
CRITERIA = """The student passes if a reader gets the same information from the plot as
from the reference. FAIL only for a content difference:
- M1 a curve, point set or bar set of the reference is missing, or an extra
  data series is drawn;
- M2 a curve has visibly different shape or values (position, slope,
  amplitude, period, number of scatter points);
- M3 different axis type (linear/log) or an axis range that hides a relevant
  part of the data;
- M4 an axis that is labelled in the reference is unlabelled or labelled with
  a different quantity or unit;
- M5 curves that the reference identifies by a legend or labels cannot be
  told apart or identified, or the legend does not match what is drawn;
- M6 a subplot of the reference is missing.
Never FAIL for: colours, line styles, markers, line widths (if curves stay
distinguishable), drawing order, sampling density, figure size, fonts,
legend position, grid, ticks, small axis padding, or a different wording,
language, capitalisation or notation of title, labels and legend with the
same meaning, or a missing title."""

PROMPT_TOLERANT = """You are grading a student's matplotlib plot against the reference solution.

The first image is the reference solution. The second image is the student's plot.
""" + CRITERIA + """

IMPORTANT: Respond with JSON ONLY. No other text.

JSON format:
{
  "verdict": "PASS" or "FAIL",
  "has_differences": true or false,
  "differences": ["content difference 1 (criterion M1-M6)", "..."],
  "overall_assessment": "brief summary",
  "hint": "How to fix using matplotlib (if FAIL)"
}"""

PROMPT_TASK = """You are grading a student's matplotlib plot for this programming assignment.

ASSIGNMENT:
{task}

{images}
The student passes only if the plot fulfils every requirement the assignment
states for the plot (curves, data, colors, line styles, markers, legend, axis
labels, title). Requirements the assignment does not state do not matter.

IMPORTANT: Respond with JSON ONLY. No other text.

JSON format:
{{
  "verdict": "PASS" or "FAIL",
  "has_differences": true or false,
  "differences": ["unmet requirement 1", "unmet requirement 2"],
  "overall_assessment": "brief summary",
  "hint": "How to fix using matplotlib (if FAIL)"
}}"""
TASK_IMAGES = {
    "task": "The image is the student's plot.",
    "task_pair": "The first image is the reference solution's plot, the second image is "
                 "the student's plot.",
}

# JEV questions. "overall" is the verdict; the others are per-criterion diagnostics.
QUESTIONS_STUDENT = {
    "overall": "Is this a correct, well-formed matplotlib plot without missing "
               "elements, wrong colors, wrong line styles, incorrect data or poor labeling?",
    "labels": "Does every curve have a legend label, and do the axes and title have labels?",
    "styles": "Are the colors and line styles clearly distinguishable and deliberate?",
}
QUESTIONS_TOLERANT = {
    "overall": "Does the student's plot (second image) show the same content as the "
               "reference (first image)? " + CRITERIA,
}
QUESTIONS_PAIR = {
    "overall": "Does the student's plot (second image) match the reference (first image) "
               "in every graded aspect: curves, data, colors, line styles, markers, "
               "legend labels, axis labels and title?",
    "curves": "Does the student's plot have the same number of curves as the reference?",
    "data": "Do the student's curves have the same shape and values as the reference?",
    "colors": "Does each student curve have the same color as the matching reference curve?",
    "styles": "Does each student curve have the same line style and marker as the "
              "matching reference curve?",
    "labels": "Are the legend labels, axis labels and title the same as in the reference?",
}


@dataclass
class JudgeResult:
    verdict: Optional[str]  # "PASS", "FAIL" or None when the reply was unusable
    p_pass: Optional[float] = None  # JEV probability for the overall question
    criteria: Dict[str, float] = field(default_factory=dict)
    differences: List[str] = field(default_factory=list)
    hint: str = ""
    latency_s: float = 0.0
    usage: Dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    error: Optional[str] = None


def _data_url(png: bytes) -> Dict[str, Any]:
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    return {"type": "image_url", "image_url": {"url": url}}


def _images(student_png: bytes, reference_png: Optional[bytes], view: str) -> list:
    if view in ("pair", "pair_tolerant", "task_pair"):
        if reference_png is None:
            raise ValueError("view='pair' needs a reference image")
        return [_data_url(reference_png), _data_url(student_png)]
    return [_data_url(student_png)]


def _post(url: str, body: dict, api_key: Optional[str], timeout: float) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(url, json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _read_key(api_key_file: Optional[str]) -> Optional[str]:
    if not api_key_file:
        return None
    return Path(api_key_file).expanduser().read_text().strip()


def parse_verdict_json(text: str) -> Dict[str, Any]:
    """Extract the JSON object from a model reply, tolerating code fences and prose."""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object in reply")
        candidate = text[start:end + 1]
    return json.loads(candidate)


class CompletionsJudge:
    """Free-text JSON verdict through an OpenAI-compatible /v1/chat/completions."""

    mode = "chat"

    def __init__(self, base_url: str, model: str, api_key_file: Optional[str] = None,
                 temperature: float = 0.1, max_tokens: int = 600,
                 thinking: bool = False, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = _read_key(api_key_file)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.thinking = thinking
        self.timeout = timeout

    def judge(self, student_png: bytes, reference_png: Optional[bytes] = None,
              view: str = "pair", task: Optional[str] = None) -> JudgeResult:
        if view in TASK_IMAGES:
            if not task:
                raise ValueError(f"view={view!r} needs the assignment text")
            prompt = PROMPT_TASK.format(task=task, images=TASK_IMAGES[view])
        else:
            prompt = {"pair": PROMPT_PAIR, "pair_tolerant": PROMPT_TOLERANT}.get(
                view, PROMPT_STUDENT)
        content = _images(student_png, reference_png, view) + [{"type": "text", "text": prompt}]
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "chat_template_kwargs": {"enable_thinking": self.thinking},
        }
        start = time.perf_counter()
        try:
            reply = _post(self.base_url + "/v1/chat/completions", body, self.api_key,
                          self.timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return JudgeResult(verdict=None, latency_s=time.perf_counter() - start,
                               error=f"request failed: {exc}")
        latency = time.perf_counter() - start
        text = reply["choices"][0]["message"].get("content") or ""
        result = JudgeResult(verdict=None, latency_s=latency,
                             usage=reply.get("usage", {}), raw=text)
        try:
            data = parse_verdict_json(text)
        except ValueError as exc:
            result.error = f"unparseable reply: {exc}"
            return result
        verdict = str(data.get("verdict", "")).upper()
        result.verdict = verdict if verdict in ("PASS", "FAIL") else None
        if result.verdict is None:
            result.error = f"verdict field is {data.get('verdict')!r}"
        result.differences = [str(d) for d in data.get("differences") or []]
        result.hint = str(data.get("hint") or "")
        return result


class JevJudge:
    """Typed yes/no questions through JEV POST /v1/systemone; verdict from P(yes)."""

    mode = "jev"

    def __init__(self, base_url: str, model: str, api_key_file: Optional[str] = None,
                 threshold: float = 0.5, timeout: float = 300.0,
                 overall_only: bool = False):
        self.overall_only = overall_only
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = _read_key(api_key_file)
        self.threshold = threshold
        self.timeout = timeout

    def judge(self, student_png: bytes, reference_png: Optional[bytes] = None,
              view: str = "pair", task: Optional[str] = None) -> JudgeResult:
        questions = {"pair": QUESTIONS_PAIR, "pair_tolerant": QUESTIONS_TOLERANT,
                     "student": QUESTIONS_STUDENT}.get(view)
        if questions is None:
            raise ValueError(f"JEV judge has no view {view!r}")
        if self.overall_only:
            questions = {"overall": questions["overall"]}
        intro = ("The first image is the reference solution, the second is the "
                 "student's matplotlib plot." if view != "student"
                 else "This is a student's matplotlib plot.")
        state = [{"role": "user",
                  "content": _images(student_png, reference_png, view)
                  + [{"type": "text", "text": intro}]}]
        body = {
            "model": self.model,
            "state": state,
            "questions": {k: {"type": "noul", "instructions": q}
                          for k, q in questions.items()},
        }
        start = time.perf_counter()
        try:
            reply = _post(self.base_url + "/v1/systemone", body, self.api_key, self.timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return JudgeResult(verdict=None, latency_s=time.perf_counter() - start,
                               error=f"request failed: {exc}")
        latency = time.perf_counter() - start
        answers = reply.get("answers", {})
        criteria = {k: float(v["noul"]) for k, v in answers.items() if "noul" in v}
        p_pass = criteria.get("overall")
        result = JudgeResult(verdict=None, p_pass=p_pass, criteria=criteria,
                             latency_s=latency, usage=reply.get("usage", {}),
                             raw=json.dumps(answers))
        if p_pass is None:
            result.error = "no probability for the overall question"
            return result
        result.verdict = "PASS" if p_pass >= self.threshold else "FAIL"
        result.differences = [k for k, p in criteria.items()
                              if k != "overall" and p < self.threshold]
        return result


def load_endpoints(path: Path) -> Dict[str, Dict[str, Any]]:
    """Read the endpoint config: {name: {"chat": {...}, "jev": {...}}}."""
    return json.loads(Path(path).read_text())["models"]


def make_judge(endpoints: Dict[str, Dict[str, Any]], name: str, mode: str):
    """Build a judge for model `name` in `mode` ("chat" or "jev") from the config."""
    cfg = dict(endpoints[name][mode])
    cls = CompletionsJudge if mode == "chat" else JevJudge
    return cls(**cfg)


class JudgeTier4:
    """Adapter that lets PlotGrader use a judge as Tier 4 (independent verdict)."""

    def __init__(self, judge, view: str = "pair"):
        self.judge_impl = judge
        self.view = view

    def grade(self, student_data, reference_data, tier_results=None,
              assignment_requirements=None):
        from .executor import render_figure_to_bytes
        from .models import GradingResult, ResultStatus, Tier

        student_fig = student_data.get("execution", {}).get("figure")
        reference_fig = reference_data.get("execution", {}).get("figure")
        if student_fig is None or reference_fig is None:
            return GradingResult(status=ResultStatus.ERROR, tier=Tier.TIER_4,
                                 confidence=0.0, score=0.0,
                                 error_message="Missing figure data for Tier 4")
        res = self.judge_impl.judge(render_figure_to_bytes(student_fig),
                                    render_figure_to_bytes(reference_fig), view=self.view)
        if res.verdict is None:
            return GradingResult(status=ResultStatus.ERROR, tier=Tier.TIER_4,
                                 confidence=0.0, score=0.0, error_message=res.error,
                                 execution_time_ms=res.latency_s * 1000)
        passed = res.verdict == "PASS"
        confidence = res.p_pass if passed else (1 - res.p_pass) if res.p_pass is not None else 0.8
        label = f"{self.judge_impl.model} ({self.judge_impl.mode})"
        return GradingResult(
            status=ResultStatus.PASS if passed else ResultStatus.FAIL,
            tier=Tier.TIER_4, confidence=confidence, score=100.0 if passed else 0.0,
            passed_checks=[f"VLM {label}: plot matches"] if passed else [],
            failed_checks=[f"VLM {label}: {d}" for d in res.differences] or
                          ([] if passed else [f"VLM {label}: FAIL"]),
            warnings=[f"VLM hint: {res.hint}"] if res.hint else [],
            execution_time_ms=res.latency_s * 1000,
        )


DEFAULT_ENDPOINTS = Path(__file__).resolve().parents[2] / "configs" / "vlm_endpoints.json"


def add_judge_args(parser) -> None:
    """CLI flags shared by the scripts that can use an HTTP judge as Tier 4."""
    parser.add_argument("--judge", help="Tier 4 model name from the endpoint config "
                        "(e.g. 27b, 4b, flash-next)")
    parser.add_argument("--mode", choices=["chat", "jev"], default="jev",
                        help="chat completions or JEV /v1/systemone (default: jev)")
    parser.add_argument("--view", choices=["pair", "pair_tolerant", "student"], default="pair",
                        help="reference+student images, or student only as in round 1")
    parser.add_argument("--endpoints", default=str(DEFAULT_ENDPOINTS),
                        help="endpoint config JSON")


def tier4_from_args(args) -> Optional[JudgeTier4]:
    if not args.judge:
        return None
    judge = make_judge(load_endpoints(Path(args.endpoints)), args.judge, args.mode)
    return JudgeTier4(judge, view=args.view)
