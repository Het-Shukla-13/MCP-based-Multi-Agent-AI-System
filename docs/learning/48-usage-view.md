# 48 — Usage view: the Phase F metrics, for the user

Branches: `feature/metrics-daily` (backend, merged first) and `feature/fe-usage-view`.

## Backend: a zero-filled daily series

`GET /metrics/summary` gains `daily: [{date, turns, errors, tokens}]`, one entry per day in the range, **including days with no activity**. A chart that silently skips empty days misrepresents time. `daily_series()` is a pure function with a unit test (empty days kept, oldest first, out-of-window data ignored).

Both metrics endpoints were already scoped to the signed-in user (`WHERE user_id = :me`). An e2e test against the real backend confirms that a new user sees **zero** activity.

## Method: form first, colour last (dataviz procedure)

| Data | Job | Form |
|---|---|---|
| replies, p50/p95 reply time, time to first words, tokens, error and fallback rates | headline numbers | **KPI row of stat tiles** (not charts) |
| replies per day | one series over time | **column chart**, one hue, no legend (the title names it) |
| tokens by model / by purpose, replies by agent | compare parts | **ranked horizontal bars**, largest first, one hue, values printed |
| tools, recent replies | look-ups | **tables** |

**Colour, computed rather than eyeballed:** the dataviz validator rejected the UI accent as a *data* colour.

- Light `#0c7a6e`: chroma 0.09, below the 0.1 floor, so it reads greyish as a fill.
- Dark `#3cc2ae`: lightness 0.738, above the 0.48–0.67 band, so large fills glare.

So data marks got their **own token**, `--chart-mark` (`#0b8a7a` light, `#2aa694` dark), validated against *our* surfaces. Text never takes the series colour; labels and values use text tokens.

## Marks and interaction (from the spec)

- **Columns:** at most 24px wide, a **4px rounded data-end, square at the baseline**, a 2px gap; solid hairline grid; clean ticks (0 / 10 / 20); compact numbers from 10K.
- **The SVG is drawn at its measured width** (`ResizeObserver`) rather than a scaled `viewBox`, which would stretch the text.
- **Every bar is focusable** (`tabIndex=0`, `role="img"`, an aria-label). The hit target is the whole day slot, bigger than the mark. The tooltip **leads with the value** ("19 replies"), and keyboard focus shows the same as hover.
- **Tooltips never gate:** "Show as table" lists every value.
- **One filter row** (7 / 30 / 90 days) scopes everything. **A refetch keeps the frame:** the previous render stays at reduced opacity, with no skeleton flash.
- **Status** (errors, tool failures) is **icon + label + colour**, never colour alone.
- **The anti-pattern check caught one mistake:** `tabular-nums` on the large stat-tile numbers. Equal-width digits look loose at display size, so they now apply only where numbers align (tables, axes).

## Tests

- **Fixture data** (`e2e/usageFixture.js`, served through `page.route`) gives deterministic visuals in both themes on desktop and phone, plus behaviour tests:
  - tiles and status labels;
  - keyboard focus on a bar shows its tooltip with the value first;
  - the table view has one row per day;
  - **the range filter refetches with `days=30`** and draws 30 bars;
  - Esc closes and **returns focus** to the Usage button.
- **Real backend:** a new user has 0 replies, no marks, and still 7 days on the axis.
- The full non-LLM suite passes **47/47**.
