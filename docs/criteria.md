# Acceptance criteria for a plot

The vision judge exists to be more tolerant than the deterministic tests:
a plot that shows the same content as the reference passes, even if a
mechanical detail differs that makes a data or property test fail (line
order, colour name, title wording). Pixel-identical plots are checked
cheaply by image comparison; the judge decides whether the rest is "similar
enough". These criteria define "similar enough". They are used for the
visual labels of the evaluation set (round 4) and in the tolerant prompt.

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
as red circles"), that requirement counts like M1–M6. The round-4 labels use
the reference image only, so style requirements in the task text are not
checked there.
