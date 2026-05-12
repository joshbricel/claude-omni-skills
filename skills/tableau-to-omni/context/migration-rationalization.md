# Migration Rationalization (the Business Track)

Most Tableau-to-Omni migrations fail because the team treats it as a technical lift-and-shift problem when it's actually a content rationalization opportunity. Most Tableau estates contain:

- The same metric calculated three different ways across three dashboards.
- "Owners" who left two years ago.
- Dashboards built for questions nobody asks any more.
- 15 dashboards with one power user each.

If you migrate the garbage, you have garbage in two tools. The migration is your one chance to NOT do that.

This file is the rubric the skill walks through before touching any technical step.

## The four-bucket rubric

For every dashboard in scope, decide one of:

| Bucket | When | What happens |
|--------|------|--------------|
| **Keep** | Used by 5+ stakeholders, drives a recurring decision, definitions are clean | Migrate as-is |
| **Consolidate** | Duplicates or near-duplicates of another dashboard | Merge into a single migrated dashboard |
| **Retire** | Not used in 90+ days, OR the question it answers is dead, OR the data is wrong | Do not migrate. Document the reason. |
| **Rebuild** | Right question, wrong execution. Calc fields are tangled or visualizations are misleading | Migrate the question, build fresh in Omni. Don't port the broken parts. |

## Inputs you need before scoring

### 1. Usage signals

Without Tableau Server access, you can't pull view counts directly. Substitutes:

- **Stakeholder survey** (template below). Send to the dashboard's stated audience.
- **Calendar of recurring meetings**. If a dashboard is shown weekly in a leadership meeting, that's strong "Keep" signal.
- **Slack / Teams search**: search for the dashboard name. Activity = engagement.
- **Tableau Server REST API** if available: pull `viewsLast30Days` per workbook.

For workbooks distributed only as `.twbx` files, ask the owner: who do you send this to, and how often does it come up?

### 2. Definition reconciliation

Run the calc field dump (`Step 2` in the SKILL.md workflow). For every metric mentioned by the business (revenue, win rate, attendance rate, etc.), find every implementation across dashboards. Document them in a single table:

| Metric | Dashboard | Calc field | Formula |
|--------|-----------|------------|---------|
| Win Rate | Sales Overview | `Win %` | `COUNT(Closed Won) / COUNT(Total)` |
| Win Rate | Pipeline Health | `Win Rate` | `SUM(Closed Won Amount) / SUM(Total Amount)` |
| Win Rate | Forecast | `winrate` | `COUNTD(Won Opps) / COUNTD(Opps)` |

Same metric, three definitions. Pick one. Get sign-off from the metric owner. Document the canonical version. Migrate only the canonical version.

### 3. Owner inventory

For every dashboard:

- Who owns it today?
- Who consumes it?
- Who owns the data behind it?
- Who owns it after the migration?

If the answer to "who owns it" is "the person who left" or "I don't know," the dashboard is automatically a Retire candidate unless someone steps up.

## Stakeholder interview template

For each dashboard going to Keep / Consolidate / Rebuild:

> 1. Who uses this dashboard, by name? (We'll talk to them.)
> 2. What decision does this dashboard inform? Be specific. ("Should we hire" not "headcount data.")
> 3. How often does this decision get made? Daily, weekly, monthly, ad-hoc?
> 4. If this dashboard didn't exist tomorrow, what would break?
> 5. What's missing or wrong on this dashboard that you've worked around?
> 6. Are there metrics on this dashboard you ignore? Why?
> 7. If you were starting fresh in Omni, what would you remove? Add?

15 minutes per stakeholder, 3 stakeholders per dashboard. Total: about 45 minutes per dashboard. Worth it.

## Scoring sheet

Build a Google Sheet or Excel with one row per dashboard and these columns:

| Field | Type | Notes |
|-------|------|-------|
| Dashboard name | string | from `extract/dashboards.json` |
| Last viewed | date | from server, or "?" if unknown |
| Active users (30d) | int | server stat or stakeholder count |
| Decisions driven | string | from interview answer 2 |
| Decision cadence | enum (daily/weekly/monthly/ad-hoc/never) | interview 3 |
| Definition cleanliness | enum (clean/messy/wrong) | from definition reconciliation |
| Owner today | string | who maintains it |
| Owner after | string | who maintains it post-migration |
| Bucket | enum (Keep / Consolidate / Retire / Rebuild) | the decision |
| Justification | text | one sentence per row |
| Estimated effort | enum (S / M / L) | small=auto-translate, medium=some manual work, large=rebuild |

The scoring sheet is the deliverable for Track A. It feeds the technical track's scope decision.

## What "won't migrate" looks like

Document everything you're choosing NOT to migrate, with a reason. This list is more important than the migration list because it's what you'll defend in the post-mortem when someone asks "why doesn't Omni have my dashboard."

```markdown
## Won't migrate

| Dashboard | Reason | Replacement |
|-----------|--------|-------------|
| Q1 2024 Bookings | One-time deck for a board meeting that already happened | None needed |
| Sales Rep Leaderboard (Old) | Replaced by "Sales Rep Performance" with same data, better calcs | "Sales Rep Performance" (migrated as Keep) |
| Pipeline Coverage by Region (East) | Duplicated by "Pipeline Coverage by Region" with a region filter | "Pipeline Coverage by Region" |
| Marketing Funnel (Aspirational) | Built but never used; metrics wrong | None; rebuild from MQL definition workshop if needed |
```

## Governance for the new world

Before importing the first dashboard, decide:

- **Folder structure.** Mirror your org. `/Finance`, `/Sales`, `/Marketing`, `/Ops` etc. Inside each, sub-folders for the major workstreams.
- **Naming conventions.** Length cap (40 chars), forbidden words ("v2", "old", "test"), required suffix on team-of-record dashboards.
- **Owner per folder.** Every folder has one human owner who reviews additions.
- **Label taxonomy.** `migrated-from-tableau`, `data-product`, `experiment`, `deprecated`. Lock the set.
- **Schedule policy.** Who can create email schedules? Default cadence?
- **Permission defaults.** Read-only by default. Editors are explicit.

Document these as a one-pager. Reference it during every migration session.

## Change management

A migration is a change. People resist change. Plan the comms:

1. **T-30 days**: announce the migration with timeline and deprecation date.
2. **T-14 days**: training session on Omni, recorded.
3. **T-7 days**: send links to migrated dashboards. Tableau still works, just labeled "Deprecated."
4. **T-0**: cutover. Tableau workbooks still alive but flagged as historical.
5. **T+30**: shut down Tableau access for migrated workbooks.
6. **T+60**: archive the old workbooks. They're now read-only history.

Skipping the comms = users still use Tableau, you maintain two tools forever.

## What "good" looks like at the end

- Every dashboard in Omni has a single named owner.
- Every metric has one canonical definition with sign-off.
- Folder structure mirrors the org.
- Labels mark migration status.
- The "won't migrate" list is published and defended.
- The Tableau workbooks have a sunset date on the calendar.
- The post-migration audit shows the Omni footprint is smaller, not larger, than the Tableau one.

If the Omni footprint after migration is larger than the Tableau footprint before, you migrated garbage.
