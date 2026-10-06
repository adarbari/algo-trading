/**
 * The field guide in the Builder: apply one of a field's guided intents to a criterion (the
 * one-click preset: op, value, mode, tolerance and on_miss as the guide gives them, the id and
 * field kept), and say a guided criterion in words in the field's unit ("≥ 10.0%", "soft, a
 * near miss within 3.0%"). Pure.
 */
import { formatValue } from '@algotrade/ui';

import {
  featureFormat,
  guideTolerance,
  guideValues,
  type CatalogueFeature,
  type GuideUse,
} from '@/entities/feature';
import type { Criterion, CriterionMode, MissDecision } from '@/entities/screen';

import { operatorSymbol, shapeOf } from './threshold';

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

function word(value: unknown, feature: CatalogueFeature): string {
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    const format = featureFormat(feature);
    // A whole number of points, sessions or counts reads without decimals ("30", not "30.0").
    const whole =
      format.kind === 'number' && Number.isInteger(value) ? { ...format, digits: 0 } : format;
    return formatValue(value, whole).text;
  }
  return String(value);
}

/** The criterion in words: "≥ 10.0%", "between $2.0B and $10.0B", "in HIGH, MEDIUM", "has a value". */
export function guideCriterionText(use: GuideUse, feature: CatalogueFeature): string {
  const values = guideValues(use).map((v) => word(v, feature));
  const shape = shapeOf(use.op);
  if (shape === 'none') return use.op === 'is_null' ? 'is empty' : 'has a value';
  if (shape === 'range') return `between ${values[0] ?? '?'} and ${values[1] ?? '?'}`;
  if (shape === 'list') return `${use.op === 'in' ? 'in' : 'not in'} ${values.join(', ')}`;
  return `${operatorSymbol(use.op)} ${values[0] ?? '?'}`;
}

/** The mode in words: "hard", "soft, a near miss within 5" / "within 20% of the threshold", "score". */
export function guideModeText(use: GuideUse, feature: CatalogueFeature): string {
  const tolerance = guideTolerance(use);
  const band =
    tolerance === undefined
      ? ''
      : typeof tolerance === 'number'
        ? `, a near miss within ${word(tolerance, feature)}`
        : `, a near miss within ${formatValue(tolerance.relative, { kind: 'percent', digits: 0 }).text} of the threshold`;
  const miss =
    use.mode === 'soft' && use.onMiss && use.onMiss !== 'WATCH' ? ` (${use.onMiss})` : '';
  return `${use.mode}${band}${miss}`;
}
