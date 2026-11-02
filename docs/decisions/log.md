# Decision log

Append-only, newest last: an entry is never edited except its `status` line (and the
`- confirmed:` line added with it); a reversal is a new entry. A unit test cannot check that a
diff touched only status lines, so a reviewer does. One entry per policy decision, or design
call worth a line, whoever took it (`.claude/skills/review-and-release`, section 2).
`decided by`: owner | Fable on the owner's behalf | orchestrator (design call). The
orchestrator never decides policy (who sees what, stored personal data, retention, money,
product behaviour, an ADR contradiction); a heuristic test rejects `orchestrator` on an entry
about those topics.
`status`: final | pending owner confirmation | overruled. `final` needs `decided by: owner` or
a `- confirmed: owner YYYY-MM-DD` line: only the owner's word makes an entry final. The owner
confirms or overrules by telling the session, which updates the entry (an overrule means a
follow-up PR).

(Entries before 2026-10-18 17:00 are in `log-2026-10-11-to-17.md`, those to 2026-10-24 in
`log-2026-10-18-to-24.md`; new entries are appended here.)

## 2026-10-25 | ADR 0065 amendment (PR 967) | The eight owner decisions
- Question: the eight owner decisions listed at the end of the ADR 0065 amendment 2026-10-25: label wording, which `close` setups, the Edges list headline, deflation on the post-publication basis, one setup per paper, the attestation, the window, the short-side cap.
- Options: the recommended answer to each / another answer to any.
- Decision: the recommended answers. (1) "after publication <years>", or "after the paper's sample" where they differ; (2) accept the 12 `close` setups, each with its named difference recorded; (3) two labelled columns, forward first; (4) Works deflated by the site-wide trial count; (5) `lazy_prices_10k_change` only, not `risk_factor_change`; (6) the per-setup attestation that parameters came from the paper's text, given at registration; (7) a closed window that stops at `frozen_from`; (8) short-side setups on a survivors-only universe capped at Not enough data.
- decided by: owner
- status: final
- Reasoning: the owner's words in the orchestrating session, 2026-10-25: "Accept the recommended answers on #966, #967 and #968. Tell each session to record them and release its PR (#966 first, then #968's renumber, then #967)."
## 2026-10-24 | Workflow-first trader site (ADR 0083) | TRADER bar, verdict-backed Ideas, historical exit rule, product rules
- Question: how does the paid trader product's site fit the workflow (find, check, test) and what are its list and legal rules?
- Options: as proposed in the use-case brief and workflow design (research artifacts of the 2026-10-24 sessions).
- Decision: TRADER bar Ideas, Setups, Test, Calendar; Explore by ⌘K; Backtests dropped; Settings (no account size or risk profile); Ideas from the picks of setups with a stored verdict `works` / `promising`, one ranking rule, licence-filtered per viewer, cap 15, "Unproven" until one exists, no per-viewer index; the setup's historical exit rule (stop = the drawdown 80% of winning trades never exceeded, fallback 2 x ATR(14), hold = horizon); product rules (one nightly batch, no alerts or broker links, "publishes setups", the model only translates, every statistic labelled backtested (hypothetical) or forward paper record, methodology and risk statement, US-only launch).
- decided by: owner
- status: final
- Note: the owner accepted the recommended answers on the ADR's gaps (2026-10-25, relayed by the orchestrating session: "Accept the recommended answers on #966, #967 and #968."): evidence strength = verdict level, then `lift_pts`, then out-of-sample trades; Regime and Explore off the bar but routed; the brief carries the shared list only; Unproven keeps today's size rule.
- Note: recorded in ADR 0083, which supersedes the 2026-10-22 "Ideas ranking rule, store and licence" index decision. The legal rules are research, not counsel's opinion.
- Reasoning: the research found two open jobs at $20-100 (an evidence-backed shortlist, an honest test); the bar follows them and the list rests only on stored verdicts.

