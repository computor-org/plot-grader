# Computor integration

How the round-4 plot judge (`plot_grader.tolerant_judge`) plugs into the
Computor test harness. References are to computor-backend
`origin/release/2026.10` (dc2a0045); `test_class.py` lines and lines marked
*branch* are on `feat/plot-judge` (one import line added at 29).

## How graphics tests run today

- The worker runs `computor-test python run -T test.yaml -s specification.yaml`
  without a shell and with a 300 s timeout
  (`computor-backend/src/computor_backend/testing/backends.py:238-283`).
  It removes `API_TOKEN`, `TESTING_WORKER_TOKEN` and `COMPUTOR_*` from the
  environment, but leaves other variables alone (`backends.py:20-35`).
- `computor-test` runs pytest on `testers/tests/python/test_class.py`. The
  harness seeds `random` and `numpy` with 1 (`test_class.py:244-245`) and
  runs a `type: graphics` collection **in-process**
  (`_execute_graphics_inprocess`, `test_class.py:273`). Each subtest `name`
  is evaluated as `plt.<name>` and kept (`test_class.py:308-314`). All
  figures are closed afterwards (`test_class.py:351`).
- Every subtest is compared value by value (`test_entrypoint`,
  `test_class.py:422`, then `compare_variable_by_qualification`,
  `testers/tests/test_base.py:796`). The image is never compared. PNGs go to
  the artifact directory only when `storeGraphicsArtifacts` is on
  (`test_class.py:248-262, 316-327`).
- Each subtest ends up in `outputDirectory/testSummary.json` with `result`
  and `resultMessage`, where `resultMessage` is the pytest failure or skip
  text (`testers/tests/python/conftest.py:52-100`,
  `testers/tests/conftest_base.py:241-255, 327-457`). The worker stores that
  JSON as the result (`tasks/temporal_student_testing.py:520-600`), and the
  student sees the message. The worker zips `artifacts/` and uploads it
  (`temporal_student_testing.py:627-650, 758-770`).
- Sandbox: Landlock denies outbound TCP only for student **subprocesses**
  (`computor-testing/ctexec/base.py:29-49`, used by `ctexec/interpreted.py:171`).
  The harness process, including in-process graphics code, keeps the worker
  container's network (`ops/docker/docker-compose.prod.yaml:281-325`,
  `computor-network`, with egress).

## Hook: `qualification: plotJudge` (implemented on `feat/plot-judge`)

A lecturer opts in per exercise by adding one subtest to the graphics
collection:

```yaml
- type: graphics
  name: figure
  entryPoint: plot.py
  tests:
    - name: figure(1).axes[0].get_xlabel()   # existing tests stay as they are
    - name: figure(1)
      qualification: plotJudge
```

- Schema: one enum value, `QualificationEnum.plotJudge`
  (`computor-types/src/computor_types/testing.py:57-58`, *branch*), plus
  the same value in the generated `computor-web/src/generated/schemas/test-yaml-schema.json`
  and `computor-web/src/generated/types/common.ts`. There are no new keys;
  the models use `extra="forbid"` (`testing.py:163`).
- Harness: `test_entrypoint` hands a `plotJudge` subtest of a graphics
  collection to `check_plot_judge` (`test_class.py:463-468`).
  `computor-testing/testers/tests/plot_judge.py` (*branch*) renders the
  student's and the reference's figure object to PNG. It extracts axes, labels,
  limits and line data and POSTs them to `$PLOT_JUDGE_URL`.
  - A judge **FAIL** fails the subtest, and the model's findings and hint
    become `resultMessage`.
  - A **PASS** passes it.
  - No URL, a timeout (`$PLOT_JUDGE_TIMEOUT`, default 120 s), a network error
    or no verdict all SKIP the subtest. The student is never failed because
    the judge is missing.
- Service: `python -m plot_grader.judge_server --bind HOST:PORT` (this repo)
  answers `POST /judge` with `judge_plot`. It allows at most 8 model calls at
  once.
- Test: `computor-testing/tests/test_plot_judge.py` (*branch*) runs the real
  `computor-test` on a synthetic example against a stub judge. It checks
  PASS, FAIL with message, and SKIP both without a judge and with an
  unreachable one. The tests fail without the hook.
- Checked by hand on 2026-09-28 with `judge_server` and Flash-Next behind
  the real `computor-test`, using `cosine_function` plus a `figure(1)`
  plotJudge subtest. The gptSolution PASSED. The correct solution without
  axis labels FAILED with "Findings: M4 axis 0 xlabel missing; M4 axis 0
  ylabel missing" in `resultMessage`.

## What it needs at runtime

1. **A reachable judge service.** `judge_server` must run on a host that can
   reach the vision model endpoint configured in `configs/vlm_endpoints.json`
   (and read its API key, if one is set), and the testing worker must reach
   that host. Set
   `PLOT_JUDGE_URL=http://<host>:<port>/judge` on the `temporal-worker-testing`
   service. The variable name avoids the `COMPUTOR_*` filter.
2. **Time.** One judge call takes a median of 25 s at 8 parallel requests,
   and more when the queue is full. The harness has 300 s in total
   (`backends.py:283`), and the in-process graphics path has no timeout of
   its own. Use `PLOT_JUDGE_TIMEOUT=90` and one `plotJudge` subtest per
   collection.
3. **Load.** The endpoint is shared and should see at most 8 parallel calls.
   Every submission test run triggers one call. Worker concurrency and
   `--parallel` of the service bound this.
4. **Reference image.** Only the judge service receives the reference
   figure. Unrelated to the hook, when artifacts are stored, the worker
   already uploads `reference_test_*_figure_*.png` next to the student's
   images (`test_class.py:261, 316-327`). Check whether students can
   download these (`api/results.py:57-80, 184-275`).

## Limits

- **Trust.** Student code runs in the same process before the judge call. It
  can patch `urllib` or the harness and fake any graphics result. This is
  already true for all in-process graphics tests.
- **Figures.** The hook judges `figure(n)` objects one by one. Stacking all
  figures, as `render.py` does, is not done.
- **Language.** The model's differences and hint are in English. The
  bilingual text in `scripts/judge_course.py` covers the fixed parts only.

## Status

The hook is implemented on a branch (`feat/plot-judge`) and is not deployed.
Using it needs a running `judge_server`, a network route from the testing
worker to it, the two environment variables above, and `plotJudge` subtests
in the course's `test.yaml`. Without a judge URL the subtests are skipped and
nothing changes for students.
