# Cover readability

**Contract (v1.9.3 onwards):** on a cover that passes the quality gate, each
block of type measures at least **4.5:1** (WCAG AA) against the *median* pixel
of the photograph under it, and at least **3:1** against its *worst* patch —
the brightest tenth of those pixels for light ink, the darkest tenth for dark
ink. Every block that puts words on the cover must be measured; a block that
cannot be sampled fails the cover rather than being skipped. A cover that
cannot reach this is refused, not shipped.

State that precisely, because the mechanism is not "every pixel clears AA":

* The bar is enforced per **block** (title, subtitle, series, author), on the
  block's bounding box, not per glyph.
* Across a 108-render fixture sweep, 390aaf8 passed 98 covers of which 48 had
  at least one **line** below 4.5:1, the worst at 1.01:1. This version passed
  69 of the same 108 and **none** of them had a line below 4.5:1.
* What can still slip through: where the photograph changes tone sharply
  *underneath* a line, part of that line can sit between 3:1 and 4.5:1 while
  the block's median stays high. On a deliberately adversarial half-dark,
  half-bright fixture about a quarter of the title's glyph pixels measured
  3.7:1. That is a large improvement on a gate that could not fail at all, and
  it is not the same as a promise that every glyph clears AA. Tightening the
  worst-patch bar to 4.5:1 would close it at the cost of refusing many covers
  a reader would find perfectly legible; that trade is not taken here.

## What was wrong

Two defects, found on 2026-09-23 by building the three layouts over two real
Pexels photographs.

### 1. The gate was reading the text against itself

`inspect_variant` decided `weak_contrast` by counting pixels inside the title
band of the **finished** cover: for light type it wanted at least 16 pixels
brighter than luma 190 and at least 18 darker than 90.

The white title glyphs supplied the bright pixels. Every line of type is drawn
with a near-black drop shadow at +2,+2 (`_draw_text_block`), which supplied the
dark ones. Both counters were satisfied by the type and its own shadow, whatever
the photograph was doing. The check could not fail, and it reported PASS on six
renders of which three were below AA.

### 2. The ink was chosen by one number, once, for the whole column

`_contrast_fills` switched to dark ink at region luma >= 150 and used white
below it, and the by-line inherited whatever the body column chose.

* A bright kitchen photograph measured just under 150 in
  `full_bleed_editorial`'s text box and took white type at 2.58:1. The same
  photograph measured just over 150 in `split_studio`'s box and took dark type
  at 8.14:1. One photograph, two layouts, opposite outcomes from a coin flip.
* On both real photographs the author line measured about **1.4:1**, on all
  three layouts, because it sits at the foot of the cover on a different part
  of the picture from the body it inherited its ink from.
* The veil (`_readability_overlay`) always darkened. When the ink was correctly
  dark, darkening the background pushed it towards the ink instead of away:
  measured, that took `full_bleed_editorial` from 9.06:1 down to 4.10:1.

## The fix

* `ink_contrast()` and `measure_plan_contrast()` measure WCAG contrast between
  each block's ink and the pixels it will sit on, **before** the type is
  painted, using the real sRGB luminance curve. Pure Python — the builder
  carries no numpy.
* Both the typical pixel (median) and the worst patch (the brightest tenth for
  light ink, the darkest tenth for dark ink) are measured. A title readable
  over most of a window frame and gone over the bright pane is not readable.
* `_contrast_fills` now measures both palettes against the region and picks the
  one whose **weakest role** reads better, instead of switching on a threshold.
* The author line takes its own reading of its own box when it is not part of
  the body stack.
* The veil moves away from the ink, never towards it (`DARK_VEIL` /
  `LIGHT_VEIL`), and the light veil is capped — pushed as hard as the dark one
  it bleaches the photograph and trips `blank_white_area`.
