# Cover readability

**Contract (v1.9.3 onwards):** on a cover that passes the quality gate, every
line of type measures at least 4.5:1 (WCAG AA) against the photograph beneath
it, and at least 3:1 against the worst patch of that photograph. A cover that
cannot reach that is refused, not shipped.

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

## What is deliberately not promised

* A cover may fail. Some photographs cannot carry type anywhere — a hard tonal
  edge running through the subtitle is the clearest case. The gate says so and
  the customer picks another layout or another photograph. That is the point:
  the previous gate could not say so.
* No panel or frame is drawn behind the type. The veil is a gradient scrim, as
  it always was; only its direction and strength changed.