## 2026-11-01 | French factors (ADR 0089) | Residual returns v2, licence, point in time
- Question: how should Kenneth French's daily factors make residual returns measurable before 2013, and under which licence and point-in-time rules?
- Options: (i) French factors before 2013-05 and ETFs after (a splice), or (ii) French factors throughout, as v2 beside v1; licence `personal` or `open`; the lag and `knowledge_ts` rules.
- Decision: (ii), with `factor_betas@v2` and `residual_returns@v2` beside v1 and v1 unchanged. Licence `personal` (no terms stated, CRSP-derived; loosening it means scoring the v2 verdicts again). Lag of 70 days, `revised = true`, each pull's changed values stored as a new vintage. A v2 label's `knowledge_ts` is the later of the window close and the vintage date (a 0053 amendment).
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Owner action: email kfrench@dartmouth.edu asking to use the daily files as regression inputs on a paid US ideas site that serves only our betas and residuals, with attribution. A yes makes the series `open`.
- Reasoning: a splice puts a structural break in the label in 2013 (long-only ETF spreads vs long-short research factors), and CAPE set the precedent for the licence.
## 2026-11-01 | Options-setups backend ADR 0088 | licence of market states, scope of the strictest-field rule, gate licence, holdout dates
- Question: (A) are the stored `market_conditions@v1` states open or personal; (B) does the strictest-field licence rule reach screener and universe fields; (C) does it apply to a gate; (D) what `holdout_from` does each research source give?
- Options: A open (recommended) or personal; B gate/entry/case/exit only (recommended) or every site; C confirm the reading or not; D per-source dates.
- Decision: A open; B gate, entry, case and exit only (0064 decision 10 not amended); C confirmed, a gate's fields are recorded in the trial licence; D first session after each source's data end: 2026-10-26 default for the three option-setups research files (earliest verdict 2027-01-26), Spintwig 2025-01-02, Lambda 2026-01-02, ORATS-only earnings 2026-03-02, AI study 2026-11-02.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Note: reversible; decided while the owner was asleep.
- Reasoning: A follows the `regime@v3.label` precedent and flips by `Feature.licence` with no recompute; B keeps existing setups visible; C follows from a gate being a rule; D never lets a gate be judged on data its research read. Recorded in ADR 0088 (PR #984).
## 2026-11-01 | Survivorship-free listing history (ADR 0087) | Delisting return convention; pull the data now
- Question: (1) which return to book for a bankruptcy or listing-standards delisting with no OTC print; (2) renew Tiingo Power, or pull the data now?
- Options: (1) (a) CRSP-style replacement -30% NYSE / AMEX, -55% NASDAQ, zero figure shown beside / (b) unmeasured / (c) zero. (2) renew one month / do not renew and wait / rush PR2 and backfill before 2026-11-09 / renew longer.
- Decision: (1) (a): a delisted name a setup would have bought is penalised, never flat. (2) pull the data now: the Massive delisted list was started on 2026-11-01; the Tiingo bars for the new ids follow PR2's ids; the renewal is raised again only if PR2 and that pull cannot both finish before 2026-11-09.
- decided by: owner
- status: final
- Reasoning: the owner's words in chat, 2026-11-01: "Ideally anything delisted if the setup suggests buying them it is a problem we should pick any options which penalizes picking a delisted stock is traded" and "let us pull the data. we still have enough time to do it. Let us start the backfill immediately." Decisions 3 to 5 of the ADR stay open.

## 2026-11-01 | Survivorship-free listing history (ADR 0087) | Decisions 3 to 5
- Question: (3) hold the 2010 `outcomes` backfill and `evaluate-edges` until the backfills (PR3) are done; (4) ETF closures before 2016 stay out of the universe, disclosed; (5) Norgate Platinum ($630 a year, Personal Use licence)?
- Options: as recommended in the ADR / the alternatives named there.
- Decision: (3) hold, as recommended. (4) stay out, disclosed, as recommended. (5) not now, as recommended; at most an owner-only cross-check.
- decided by: owner
- status: final
- Reasoning: the owner's word in chat, 2026-11-01: "3 to 5 aligned with your suggestion."

## 2026-11-01 | fundamentals@v5 IFRS share count (PR #965) | refetch and backfill, retiring v4, the net_share_issuance frozen period
- Question: (1) authorise the live-store refetch and history backfill; (2) retire `fundamentals@v4`; (3) how to treat the `net_share_issuance` edge's frozen period (from 2026-04-01) now that its input moves to v5?
- Options: as recommended by the architect re-review / the alternatives (no backfill, keep v4, restart the frozen period).
- Decision: (1) yes: `shares --force`, then the rollups backfill `--only fundamentals@v5`; (2) yes, retired only after the v5 backfill covers the full history (`retire-features --dry-run` first); (3) keep `frozen_from = 2026-04-01`: v4 values carry over unchanged and v5 only adds names that had no count, recorded as a coverage change in the edge notes and the run's trial log.
- decided by: owner
- status: final
- Reasoning: the owner's word in chat, 2026-11-01: "Yes, all three" (the architect's recommendations). `SHARE_CONCEPTS_VERSION_DATE` = 2026-11-02, the first nightly with the merged code.

## 2026-11-01 | Setups as positions and rules (ADR 0088) | Exits as values or rules, share path exits in P1, X1 monthly entry
- Question: (a) can an exit (and an entry) be a fixed value or a rule; (b) do share setups get path-aware exits in P1 or P2; (c) does X1 `index_put_write` enter every session or monthly?
- Options: (a) values only / values or rules; (b) P2 / P1; (c) `every_session` / the Cboe PUT roll date with the ladder as a variant.
- Decision: (a) both: a fixed value or a rule, compiled to one ordered list (ADR 0088 decision 4). (b) P1: build-table row E3c, a share path walker over `bars/1d` reusing E3b's exit evaluator, its trades in the trade contract, needing E3b and E6a, architect review (point in time); a setup without `[outcome.exit]` changes no stored verdict. (c) X1 enters on `calendar:after_monthly_expiry` (the first session after the monthly expiry, gated); the every-session ladder becomes a variant.
- decided by: owner
- status: final
- Reasoning: the owner's words in chat, 2026-11-01: `every_session` opens overlapping puts daily, so a fixed monthly entry matching the PUT index is the honest baseline; exits and entries are values or rules alike; share setups should get rule exits now. Recorded in `docs/options/backend-build.md` and `backend-concepts-1.md` (2.4a).