* `render_layout_with_qa` tries the veil direction the photograph asks for,
  escalating strength until AA is cleared, then tries the other direction. A
  photograph that is bright where the title sits and dark where the subtitle
  falls cannot be fixed with one ink, but a strong dark scrim makes the whole
  text area dark and light type reads across all of it.
* `inspect_variant` reports `weak_contrast` from that measurement, and reports
  it for a plan that was never measured at all — a missing check must not read
  as a pass.

## Measured, before and after

Same fixtures, same script, run against `390aaf8` and against this branch.
Typical contrast of each line:

| Fixture | Layout | Line | Before | After |
|---|---|---|---|---|
| bright beige | full_bleed_editorial | subtitle | **2.58:1** | 10.49:1 |
| bright beige | printed_moment | title | **2.97:1** | 12.28:1 |
| bright beige | printed_moment | subtitle | **3.33:1** | 10.78:1 |
| mid grey | split_studio | title | **3.90:1** | 5.87:1 |
| mid grey | split_studio | subtitle | **3.13:1** | 5.00:1 |
| mid grey | full_bleed_editorial | subtitle | **3.99:1** | 5.82:1 |
| bright top / dark bottom | any | author | **1.62:1** | 9.67:1 |

The dark-photograph fixtures are not in that table because the measuring script
used for it cannot separate the drop shadow from a dark background; the
module's own measurement, which reads the background before the type is
painted, puts them at 13–17:1 both before and after. Dark photographs were
never the problem.

## How to reproduce

```
python -m pytest tests/test_a_cover_is_readable_over_any_photograph.py -q
```

Ten tests. On `390aaf8` the file does not import, because the functions it
tests do not exist there; the before/after evidence above is the measurement to
look at instead.

For a real photograph rather than a fixture, run
`Desktop\Factory tools\Check the cover over a real photo.bat`, which fetches one
free Pexels photograph and writes the three covers to the Desktop.

## A pale photograph must still get a cover

The light veil that makes dark type readable will, on an *already* pale
photograph, push it past the very thresholds `inspect_variant` uses to reject a
cover that has stopped looking like a photograph. Measured on a flat textured
fixture: at luma 242 all three layouts passed on both versions; at luma 244 and
above all three passed on `390aaf8` and **all three were refused** here with
`blank_white_area, not_full_bleed` — leaving the customer at "choose another
photo" for a fog, a snow scene, an overcast sky or a white studio backdrop that
had been fine the release before.

`photograph_is_bleached()` is now asked before an attempt is accepted, so a veil
that washes the picture out is rejected and the other direction is tried. The
levels above now pass with the weakest line between 4.7:1 and 15.3:1.
`tests/test_a_pale_photograph_still_gets_a_cover.py` pins it, and also pins that
the fast C-level white-pixel mask agrees with the gate's own Python count.

## Cost

Rendering one cover: measured on flat fixtures, 1.53s → 1.62s end-to-end
through `attach_upload` for a dark photograph, 1.58s for mid grey, 2.83s for a
pale one. The pathological case — a hard tonal edge where one layout can never
pass, so every recovery editor burns the whole escalation ladder — costs 13.1s
against a 1.50s baseline. That path is on the builder, which has a 7200-second
task budget, and it is the case the gate is there to catch.

Two things keep it from being worse: the sRGB curve is a 256-entry table rather
than an exponent per pixel, and a text block is judged on `SAMPLE_BUDGET`
samples (5000) rather than every pixel in its box. Peak RSS across a nine-render
sweep: 132 MB before, 135 MB after; the six-attempt worst case is 160 MB, held
down by keeping only the best attempt rather than all six.

## What is deliberately not promised

* A cover may fail. Some photographs cannot carry type anywhere — a hard tonal
  edge running through the subtitle is the clearest case. The gate says so and
  the customer picks another layout or another photograph. That is the point:
  the previous gate could not say so.
* No panel or frame is drawn behind the type. The veil is a gradient scrim, as
  it always was; only its direction and strength changed.
