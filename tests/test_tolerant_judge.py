"""Round-4 decision rule of plot_grader.tolerant_judge, with a stub model.

Oracle: the decision in docs/criteria.md, stated case by case on
trivial synthetic plots (never assignment content): a pixel-identical plot
passes without asking the model; a plot passes only if the model says PASS
and the student's data shows the reference content; a plot without the
reference's axis label fails M4 whatever the model says.
"""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from plot_grader.executor import extract_plot_data  # noqa: E402
from plot_grader.judges import JudgeResult  # noqa: E402
from plot_grader.tolerant_judge import judge_plot  # noqa: E402


def plot(y=(1, 4), ylabel="y", color="r", size=(4, 3)):
    """(png, plot data) of ax.plot([1, 2], y) as render.py would produce."""
    fig, ax = plt.subplots(figsize=size, dpi=50)
    ax.plot([1, 2], list(y), color=color)
    ax.set_xlabel("x")
    ax.set_ylabel(ylabel)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    data = {"n_figures": 1, "plot_data": extract_plot_data(fig)}
    plt.close(fig)
    return buf.getvalue(), data


class StubModel:
    def __init__(self, verdict, differences=(), hint=""):
        self.reply = JudgeResult(verdict=verdict, differences=list(differences),
                                 hint=hint)
        self.calls = []

    def judge(self, student_png, reference_png=None, view="pair", task=None):
        self.calls.append((Image.open(io.BytesIO(student_png)).size,
                           Image.open(io.BytesIO(reference_png)).size, view))
        return self.reply


class NoModel:
    def judge(self, *a, **k):
        raise AssertionError("the model must not be asked")


REF = plot()


def test_pixel_identical_passes_without_model():
    v = judge_plot(*REF[:1], REF[0], REF[1], REF[1], judge=NoModel())
    assert v.verdict == "PASS" and v.pixel_identical


def test_tolerated_style_change_passes_when_model_agrees():
    stu = plot(color="g")  # T1: colour differs, content the same
    model = StubModel("PASS")
    v = judge_plot(stu[0], REF[0], stu[1], REF[1], judge=model)
    assert v.verdict == "PASS" and v.criteria == [] and v.problems == []
    assert len(model.calls) == 1


def test_model_sees_both_images_at_three_quarters_with_tolerant_prompt():
    stu = plot(color="g")
    model = StubModel("PASS")
    judge_plot(stu[0], REF[0], stu[1], REF[1], judge=model)
    w, h = Image.open(io.BytesIO(REF[0])).size  # 200 x 150 at dpi 50
    assert model.calls == [((w * 3 // 4, h * 3 // 4), (w * 3 // 4, h * 3 // 4),
                            "pair_tolerant")]


def test_missing_axis_label_fails_even_if_model_passes():
    stu = plot(ylabel="")
    v = judge_plot(stu[0], REF[0], stu[1], REF[1], judge=StubModel("PASS"))
    assert v.verdict == "FAIL" and v.criteria == ["M4"]


def test_scaled_data_fails_even_if_model_passes():
    stu = plot(y=(1.25, 5))  # 25 % larger values: M2
    v = judge_plot(stu[0], REF[0], stu[1], REF[1], judge=StubModel("PASS"))
    assert v.verdict == "FAIL" and "M2" in v.criteria


def test_model_fail_is_reported_with_its_criteria_and_hint():
    stu = plot(color="g")
    model = StubModel("FAIL", ["M5: legend does not match"], "add a legend")
    v = judge_plot(stu[0], REF[0], stu[1], REF[1], judge=model)
    assert v.verdict == "FAIL" and v.criteria == ["M5"]
    assert v.differences == ["M5: legend does not match"] and v.hint == "add a legend"


@pytest.mark.parametrize("problems_in_data", [False, True])
def test_unusable_model_reply_never_passes(problems_in_data):
    stu = plot(ylabel="" if problems_in_data else "y", color="g")
    v = judge_plot(stu[0], REF[0], stu[1], REF[1], judge=StubModel(None))
    assert v.verdict == ("FAIL" if problems_in_data else "ERROR")


def test_complex_valued_curve_counts_as_its_real_part():
    # matplotlib plots the real part of complex data; the extracted data then
    # holds strings like "(1+0j)"
    ref_png, ref = plot(y=(1, 4))
    stu_png, stu = plot(y=(1, 4), color="b")
    line = stu["plot_data"]["axes"][0]["lines"][0]
    line["ydata"] = [str(complex(v)) for v in line["ydata"]]
    v = judge_plot(stu_png, ref_png, stu, ref, judge=StubModel("PASS"))
    assert v.verdict == "PASS" and v.problems == []


def test_unseeded_random_reference_leaves_curve_values_to_the_model():
    ref_png, ref = plot(y=(1, 4))
    stu_png, stu = plot(y=(2, 3), color="b")  # another random draw
    assert judge_plot(stu_png, ref_png, stu, ref, judge=StubModel("PASS")).verdict == "FAIL"
    v = judge_plot(stu_png, ref_png, stu, ref, judge=StubModel("PASS"), random_data=True)
    assert v.verdict == "PASS"
    assert judge_plot(stu_png, ref_png, stu, ref, judge=StubModel("FAIL"),
                      random_data=True).verdict == "FAIL"


@pytest.mark.parametrize("source,unseeded", [
    ("import numpy as np\nx = np.random.rand(10)", True),
    ("import numpy as np\n# np.random.seed(1)\nx = np.random.rand(10)", True),
    ("rng = np.random.default_rng()\nx = rng.random(10)", True),
    ("import numpy as np\nnp.random.seed(1)\nx = np.random.rand(10)", False),
    ("rng = np.random.default_rng(seed=42)\nx = rng.random(10)", False),
    ("import numpy as np\nx = np.linspace(0, 1)", False),
])
def test_unseeded_random_detection(source, unseeded):
    from plot_grader.tolerant import unseeded_random
    assert unseeded_random(source) is unseeded
