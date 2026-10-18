# ADR 0075: Market-level triggers, lockup and reverse-split classes, two calendar windows

**Status:** accepted (2026-10-18; orchestrator design call, architect-reviewed, pending owner
confirmation, see `docs/decisions/log.md`). Amends [0053](0053-edges-hypotheses-outcomes-and-one-harness.md)
(amendment 2026-10-08: ED4, item 7 "Event schedules", the schedule vocabulary) and [0073](0073-calendar-schedules-and-the-time-series-base.md)
decision 8 (where a schedule known only at D lives). Part of the EB H4 follow-ups; PR A records
the design and splits `config/edges/schedules/`, the classes, trigger and windows follow in
their own PRs.

## Context
Three kinds of timing the edge list needs have no home. A lockup expiry and a reverse split are
per-name events with a known anchor, like the classes of 0050. A VIX spike or an FOMC date is
one fact about the whole market: as an event class its base (the same class, other names) would
equal the universe, and the cross-section harness would count each trigger N times. Two more
calendar windows (the last sessions of a month, the turn of the year) fit 0073 as they are.

## Decision
1. **Event class `ipo_lockup`** (group `ipo_lockups@v1` in `features/rollups/events/`): fields
   `lockup_expiry_date`, `sessions_to_lockup_expiry` (0 on the expiry session, negative to -20
   after it), `lockup_release_terms` (`standard` | `early_release`), `lockup_days`,
   `ipo_offer_price`. Sign -1, `announced_ahead` (an entry may precede the anchor, as
   `earnings_expected`), anchor = the expiry session. Read with `latest_versions(through=D)`,
   `is_ipo` rows only. The CIK is mapped to an instrument through `instruments/company` as of D,
   never the row's own `instrument_id` (a later version, a survivorship leak). A base event; its
   edge is the short avoid-list side.
2. **Event class `reverse_split`** (group `reverse_splits@v1`, input `events/split`): fields
   `last_reverse_split_date`, `sessions_since_reverse_split`, `reverse_split_ratio` (< 1),
   `reverse_splits_1y`. Anchor = the ex-date, only rows with `ts <= D` (the table has no
   `known_from`). The ratio convention (new shares per old) is pinned by a test. The fund
   universe is excluded. The expression feature `reverse_split_recent` reads the group.
3. **A market-level trigger is not an event class.** A new schedule family
   `on_market:<trigger>` is measured by the 0073 time-series harness: a named universe, `base =
   "out_of_window"`, benchmark none, one horizon. Group `market_triggers@v1` in
   `features/rollups/market/` with fields
   `vix_spike_date`, `sessions_since_vix_spike`, `vix_spike_level`. Both legs are `macro/series`
   rows (`config/site/macro.toml`): VIX is FRED `VIXCLS` and VIX3M is FRED `VXVCLS` (Cboe closes
   via FRED, as `docs/data/vendors.md` says), each `pit = "lag"`,
   `release_lag_days = 1`, `licence = "personal"` (FRED terms: personal use only), so the group
   is personal. Neither is an ALFRED series: the unrevised close has one value, and its vintage
   is the observation date plus the one-day release lag.
4. **The VIX spike** is the first session where the latest fresh VIX is at least 30 and
   VIX / VIX3M is above 1 after at least 21 sessions without one. The thresholds are fixed in
   the feature; a change is a version bump. D is the session the reading was first known;
   a reading is known by D when its observation date plus the release lag is at or before D, the
   same rule for history and live (no ALFRED vintages involved). Placement
   (`time_series/triggers.py`) skips a trigger within `h` sessions of the last counted window,
   so windows never overlap. The base depends on later triggers inside the range (known by the
   range end, never a decision input), so a stretch near the range end can change when the
   range is extended; the run record says so.
5. **FOMC joins as `on_market:fomc`**, which amends 0073 decision 8 (a window whose placement
   needs a schedule known only at D is no longer `on_event:macro_release` when it is market-wide).
   `tdf_contrarian_flows` stays blocked: it needs `on_market:large_market_month`.
6. **Two calendar windows** (`calendar:<name>`, 0073): `pre_month_end`, the last 3 sessions of
   every month (it avoids the clash with the `month_end` rebalance schedule; a fitness test keeps
   `WINDOW_NAMES` disjoint from `SCHEDULES`), and `year_turn`, the last 5 sessions of December
   and the first 5 of January (length 10, belonging to December's year). A property test checks
   non-overlap per kind over 2000-2040. The weekend window is skipped: its evidence has decayed
   and it would add a trial. `year_turn` gives about 8 windows since 2018, below
   `MIN_INDEPENDENT_SESSIONS`, so it cannot reach `evidenced`.
7. **`etf_launch` is deferred**: it needs the owner's keyword list.
8. **Config layout**: the event-class vocabulary and schedule parsing move from `document.py`
   (963 lines; `config/edges/` at its module cap) to `config/edges/schedules/events.py`, which
   `document.py` re-exports unchanged; the market-trigger names land beside it. The calendar windows stay in
   `core/time/windows.py` (`WINDOW_NAMES`, ADR 0073).

## Consequences
The Guide and `guide_coverage` gain an entry per new class, trigger and window in the PRs that
add them. A market trigger has one trigger count per range, not per name, so its evidence is
small and shown with its counts. No table, grain or layer boundary changes.
