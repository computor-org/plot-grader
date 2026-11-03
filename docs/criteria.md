# Acceptance criteria for a plot

The vision judge exists to be more tolerant than the deterministic tests:
a plot that shows the same content as the reference passes, even if a
mechanical detail differs that makes a data or property test fail (line
order, colour name, title wording). Pixel-identical plots are checked
cheaply by image comparison; the judge decides whether the rest is "similar
enough". These criteria define "similar enough". They are used for the
visual labels of the evaluation set and in the tolerant prompt.

A plot **passes** if a reader gets the same information from it as from
the reference. It **fails** if any of these is violated:

- **M1 Same curves.** Every curve, point set or bar set of the reference is
  present. No extra data series (an extra grid line or reference line that
  the task asks for is not extra).
- **M2 Same data.** Each curve has the same shape and values as far as they
  can be read off the plot: position, slope, amplitude, period, number of
  points in a scatter. A visibly steeper, shifted or rescaled curve fails.
- **M3 Same axes.** Same axis type (linear or log) and an axis range that
  shows the same relevant region of the data.
- **M4 Axis labels.** Where the reference labels an axis, the student's axis
  is labelled with the same quantity (and unit, if the reference gives one).
- **M5 Curves identifiable.** Where the reference tells curves apart by a
  legend or labels, the student's curves are distinguishable and identified
  with the same meaning; the legend matches what is drawn.
- **M6 Same panels.** Every subplot of the reference exists with its
  content; the arrangement may differ.

These differences are **tolerated** and never fail a plot on their own:

- **T1 Style.** Colours, line styles, markers and line widths, as long as
  M5 holds.
- **T2 Mechanics.** Drawing order, sampling density (a smooth curve either
  way), figure size, resolution, fonts.
- **T3 Decoration.** Legend position, grid, tick spacing, small differences
  in axis padding.
- **T4 Wording.** Different wording, language, capitalisation or notation of
  title, axis labels and legend entries with the same meaning
  ("Zeit t [s]" and "time t (s)").
- **T5 Title.** A missing or differently worded title, if axis labels and
  legend identify the content.
- **T6 Random data.** A different draw of random data with the same
  statistics (spread, trend, convergence), unless the task fixes the seed.

When the task text explicitly requires a style (for example "plot the data
as red circles"), that requirement counts like M1–M6. The visual labels of
the evaluation set use the reference image only, so style requirements in the
task text are not checked there.

## How the judge applies the criteria

`plot_grader.tolerant_judge` passes a plot that is pixel-identical to the
reference without a model call; on the evaluation set almost every
pixel-identical plot was acceptable. Otherwise both of these must hold:

- The vision model, asked with the tolerant prompt (`pair_tolerant`, chat
  mode, images scaled to 75 %), says PASS. The prompt, not the model, sets
  the tolerance: the same model with a strict prompt failed most of the
  acceptable plots that the deterministic tests also fail. Chat mode is used
  because JEV was about as accurate but markedly slower.
- `tolerant_check` (`src/plot_grader/tolerant.py`) finds no content problem
  in the extracted plot data. It covers what the tolerant model alone lets
  through, mainly missing axis labels and rescaled data: at least as many
  panels as the reference (M6), axes the reference labels stay labelled in
  any wording (M4), every reference curve matched in any order and sampling
  within 5 % of its y range (M1/M2), and at least 80 % of the reference x
  data range visible (M3). Complex-valued data is compared
  by its real part, as matplotlib plots it. When the reference draws random
  numbers without a fixed seed (`unseeded_random`, criterion T6), the curve
  values are left to the model (`random_data=True`).

An unusable model reply gives ERROR unless the data checks already found a
problem. The prompt and the check thresholds were tuned on the synthetic
evaluation set, not on human labels of real submissions.
