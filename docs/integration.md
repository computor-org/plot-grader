# Computor integration

How the plot judge (`plot_grader.tolerant_judge`) relates to the Computor
test harness. Paths refer to the `computor-backend` repository on `main`.

## How graphics tests run today

- The worker runs `computor-test python run -T test.yaml -s specification.yaml`
  without a shell and with a 300 s default timeout
  (`computor-backend/src/computor_backend/testing/backends.py`).
  It removes `API_TOKEN`, `TESTING_WORKER_TOKEN` and `COMPUTOR_*` from the
  environment, except the sandbox switches and the `COMPUTOR_JOB_*` resource
  limits, and leaves other variables alone.
- `computor-test` runs pytest on `testers/tests/python/test_class.py`. The
  harness seeds `random` and `numpy` with 1 and runs a `type: graphics`
  collection like every other test in the bounded, sandboxed job
  (`testers/executors/python.py`). Each subtest `name` is evaluated inside
  the job as `plt.<name>` and returned to the harness as data; the figure
  objects never reach the harness process.
- Every subtest is compared value by value (`test_entrypoint` in
  `test_class.py`, then `compare_variable_by_qualification` in
  `testers/tests/test_base.py`). The image is never compared. When
  `storeGraphicsArtifacts` is on, the job saves the open figures as PNG and
  the harness copies them, size-capped and without symlinks, to the artifact
  directory.
- Each subtest ends up in `outputDirectory/testSummary.json` with `result`
  and `resultMessage`, where `resultMessage` is the pytest failure or skip
  text. The worker stores that JSON as the result
  (`computor-backend/src/computor_backend/tasks/temporal_student_testing.py`),
  and the student sees the message. The worker zips `artifacts/` and uploads
  it through the API.
- Sandbox: student code runs under a Landlock filesystem allow-list and, where
  the host permits it, in a loopback-only network namespace
  (`computor-testing/ctexec/base.py`). The harness process itself keeps the
  worker container's network.

## Hook: `qualification: plotJudge` (not on `main`)

`computor-testing` on `main` has no plot-judge hook. The proposed opt-in is
one extra subtest in the graphics collection:

```yaml
- type: graphics
  name: figure
  entryPoint: plot.py
  tests:
    - name: figure(1).axes[0].get_xlabel()   # existing tests stay as they are
    - name: figure(1)
      qualification: plotJudge
```

- Schema: one enum value, `QualificationEnum.plotJudge`, in
  `computor-types/src/computor_types/testing.py`, plus the same value in the
  generated `computor-web` test-yaml schema and types. The models use
  `extra="forbid"`, so no new keys are needed.
- Harness: a `plotJudge` subtest of a graphics collection sends the
  student's and the reference's figure as PNG, together with the extracted
  axes, labels, limits and line data, to `$PLOT_JUDGE_URL`. Because graphics
  run in the sandboxed job, the PNGs and plot data have to come from the job
  output, not from figure objects in the harness process.
  - A judge **FAIL** fails the subtest, and the model's findings and hint
    become `resultMessage`.
  - A **PASS** passes it.
  - No URL, a timeout (`$PLOT_JUDGE_TIMEOUT`, default 120 s), a network error
    or no verdict all SKIP the subtest. The student is never failed because
    the judge is missing.
- Service: `python -m plot_grader.judge_server --bind HOST:PORT` (this repo)
  answers `POST /judge` with `judge_plot`. It allows at most `--parallel`
  (default 8) model calls at once.

## What it needs at runtime

1. **A reachable judge service.** `judge_server` must run on a host that can
   reach the vision model endpoint configured in `configs/vlm_endpoints.json`
   (and read its API key, if one is set), and the testing worker must reach
   that host. Set
   `PLOT_JUDGE_URL=http://<host>:<port>/judge` on the `temporal-worker-testing`
   service. The variable name avoids the `COMPUTOR_*` filter.
2. **Time.** One judge call takes a median of 25 s at 8 parallel requests,
   and more when the queue is full. The harness has 300 s in total
   (`backends.py`). Use `PLOT_JUDGE_TIMEOUT=90` and one `plotJudge` subtest
   per collection.
3. **Load.** The endpoint is shared and should see at most 8 parallel calls.
   Every submission test run triggers one call. Worker concurrency and
   `--parallel` of the service bound this.
4. **Reference image.** Only the judge service receives the reference
   figure. Unrelated to the hook, when artifacts are stored, the worker
   already uploads the reference's figure PNGs next to the student's images.
   Check whether students can download these
   (`computor-backend/src/computor_backend/api/results.py`).

## Limits

- **Trust.** The plot data and figures come from the job that runs the
  student code, so student code can fake them. This is true for all graphics
  tests.
- **Figures.** The hook judges `figure(n)` objects one by one. Stacking all
  figures, as `render.py` does, is not done.
- **Language.** The model's differences and hint are in English. The
  bilingual text in `scripts/judge_course.py` covers the fixed parts only.
