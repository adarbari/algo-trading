/**
 * The field guide in the Builder: apply one of a field's guided intents to a criterion (the
 * one-click preset the drawer's "Use this" runs: op, value, mode, tolerance and on_miss as the
 * guide gives them, the id and field kept). Pure.
 */
import { guideTolerance, type GuideUse } from '@/entities/feature';
import type { Criterion, CriterionMode, MissDecision } from '@/entities/screen';

import { shapeOf } from './threshold';

const MODES: readonly CriterionMode[] = ['hard', 'soft', 'score'];
const MISSES: readonly MissDecision[] = ['WATCH', 'LIQUIDITY_RISK', 'EVENT_RISK'];

/** `criterion` set to `use`: the guide's operator, value, mode, tolerance and on_miss. */
export function applyGuideUse(criterion: Criterion, use: GuideUse): Criterion {
  const mode = MODES.find((m) => m === use.mode) ?? 'hard';
  const tolerance = guideTolerance(use);
  const onMiss = MISSES.find((m) => m === use.onMiss);
  return {
    ...criterion,
    op: use.op,
    value: shapeOf(use.op) === 'none' ? undefined : (use.value ?? undefined),
    mode,
    tolerance: mode === 'hard' ? undefined : tolerance,
    on_miss: mode === 'soft' ? onMiss : undefined,
  };
}