## 2026-11-01 | ADR 0083 amendment (Evening Desk site) | Ideas tabs, idea page, watchlist, sign-up answer, derived option figures
- Question: how do Ideas, the idea detail, a watchlist, the sign-up answer and option quotes work on the Evening Desk site?
- Options: as the mockups show / as amended below.
- Decision: (a) Ideas has Stocks | Premium tabs; the default comes from one sign-up answer; the cap of 15 and the Unproven fallback apply per tab. (b) A per-pick idea page, its sections filled from the setup: why it is here, the plan (the setup's historical exit rule), evidence, what could go wrong, learn this setup. (c) A watchlist: a per-user ticker list stored as user config (ADR 0029), filtering Ideas; tickers only, no quantities, basis or positions. (d) The sign-up answer is stored as a preference. Option quote display B: option screens show only our own derived figures (yield %, delta bands, return on collateral), never raw bid / ask, because the Cboe feed is unlicensed for display.
- decided by: owner
- status: final
- Reasoning: the owner's decisions of 2026-11-01 on the Evening Desk mockups, relayed by the orchestrating session. Recorded as the ADR 0083 amendment 2026-11-01; build plan `docs/ui/evening-desk-plan.md`.

## 2026-11-01 | Evening Desk plan | Product questions the mockups raised
- Question: (1) which option figures count as derived; (2) the raw-quote Options tab and `GET /chains/{underlying_id}/live`; (3) watchlist filter before or after the cap, and its size; (4) a "Yours" Ideas tab; (5) Past lists now; (6) what "Both" defaults to, and a start-page choice; (7) Settings scope; (8) the buying-power inputs; (9) typed sold-at price and cost basis; (10) the idea page's wording; (11) a Sunday premium edition; (12) premium strategy tests for traders; (13) the tab of an Unproven screener that implements no setup.
- Options: per question, the mockup / the plainest default within the fixed rules.
- Decision: (1) our computed mid premium, spread as % of mid, open interest and volume, a straddle from mids, IV, IV rank, delta, yield %, return on collateral, breakeven and probability below the strike are shown; never a vendor bid, ask, last or size. (2) Both stay, admin-only (role gate and REST `redact`); the plan's V6 removes the raw columns from trader screens. (3) After the cap (it only narrows tonight's list); at most 50 instruments. (4) No: Ideas is Stocks | Premium; the watchlist lives in Settings and the ticker Watch toggle, followed and own setups on Setups. (5) Deferred to its own ADR (ADR 0083 decision 2). (6) Both -> Stocks; one preference (the default Ideas tab), no start-page choice. (7) In: theme, default tab, country shown read-only (US), sign out; out: nightly brief toggle, plan / trial, data download, account deletion. (8) A typed contract count (component state only), Reg-T only, no named broker rules. (9) Never stored: not in the URL, `localStorage`, user config or logs. (10) "The setup's rule holds Monday at a premium of $0.55 or more"; "Copy exit rule as text"; "The plan" shown as the historical exit rule. (11) No: the same nightly list. (12) Owner-only now (ADR 0088 decision 12). (13) Stocks.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: each keeps the fixed rules (publisher only, no sizing or stored positions, one nightly batch, labelled statistics, decision B) with the plainest default; a mid, a spread ratio and a straddle are our computations and OI / volume are exchange statistics, not quotes; billing, brief delivery and the scorecard have their own ADRs; HOD-derived evidence stays owner-only until its terms are read.

## 2026-11-01 | Evening Desk plan | Vertical slices, no new components, the option grid's grain open
- Question: how is the Evening Desk build cut, and how are the architect's and the simplicity review's findings folded in?
- Options: slices by layer (design system, pages, reads) / vertical slices that each ship one screen end to end.
- Decision: vertical slices V1-V12 on data that exists today, then O1-O4 following the options backend (E4, E6, E9-E12b); every mockup element mapped to an existing component or a variant (no `Stepper` or `Breadcrumb`); the Ideas setup-picks read gets its own owner (`ideas-setup-picks`, `services/read/ideas/`) with `ideas-list` narrowed to Unproven, the inverse pick reads outside `pick_edges.py`; Reg-T stays in `services/preview/options/`, not `quant/`; the option grid's grain (a read over the stored chain plus a small catalogue group, or a catalogue group only) is the architect's first call in V6; `put_wing@v1` / `call_wing@v1` unchanged.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: the owner's instruction of 2026-11-01 ("new screens are available and work end to end, incrementally"); the architect review (file-disjointness, ownership, licence, cache key) and the simplicity review (cut two components, merge slices).

