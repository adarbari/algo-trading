/** Test fixtures: a server `LlmUsage` as the operation selects it (a normal month, over a cap, empty). */
import type { LlmUsage, UsageCall, UsageTally } from './types';

export const tally = (over: Partial<UsageTally> = {}): UsageTally => ({
  calls: 0,
  inputTokens: 0,
  outputTokens: 0,
  callsWithoutTokens: 0,
  spentUsd: 0,
  billedUsd: 0,
  reportedUsd: 0,
  boundUsd: 0,
  freeCalls: 0,
  unknown: null,
  ...over,
});

export const call = (over: Partial<UsageCall> = {}): UsageCall => ({
  ts: '2026-10-08T14:00:00+00:00',
  provider: 'claude',
  model: 'claude-haiku-4-5',
  useCase: 'screener-draft',
  user: 'abhi',
  inputTokens: 1200,
  outputTokens: 300,
  latencyS: 1.8,
  costUsd: 0.0027,
  costBasis: 'price',
  outcome: 'ok',
  fellBackFrom: null,
  runId: 'llm_usage-2026-10-08-1',
  unknownFields: [],
  unknown: null,
  ...over,
});

const NOT_REPORTED = {
  code: 'NULL',
  kind: 'NOT_STORED',
  guideTerm: 'unavailable_not_stored',
  kindText: 'not available for this instrument',
  cause: null,
} as const;

const DAYS = ['2026-10-06', '2026-10-07', '2026-10-08'];

export function usage(over: Partial<LlmUsage> = {}): LlmUsage {
  const today = tally({
    calls: 3,
    inputTokens: 2400,
    outputTokens: 600,
    callsWithoutTokens: 1,
    spentUsd: 0.7527,
    billedUsd: 0.0027,
    reportedUsd: 0.5,
    boundUsd: 0.25,
  });
  return {
    today: '2026-10-08',
    recorded: true,
    budget: { dailyUsd: 1, monthlyUsd: 10, over: 'free', reportedCallUsd: 0.25, error: null },
    windows: [
      {
        key: 'today',
        start: '2026-10-08',
        end: '2026-10-08',
        tally: today,
        cap: { kind: 'daily', limitUsd: 1, usedShare: 0.7527 },
      },
      {
        key: '7d',
        start: '2026-10-02',
        end: '2026-10-08',
        tally: tally({ calls: 9, spentUsd: 2, reportedUsd: 1.5 }),
        cap: null,
      },
      {
        key: '30d',
        start: '2026-09-09',
        end: '2026-10-08',
        tally: tally({ calls: 20, spentUsd: 4 }),
        cap: null,
      },
      {
        key: 'month',
        start: '2026-10-01',
        end: '2026-10-08',
        tally: tally({ calls: 12, spentUsd: 3 }),
        cap: { kind: 'monthly', limitUsd: 10, usedShare: 0.3 },
      },
    ],
    breakdowns: [
      {
        by: 'model',
        rows: [
          {
            key: 'claude-haiku-4-5',
            provider: 'claude',
            costShare: 0.6,
            tally: tally({ calls: 5, spentUsd: 2.4, inputTokens: 5000, outputTokens: 900 }),
          },
          {
            key: 'sonnet',
            provider: 'claude_cli',
            costShare: 0.4,
            tally: tally({ calls: 2, spentUsd: 1.6, reportedUsd: 1.6 }),
          },
        ],
      },
      {
        by: 'use_case',
        rows: [
          {
            key: 'screener-draft',
            provider: null,
            costShare: 1,
            tally: tally({ calls: 7, spentUsd: 4 }),
          },
        ],
      },
      {
        by: 'user',
        rows: [
          { key: null, provider: null, costShare: 1, tally: tally({ calls: 7, spentUsd: 4 }) },
        ],
      },
      {
        by: 'cost_basis',
        rows: [
          {
            key: 'price',
            provider: null,
            costShare: 0.6,
            tally: tally({ calls: 5, spentUsd: 2.4 }),
          },
          {
            key: 'reported',
            provider: null,
            costShare: 0.4,
            tally: tally({ calls: 2, spentUsd: 1.6, reportedUsd: 1.6 }),
          },
        ],
      },
      {
        by: 'outcome',
        rows: [
          { key: 'ok', provider: null, costShare: 1, tally: tally({ calls: 7, spentUsd: 4 }) },
        ],
      },
    ],
    daily: DAYS.map((day, i) => ({
      day,
      tally: tally({ calls: i, spentUsd: i / 2, inputTokens: i * 100, outputTokens: i * 10 }),
    })),
    reliability: {
      attempts: 20,
      ok: 16,
      fellBack: 2,
      failed: 1,
      skippedBudget: 1,
      fallbackRate: 0.1,
      failureRate: 0.05,
    },
    recent: [
      call(),
      call({
        ts: '2026-10-08T13:00:00+00:00',
        provider: 'claude_cli',
        model: 'sonnet',
        inputTokens: null,
        outputTokens: null,
        costUsd: 0.5,
        costBasis: 'reported',
        useCase: 'regime',
        unknownFields: ['input_tokens', 'output_tokens'],
        unknown: NOT_REPORTED,
      }),
      call({
        ts: '2026-10-08T12:00:00+00:00',
        outcome: 'skipped_budget',
        costUsd: null,
        costBasis: 'unknown',
        inputTokens: null,
        outputTokens: null,
        unknownFields: ['input_tokens', 'output_tokens', 'cost_usd'],
        unknown: NOT_REPORTED,
      }),
    ],
    ...over,
  };
}

/** Today's spend is past the daily cap (share above 1) and no monthly cap is set. */
export function overBudget(): LlmUsage {
  const base = usage();
  return {
    ...base,
    budget: { ...base.budget, monthlyUsd: null },
    windows: base.windows.map((w) =>
      w.key === 'today' && w.cap
        ? { ...w, cap: { ...w.cap, usedShare: 1.35 }, tally: { ...w.tally, spentUsd: 1.35 } }
        : w.key === 'month' && w.cap
          ? { ...w, cap: { kind: 'monthly', limitUsd: null, usedShare: null } }
          : w,
    ),
  };
}

/** Nothing recorded yet, no caps set. */
export function emptyUsage(): LlmUsage {
  const base = usage();
  return {
    ...base,
    recorded: false,
    budget: { dailyUsd: null, monthlyUsd: null, over: 'free', reportedCallUsd: 0.25, error: null },
    windows: base.windows.map((w) => ({
      ...w,
      tally: tally(),
      cap: w.cap && { kind: w.cap.kind, limitUsd: null, usedShare: null },
    })),
    breakdowns: [],
    daily: [],
    reliability: {
      attempts: 0,
      ok: 0,
      fellBack: 0,
      failed: 0,
      skippedBudget: 0,
      fallbackRate: null,
      failureRate: null,
    },
    recent: [],
  };
}

/** The `i`th of the fixture's recent calls. */
export function callAt(i: number): UsageCall {
  const found = usage().recent[i];
  if (!found) throw new Error(`the fixture has no call ${String(i)}`);
  return found;
}
