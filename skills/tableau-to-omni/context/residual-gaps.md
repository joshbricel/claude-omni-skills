# Tableau-to-Omni residual fidelity gaps

This file enumerates the Tableau-side features that do not survive cleanly
to Omni, with the closest workable substitute the migration produces. Feed
these into the migration rationalization rubric (`migration-rationalization.md`)
during the "Rebuild" track decisions.

## Custom shape marks (e.g. gendered icons)

**Tableau:** the workbook embeds a custom shape file (`Female.png`, `Male.png`)
and uses Tableau's "Shape" mark to render gendered icons next to a count.

**Omni:** there is no built-in shape-mark equivalent for arbitrary user-supplied
images. The closest analog the migration produces is a `gender_callout` tile
(two-row spreadsheet showing Female / Male and the measure). Numbers only,
no iconography.

**Workaround:** a markdown tile can embed an image hosted externally. Hand-build
post-migration if visual fidelity matters.

## Regression / trend lines on scatter

**Tableau:** "Analytics > Trend Line" overlays a regression line on the scatter.
The Acme `New Members Scatter Plot` worksheet uses this on a per-geo trellis.

**Omni:** the bar/line/scatter mark types do not include a built-in regression
overlay. Some Omni instances support a `mark.type: trend` series, but it's not
universally available and not reliable from the import payload.

**Workaround:** run a regression in Snowflake (`REGR_SLOPE`, `REGR_INTERCEPT`)
as separate measures, plot the line as a second `series` with `mark.type: line`
on the same axes. Manual but reproducible.

The migration's scatter tile renders the points correctly; the trend line is
the gap.

## Per-mark color overlays on area+line trend

**Tableau:** the `Events Trend` worksheet uses three marks (Area, Line, Area)
to render a filled area chart with a line on top in a different color.

**Omni:** `area` and `line` are separate visConfigs. Overlaying them in one
tile via `series` with mixed `mark.type` per series works, but the visual
result is less polished than Tableau's.

**Workaround:** the migration ships a `line` tile by default. Hand-tune in
Omni UI to mix area + line series.

## Per-dashboard custom hero color band

**Tableau:** the `Events` and `New Member Categories` dashboards use a red
brand band; the `New Membership` and `Membership` dashboards use gray. The
band is a layout artifact (a Tableau text element with a colored background).

**Omni:** dashboards have a `themeId` setting which controls the global look.
Per-dashboard hero colors at the band level are not natively supported in
the import API. The migration produces the dashboards but uses Omni's
default theme.

**Workaround:** post-import, set a custom theme via the Omni UI, OR add a
markdown tile at the top of the dashboard with HTML/CSS for the hero band.

## "Current Filters Selected" text panel

**Tableau:** dashboards include a worksheet (`Filters Selected 2`,
`NEW Filters Selected 2`) that renders the current filter state as text.

**Omni:** the dashboard filter pills already display selected values
inline; there's no need for a separate "what's selected" tile. The
migration drops these tiles intentionally.

**Workaround:** none needed; it's a UX upgrade.

## Filter cascade (Tableau "actions")

**Tableau:** worksheet-level Action filters (e.g. clicking on a category bar
filters every other tile to that category) are defined per-action in the
workbook XML.

**Omni:** the `crossfilterEnabled: true` flag at the dashboard level enables
the same UX automatically. The migration sets this by default per
`cross_filter: true` in the spec.

**Edge case:** if some Tableau actions excluded specific tiles
(e.g. "filter all tiles EXCEPT the trend chart"), the migration's blanket
cross-filter doesn't preserve that scope. Post-edit `tileFilterMap` in Omni
UI, or extend the spec to declare per-tile filter exclusions.

## Tableau parameters

**Tableau:** the workbook has 3 parameters (`Age Distribution`,
`Date Selector`, `View by Date Selector`).

**Omni:** Omni topics support template parameters via `parameters:` in topic
YAML, but driving them from the dashboard UI requires manual control wiring.

**The Acme demo:** none of the parameters drive load-bearing logic in the
PDF dashboards. They're scope toggles. The migration drops them; document
them in the cut-list rather than translate.

## Per-event scatter aggregation grain

**Tableau:** the `New Members Scatter Plot` shows ~95 dots across 3 geos. Each
dot represents some grouping (likely per-event or per-week per-geo) so X
ranges 0-20 events and Y ranges 0-300 new members.

**Omni migration:** the migrated scatter aggregates by `(category, geo)`,
which gives 6 × 3 = 18 dots. This is structurally a different chart but
arguably more readable for the "what categories produce new members" question.

**To match Tableau exactly:** add `vw_events_wide.startdate[week]` to the
scatter's fields list (becomes implicit grouping), drop the `color` and
`column` settings, and trellis by `geo_name` only. The result will have
~200-300 dots, matching Tableau's density.

The migration ships the simpler form by default. Document this as a
parity-vs-readability tradeoff in the migration log.

## Custom palettes per dashboard

**Tableau:** the workbook ships custom color palettes (e.g. pink for female,
blue for male; categorical colors for sport categories).

**Omni:** color palettes are global at the org level (themes). The migration
maps colors via the `_mark_color` field on each `series`, but requires
hand-tuning for full visual match.

**Workaround:** define an Omni theme that mirrors the Tableau palette, then
set `themeId` on each migrated dashboard. One-time setup; reusable across
future migrations.

---

These gaps are predictable and documented up front so the rationalization
phase ("Rebuild" bucket) accounts for them. None of them block the data
migration; all of them affect visual fidelity.