## 2026-11-01 | Evening Desk V2 | Setups library and setup page: what ships now, what waits
- Question: (1) the verdict words (the mockup's "Too few cases to tell", "No better than chance", "Baseline" against the read model's `not_enough_data`, `not_working`, `diagnostic_only`); (2) "Start here" without a curated list; (3) "Ideas tonight" before V3's inverse read; (4) the forward-record label without a `since` date; (5) the "Before you act" items.
- Options: (1) relabel now / keep the served words and map only the tone; (2) a curated list in config / the first three of the best verdict group; (3) the followed-setups desk only / leave the section out until V3; (4) derive the date in the browser / label it "Forward paper record" until the read serves `since`; (5) setup-specific / three checks that hold for any setup.
- Decision: (1) keep the served words (they are Guide terms and filter labels) and map each code onto the design system's verdict tones; the relabel is a follow-up with the Guide terms and filter definitions. (2) The first three of the best verdict group, shown while the list is not narrowed. (3) Left out; a follow-up PR adds it from V3's setup-to-picks read (the desk covers followed setups only and "none tonight" would mislead for the rest). (4) "Forward paper record" without a date on the live-record strip; `PaperRecord.since` is a read change for a later PR (the browser derives nothing from rows). (5) Three generic checks (report date, the stop is history, hypothetical and at risk); the Guide entry holds the explanation.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: each keeps the fixed rules (labelled statistics, publisher wording, nothing derived in the browser) without a read change in this slice.
## 2026-11-01 | V7 onboarding | The sign-up question has two answers and the skip button starts with shares
- Question: the mockup offers Stocks / Options / Both plus an optional watchlist; the amendment stores one `[ideas] default_tab` of `stocks` or `premium`. What does the question offer, and what does the skip store?
- Options: three answers with Both = stocks / two answers (mostly shares, mostly options), Skip stores shares / Skip stores nothing and asks again.
- Decision: two answers, "Mostly shares" (`stocks`) and "Mostly options (selling premium)" (`premium`); Skip stores `stocks`, so the question is asked once; the watchlist is added in Settings or with the Watch button, not in the question.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the stored value has two states; asking again on every visit after a Skip would nag; the user can change it any time in Settings.
## 2026-11-01 | Evening Desk V1 | Wording of the conflicts statement and the bar's Test tab
- Question: what may the Guide's "Conflicts" section claim, and where does the bar's Test tab point before V9?
- Options: claim only what ADR 0083 fixes / also state owner holdings and data-vendor ties.
- Decision: the section states only what ADR 0083 decision 4 and ADR 0026 fix (subscription-funded, no broker links, buttons or commissions, one list for everyone, setups published rather than advice, no name listed for payment); a statement about the owner's own holdings or paid data vendors is not written until the owner decides it. The bar's Test tab points at `/screeners` until V9 moves the flow to `/test` and redirects.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: a Fable agent reviewed the draft: every sentence maps to ADR 0083 decision 4 or ADR 0026, nothing to cut, nothing to add (no "independent" or "unbiased"), owner holdings and vendor ties stay unwritten; a conflicts page that claims more than the product rules fix would be an invented policy; "no name listed for payment" follows from the one fixed list built by rules.
## 2026-11-01 | V8 Calendar PR (#1027) | /calendar distant-link budget raised by the Earnings week table
- Question: the Earnings week table (FeatureTable, the column factories and the column picker now load on `/calendar`) puts the route at 357013 B gzip on the wire against the shrink-only `network` budget of 334800 B (+22 kB). Raise once, or make the week view lighter?
- Options: raise the one route budget to measured + the 5 % headroom with a dated reason / a lighter week view (a lazy table chunk, the picker split out) / drop the table for a list.
- Decision: raise `network./calendar.wire_gzip_bytes` once to 374900 B (CI 357013 B + 5 %, the #909 headroom), with a `reasons` entry "2026-11-01 #1027 the Earnings week table is the Calendar's default view: FeatureTable, its column factories and the picker load with the page; the table is the feature, not a shared-code move"; no other budget changes. No lighter view: the table is the default view, so a lazy chunk would still load on first paint and add a request over the request budget, and the picker split out saves well under a kilobyte.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the same shape as #939's Explore raise (+23 kB, "the table is the feature"), the owner's only precedent for a wire raise that is not filter-bar shared code; the 5 % headroom is the owner's rule of 2026-10-23 for route budgets; a feature's cost belongs in its budget, and shrink-only means a hand raise with a reason, never `PERF_UPDATE`.

## 2026-11-01 | V8 Calendar PR (#1027) | Earnings week table: filter-bar exemption, time-boxed
- Question: `architecture/web_filter_bar.toml [exempt]` gains `src/pages/trader-calendar/ui/EarningsWeek.tsx` (the week's reports of the scope list or one screener's picks, narrowed by the source picker). The rule says a table of many rows is never exempt and `[migrating]` takes no new line. Exempt, or build it on `SurfaceFilterBar` now?
- Options: exempt with a dated follow-up / build on the bar now over a `calendar_week` surface (`config/site/filters/calendar_week.toml` with filters on `rollup.earnings@v1.next_earnings_date`, `earnings_time`, `feature.earnings_move_vs_usual`, the overpaid counts and chain liquidity; their Guide terms in `guide/glossary/filters.toml`; `FeatureTable` in server mode with `keys` and `filters`, which the instruments read already combines; a views scope) / build on the bar now reusing the `universe` surface's filters with a scope of its own.
- Decision: exempt, time-boxed: the reason line names the follow-up slice V8c and its date, due by 2026-11-08 (the PR after the earnings pricing features' first nightly), and V8c builds the `calendar_week` surface above and deletes the line; the exemption is not a precedent for any other many-row trader table (the two admin "not yet on the bar" lines are the only other ones, and both carry a follow-up).
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: a `calendar_week` surface built today would serve every meaningful filter as `withheld` (NOT_STORED): `earnings_moves@v1` and `implied_move@v1` have no rows until their first nightly after this PR merges, so the bar would be empty chrome on the Calendar's default view; reusing the `universe` surface (sector, market cap, liquidity) is less code but filters a week's reports by the wrong axes and would conflate saved views with Explore's. The rule's intent (every many-row table gets the bar) holds through the dated line; the owner may instead choose the `universe` reuse now, which costs a filter-bar shared-code raise on `/calendar` (pre-approved) on top of the raise above.

## 2026-11-02 | Pre-push queue | A machine-wide queue for `make changed`, most dependants first
- Question: eight sessions pushing at once ran five pre-push `make changed` together (load 42, 12+ min each); how is the load bounded?
- Options: leave it / a per-worktree lock only / one machine-wide queue.
- Decision: one machine-wide queue (`scripts/ops/push_queue.py`), 2 slots by default, ordered by priority = open PRs that depend on the pushed one (stacked on it, or naming it as `Stacked on` / `Depends on` / `waits on` / `needs #N`), then arrival; a later push with more dependants goes first.
- decided by: owner
- status: final
- Reasoning: the owner's decision in chat; two concurrent runs is what the 10-core / 16 GB Mac carries, and the PR others wait on should clear first.
## 2026-11-01 | ADR 0088 E6b (the judge's inputs) | Merge timing of the fingerprint shift, the 2-PR split, the tails defaults
- Question: (1) E6b-1 changes every stored verdict fingerprint once; Ideas reads only stored verdicts (ADR 0083 decision 2) and auto-deploy restarts the API within 5 minutes of a merge (`docs/hosting.md`), so Ideas is empty from the deploy until rows exist under the new fingerprint. Merge on green, or hold for the owner? (2) Approve the split into E6b-1 (fingerprint PR) and E6b-2 (option harness, no fingerprint change) and the `[tails_verdict]` defaults?
- Options: (1) merge on green as soon as CI passes / hold `no-automerge` + `needs-owner` for the owner's moment / make Ideas fall back to the live judge like the edges list (`versions.load_summary`). (2) one PR / two PRs; the 2.6 defaults / tighter or looser.
- Decision: (1) Merge on green, timed, no `needs-owner`: the orchestrator removes `no-automerge` only (a) after E6a has merged and its LEG_VERSION 5 re-run is stored (the plan's prerequisite, itself owner-authorised), (b) with the read-only `edge-verdicts --dry-run --expect-same-headlines` result from the worktree in the PR body at 0 mismatches on the live store (a dry run writes nothing, so the session may run it), and (c) on a weekday morning after a complete post-session, so the window closes the same evening. The window needs no owner action: the post-session's own `edge-verdicts` step (ADR 0053 amendment 2026-10-22) stores that night's canonical runs under the new fingerprint; the real-data comparison already happened in (b), so the nightly's `no_prior` is not a gap. The owner's same-day re-store (plan step 5.3) shortens the window to minutes but stays owner's-words only (a live-store write). The live-judge fallback for Ideas is refused: it contradicts ADR 0083 ("stored verdict", one nightly publisher), which only the owner may override. (2) Both approved: two PRs, so the one risky deploy (66 headlines re-stored and compared) is separate from the option plumbing and E7 waits only on E6b-1; the 2.6 defaults as written (`option_cost_level = "full"`, `promising_psr = 0.90`, `works_psr = 0.95`, `max_cvar_ratio = 1.25`, `min_tail_windows = 5`, `bootstrap_draws = 2000`, `bootstrap_mean_block = 3.0`), with the seed from the trial identity plus a frozen constant, not the leg key. Note for the owner: `min_tail_windows = 5` at 5 % needs about 100 out-of-sample windows, so on a bare 3-month holdout `cvar_ratio` is NOT_MEASURED (never a pass) and Promising waits; that is the conservative side and stays until an option setup reaches its first verdict. No site edge is `option_pnl` today, so the defaults move no stored label; each later tune is one re-store.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Note: reversible; the empty Ideas window is at most one trading day on the pre-launch site and closes itself; decided while the owner was away.
- Reasoning: the owner-away rule (2026-11-01: PRs merge as built, no `needs-owner`); CLAUDE.md "PRs auto-merge"; the live-store rule in `.claude/skills/review-and-release` section 2 (a dry run is a read; the nightly step is the sanctioned writer); ADR 0083 decision 2 fixes "stored verdict"; ADR 0088 design 2.6 fixes the thresholds as design calls under review-and-release section 2.

## 2026-11-01 | ADR 0088 S5 | short_premium_liquidity as a rule preset: decisions and the stale-chain contract
- Question: the Python screener gave QUALIFIED / LIQUIDITY_RISK / UNKNOWN / REJECT and its UNKNOWN rows made a run PARTIAL (so a stale-chain tolerance excluded them, ADR 0054). A rule screen decides every row (ADR 0030: missing never passes, REJECT). Port as is, or keep the four decisions?
- Options: a rule preset with REJECT for every non-pick (the engine's one vocabulary) / soft criteria to keep LIQUIDITY_RISK / extend the engine to produce UNKNOWN.
- Decision: the plain rule preset: pick = chain current (`liq_status` OK) and the short put or the short call tier A / B (a group); everything else REJECT. `option_liquidity@v1` already is the feature group, so no new group was added. The legacy CSV reads the rule run's `[columns]` (same names) and `process_further` is QUALIFIED; the stale-chain contract moves to the gate: a stale name is a reject (never a pick), the `chains` step fails when more are stale than it tolerates, and the screens step needs it.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: owner rule G14 (every screener is a rule) and the less-code rule; changing the engine for one preset adds a second vocabulary. What is lost: LIQUIDITY_RISK on tier C/D names, and a PARTIAL screen on stale chains (the chains gate already fails the night). The liquidity picks are identical: QUALIFIED iff the put or call tier is A / B on a current chain.

## 2026-11-01 | ADR 0088 S5 | The liquidity screen on Ideas
- Question: as a rule preset `short_premium_liquidity` is a listed site screener (the Python one was ignored by the read model); it implements no setup, so its first 5 picks (`site_top`) show under Ideas "Unproven" in Stocks. Keep it off Ideas?
- Options: (a) accept it, ranked by `chain_oi` (deepest chain first) instead of instrument id / (b) a preset-level exclusion from Ideas (a schema addition).
- Decision: (a). Every site screener without an edge is listed the same way; an exclusion flag is a new schema field for one preset. The page labels the picks Unproven.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the less-code rule and consistency with the other 90 presets; the owner may ask for (b) if a liquidity list on the home page is unwanted.
## 2026-11-02 | ADR 0088 E16 (position baselines) | What a `position:<template>` baseline is valued as, and which picks it holds
- Question: G19 says "the setup's own picks valued with another template" and leaves open (1) which screener's picks when a setup has several, (2) what a shares baseline is valued by on an option setup (which has no benchmark), (3) whether a baseline may hold the picks as the other side, and (4) whether a baseline on the other outcome grain (an option setup against the stock alone, X3's shape) is in scope.
- Options: (1) the first screener / one baseline per screener. (2) the setup's own measure / the raw return over the same window. (3) allow `short_shares` of a long setup / refuse. (4) refuse a mixed grain / read both grains.
- Decision: (1) the first screener of the edge (the ensemble's first screener for an ensemble); the setup's own picks, never the bottom of the ranking. (2) the raw `fwd_return` when the setup has no benchmark (an option setup's value is a return on the spot; excess over a benchmark would not compare), else the setup's measure. (3) refuse: the picks are the setup's own, so shares are held as its own side (`long_shares` for a long or option setup). (4) read both grains: the baseline's legs are measured on the grain its template needs, the commit sequences of both are summed so a commit to either re-measures the stored legs, and the baseline's rows are keyed apart from the setup's (its leg and trial keys carry the template, so no site edge's stored key moves). A baseline is a `baseline` role row: never a trial, never a PBO peer, never in `screener_hashes`.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the plan's "paired base, not a trial" (G19, 2.7) fixes the role; the raw return is the only stock figure comparable with an option's return on spot (a covered call earns the stock's move plus the premium); refusing the opposite side keeps "own picks" true (a short leg is ranked from the bottom, so it would silently hold other names); reading both grains is what A3 against `position:long_shares` needs, and the summed sequence is the existing staleness rule (ADR 0063) extended, not a new one. Option-template baselines are limited to option_pnl setups (they take the setup's entry, tenor and cycle) and fail with a named error otherwise.
## 2026-11-01 | ADR 0088 S2 / S3 / F2 | B2 reuses the two existing presets; S3 already merged; F2 is a coverage test
- Question: S2 says reuse `low_volatility` and `ivol_high` and add `total_vol_high` only if a run shows the sort differs. Build it now?
- Options: add `total_vol_high` now / add nothing until a run of the two edges (X4) shows the sort differs.
- Decision: add nothing. S2 is a reuse, so it has no PR; `total_vol_high` waits for the X4 run. S3 (`earnings_move_rich`, `earnings_move_cheap`) merged in #993, so it needs no slice. F2's 33 verdict-column terms were written with F1 and F3 (#992, #1008); this PR adds the test that keeps them in step with the columns and keeps their wording descriptive, and rewords the two sentences that told a reader what to do.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the build doc's own condition ("only if the run shows the sort differs") cannot be met before X4's run exists, and a third near-duplicate preset would add code the owner's less-code rule (2026-10-25) asks to avoid.
## 2026-11-02 | `make changed` about 3x faster (pre-push gate) | Fresh base, parallel step 1, related vitest, no local e2e; then affected-only tests
- Question: each pre-push `make changed` took 10-12+ min on the shared Mac and the queue (#1048) backed up; what may the local gate drop or narrow while CI stays the gate (rule 9)?
- Options: keep the gate as it is / narrow it in two PRs (A: fetch `origin/main` before computing the changed files and diff from the merge base; the mirrored tests at `-n $(WORKERS)`; one `vitest related` run instead of one vitest per folder; the Playwright e2e specs CI-only; the bundle budgets kept local; caches kept across runs. B: affected-only tests with `pytest-testmon`, `tests/architecture` in full whenever an architecture-sensitive path changes, architect-reviewed) / drop the local gate.
- Decision: the two PRs as described; the bundle build and budgets stay local (the web CI failure seen most).
- decided by: owner
- status: final
- Reasoning: the owner's decision in chat (2026-11-02); the local hook exists to catch the common CI failures early (architecture and layout tests, bundle budgets, Guide coverage, lint and types), not to repeat CI.

## 2026-11-02 | Pre-push hook (`make pre-push`) | A 90 s fast lane of the checks that fail most; the rest CI's (replaces the testmon plan of PR B)
- Question: after #1051 the hook (`make changed`) still took 5-12 min a push on the shared Mac while GitHub CI idled; what should run locally?
- Options: affected-only tests with pytest-testmon (the earlier PR B plan) / a fast lane chosen by measured failure frequency per second of local cost, the rest in CI / no local hook.
- Decision: the fast lane. The hook runs `make pre-push` (`scripts/pre_push.py`, target 90 s warm): `make numbering` and a fixed list of fast file- and TOML-only tests that failed most in the last 100 red CI runs, and for web changes Prettier, Stylelint, `ds:check` and the bundle and DOM budgets; a merge-only push runs the python lane alone. ESLint, `tsc`, vitest, the mirrored pytest, e2e and screenshots are CI's. `make changed` stays as the full local check; CI's per-branch `cancel-in-progress` stays (now tested).
- decided by: owner
- status: final
- Reasoning: the owner's words in chat (2026-11-02): "things which often fail (in make changed locally or in CI previously) we do locally through a hook, but minimize the runtime on local load; the rest we push to GitHub CI." The table and timings are in `docs/ci.md` "Pre-push fast lane".
## 2026-11-02 | Harness: shared-file conflict loop, push-queue order | Merge drivers and `Unblocks:`
- Question: how do five UI PRs stop re-conflicting on `perf-budgets.json` and the two latency files at every merge to main, and how does the push queue favour the push that frees the most work?
- Options: hand-merge each time / merge drivers (budgets union + max, views union) plus regeneration in `merge_main.sh` / generate the files only in CI. Queue: open dependants only / also an `Unblocks:` PR-body line.
- Decision: merge drivers in `.gitattributes` (`scripts/ops/merge_budgets.py`), installed by `worktree.sh`, `merge_main.sh` and checked by `make doctor`; the view list regenerated after a merge that changed it; `Unblocks: V10, V11, #N` counted once per id in the queue priority. The route list is read as the budget keys themselves: a route one side removed (the other unchanged) is dropped with its e2e entry and reasons; there is no separate router list to consult.
- decided by: owner
- status: final
- Reasoning: the owner's decision in chat (2026-11-02); the shared files are mechanical unions, so a conflict there carried no judgement, only a 5-15 minute re-run each time.

## 2026-11-02 | V11a option calculators and the filter bar | Exempt: a drill-down of typed inputs, not a stored list
- Question: ADR 0082 puts every table, list or feed behind the shared filter bar; do the Roll a put and Calls on shares calculators carry it?
- Options: exempt them in `architecture/web_filter_bar.toml` / give each the shared bar.
- Decision: exempt. At most 18 rows computed per request from what the trader typed, nothing stored, no cross-row search; the "same delta" and "include rolls that cost money" toggles are inputs the server re-runs on, not row filters. Guide entries still ship for every column and control.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the [exempt] kinds of `web_filter_bar.toml` (a fixed handful of rows, a drill-down of one thing) fit; wrapping server inputs in the filter bar would misrepresent them (precedent: Explore's Compare table).
## 2026-11-02 | V11b Buying power: which margin rules | The exchange minimum (Reg-T) only, no named broker
- Question: the OptMargin mockup has a "Your broker's rules: tastytrade" select; which margin rules does the calculator offer at launch?
- Options: (a) the Reg-T / Cboe exchange minimum for an uncovered short option only, no broker named; (b) a site-config list of named brokers with their published multipliers, sourced and dated, kept by hand; (c) (a) now, (b) later only as a sourced, dated change.
- Decision: (c). The select is dropped; its place is an "exchange minimum" label with its Guide entry (a broker may require more; a margin figure is a floor, not a quote). Cash-secured stays exact (strike x 100 x contracts).
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: the exchange minimum is published, stable and broker-neutral, the one figure the site can state accurately for every trader; a stale multiplier shown as a named broker's rule is a data-quality and liability risk (data tenet), a hand-kept broker list has no ingestion check, and a broker select sits against ADR 0083's no-broker-links and no-account-profile rules.
## 2026-11-02 | V10 Describe it (Evening Desk) | Where Describe it lives, and C18's `not_said` status
- Question: (1) the Describe box sat on Expert; where does the sentence way in live now? (2) the plan gives C18 (`PartCard`) a `not_said` status; does V10 add it?
- Options: (1) its own page `/test/describe/$id` with the rows it became / a mode of Expert. (2) add `not_said` now, unused / add it with the first draft that has a part the trader did not say.
- Decision: (1) `/test/describe/$id` (steps, draft bar, the sentence box with the tagged sentence (C17) and the part cards (C18), then the criteria table, where a proposed formula waits as a pending row); Expert keeps the rules, preview and funnel; a new Describe draft opens there. The Builder's state is per page, so the rows sit beside the sentence and nothing pending is lost on a page change. (2) not now: a screener draft has no part the trader did not say (the mockup's two, "what it should beat" and "why it works", are a setup's, which Describe it does not draft yet); the status ships with the slice that drafts a setup from a sentence, with its Guide entry, so no unused design-system state lands.
- decided by: orchestrator (design call)
- status: pending owner confirmation
- Reasoning: one tree, no lost pending formula; a component state with no screen to show it is dead code and an untested Guide entry.
## 2026-11-02 | ADR 0083 amendment (c), V7 follow-up | The watchlist filters both Ideas lists; one "Showing N of M on your watchlist" line, no toggle
- Question: the watchlist filters Ideas after the cap of 15 (plan V3 / V7). Does it also filter the Unproven pool (`Query.ideas(tab)`)? With a watchlist, what do `total` and a setup's `picked` count, and does the page say how many the watchlist hid? Does the page need a Watchlist / All toggle?
- Options: setup list only / both lists. Counts watched only / unfiltered with a "shown of" line. A toggle / a line with its Guide entry and a link to Settings.
- Decision: both lists (the pool after the rule ranked it, so each screener's first picks are unchanged); `total` and `picked` stay unfiltered, `shown` and the licence left-out count only watched names, and the page says "Showing N of M ideas: your watchlist" (`watchlist` on `SetupIdeas` and `Ideas`: the count before the filter, null with no watchlist); no toggle, the line's "Edit watchlist" opens Settings.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: one rule for the whole page is what the amendment's "on Ideas it is a filter" says; the pool already filters server side, so it is one more predicate; without the "of M" an empty group would read as "no picks"; a toggle adds page state and a control (owner 2026-10-25: less code).
## 2026-11-02 | ADR 0088 X3 | `covered_call_strike_tenor`: the named ETFs, delta, cycle, the IV-rank tenor case
- Question: the plan names the edge (A3 + C4, baseline `position:long_shares`, a tenor case 30 / 45 on IV rank) but not its symbols, delta, schedule, hold cap, the IV-rank field and threshold, the variant shape, exits, costs, or whether the single-name version ships with it.
- Options: symbols 3 (X1's) / 7 across asset classes. Delta 0.30 (template) / 0.20. Schedule `every_session` / `calendar:after_monthly_expiry`. Field `feature.iv_rank` (IBKR, personal) / `rollup.iv_history@v2.iv_rank_252d` (ours, open); threshold 0.5 / 0.7. Main case-valued / main fixed 45 with the case as a variant. Exits none / take-profit 50%. Single names now / after D6.
- Decision: SPY, QQQ, IWM, DIA, XLE, GLD, TLT; the template's 0.30 delta; `every_session` with `horizon_sessions = [21]` (decisions 21 sessions apart; every trade closed at 21 sessions; the 30-day point picks a different monthly expiry from the 45-day one on about half the sessions); the case `tenor = 30 when rollup.iv_history@v2.iv_rank_252d >= 0.5 else 45` as a `[[variants]]` entry over a fixed-45 main; no `[outcome.exit]`; `cost_bps = 35`; `skip_report_in_life = true` (a no-op on ETFs); the `liquid_optionable_floored` single-name edge is a follow-up. Two changes from Fable's pick, forced by the code: the monthly `calendar:after_monthly_expiry` cycle holds its window's length (1 session), so a 31-session hold needs a plain schedule; and a named sleeve does not value `position:` baselines (they are the cross-section harness's), so `position:long_shares` is not declared (now refused for a sleeve) and the delta-equivalent stock is the reading against the stock. A third change, from the architect review: a 31-session hold put the expiry floor (the later of S + tenor and the hold's end) past 30 days, so both tenors chose the same expiry and the variant could not test the rule; the hold is 21 sessions. These three changes were made by the implementing session from the code.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: seven liquid chains across asset classes give the rank case dispersion that three index ETFs would not; 0.30 keeps one template and is the band the c19 evidence describes (beta minus the upside sold); our own rank keeps the edge open-licence and one source across the holdout; a fixed main is what the case is compared with; no exits keep A3 a clean test; 35 bps is the existing short-option convention.

## 2026-11-02 | Plan O4 | The option idea page's premium floor is not applicable until a setup declares a minimum credit
- Question: the plan's O4 line is "the setup's rule holds Monday at a premium of $X or more". No stored field gives $X: no setup declares a minimum credit (concepts 2.16 EF-G14, deferred) and no option verdict stores a typical trade to derive a break-even from. What does the page show?
- Options: derive a floor from the example (credit less a typical trade); derive it from the setup's evidence once stored; show UNKNOWN with its reason.
- Decision: the section carries `mondayFloor` null and `floorUnknown` NOT_APPLICABLE with the reason, and the Guide entry says so; the figure appears when a setup declares a minimum credit (a `select` rule at entry, EF-G14) or its stored evidence supports a floor, by inverting the premium figures at the example's strike and days. No number is invented in the read.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: ADR 0088's rule that figures are derived or UNKNOWN, never filled; an invented floor would read as the setup's own rule; the architect review of the read agreed.

## 2026-11-02 | ADR 0088 decision 15 | Every option outcome kind, including `expires_otm`, waits for its unseen holdout; each setup declares its own `holdout_from`
- Question: the judge held back only `option_pnl` verdicts; `option_model_pnl` setups (c12 to c18) could be judged Works today. Does `expires_otm` (a short option's not-assigned hit measured on the underlying's bars) count as an option setup for the holdout? One site-wide start, or per setup? Does the run's end date show 3 months of unseen trades?
- Options: gate `option_pnl` only / all option kinds with or without `expires_otm`; one site-wide start / a start declared per setup; the run's end / closed trades measured from the start.
- Decision: gate `option_pnl`, `option_model_pnl` and `expires_otm` (a short-premium verdict is an option verdict whether its hit is priced from chains or read from bars; a fitness test puts every outcome kind on one side); a setup declares `holdout_from` in its document (the latest of its gates' and thresholds', never before the site's 2026-10-26; not a run input); the verdict needs measured windows decided from that date whose last exit is 92 days after it, read from the run's own series.
- decided by: Fable on the owner's behalf
- status: pending owner confirmation
- Reasoning: ADR 0088 decision 15 says "no option verdict before its unseen holdout"; the data source is the measurement, not the claim; the earliest verdict for a `holdout_from` of 2026-10-26 is a window closed on 2027-01-26.
