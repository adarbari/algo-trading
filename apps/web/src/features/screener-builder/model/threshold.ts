/**
 * What a criterion's operator and threshold look like for a field: the operators its type
 * allows, the shape of the threshold (none, one value, a range, a list), and how a stored
 * value reads in the field's unit (a fraction is typed as a percent). Pure.
 */
import { featureFormat, isNumericFeature, type CatalogueFeature } from '@/entities/feature';

export type FieldKind = 'number' | 'bool' | 'text' | 'date';
export type ThresholdShape = 'none' | 'single' | 'range' | 'list';

export interface OperatorOption {
  value: string;
  label: string;
}

const LABELS: Readonly<Record<string, string>> = {
  gt: '>  greater than',
  gte: '≥  at least',
  lt: '<  less than',
  lte: '≤  at most',
  eq: '=  equals',
  ne: '≠  not equal',
  between: 'between',
  in: 'in',
  not_in: 'not in',
  is_null: 'is empty',
  not_null: 'has a value',
};

const OPS: Readonly<Record<FieldKind, readonly string[]>> = {
  number: ['gte', 'gt', 'lte', 'lt', 'between', 'eq', 'ne', 'in', 'not_in', 'is_null', 'not_null'],
  date: ['gte', 'gt', 'lte', 'lt', 'between', 'eq', 'ne', 'is_null', 'not_null'],
  text: ['eq', 'ne', 'in', 'not_in', 'is_null', 'not_null'],
  bool: ['eq', 'ne', 'is_null', 'not_null'],
};

/** Ops that compare numerically: the only ones a tolerance applies to. */
const NUMERIC_OPS = ['gt', 'gte', 'lt', 'lte', 'between'];

export function fieldKind(feature: CatalogueFeature | undefined): FieldKind {
  if (!feature) return 'number';
  if (isNumericFeature(feature)) return 'number';
  if (feature.dtype === 'bool') return 'bool';
  if (feature.dtype === 'date') return 'date';
  return 'text';
}

export function operatorsFor(kind: FieldKind): OperatorOption[] {
  return OPS[kind].map((value) => ({ value, label: LABELS[value] ?? value }));
}

/** The short symbol of an operator for a sentence ("≥"). */
export function operatorSymbol(op: string): string {
  return (LABELS[op] ?? op).split('  ')[0] ?? op;
}

export function shapeOf(op: string): ThresholdShape {
  if (op === 'is_null' || op === 'not_null') return 'none';
  if (op === 'between') return 'range';
  if (op === 'in' || op === 'not_in') return 'list';
  return 'single';
}

/** A tolerance applies to numeric comparisons of a number field. */
export function allowsTolerance(op: string, kind: FieldKind): boolean {
  return kind === 'number' && NUMERIC_OPS.includes(op);
}

/** The operator kept when the field changes type, else the kind's first. */
export function opFor(kind: FieldKind, op: string): string {
  return OPS[kind].includes(op) ? op : (OPS[kind][0] ?? 'eq');
}

/** A threshold that fits the shape and kind: the old one where it still does, else empty. */
export function coerceValue(op: string, kind: FieldKind, value: unknown): unknown {
  const shape = shapeOf(op);
  if (shape === 'none') return undefined;
  const fits = (v: unknown) =>
    kind === 'number'
      ? typeof v === 'number'
      : kind === 'bool'
        ? typeof v === 'boolean'
        : typeof v === 'string';
  if (shape === 'single') return fits(value) ? value : kind === 'bool' ? true : undefined;
  if (shape === 'range') {
    return Array.isArray(value) && value.length === 2 && value.every(fits) ? value : undefined;
  }
  if (Array.isArray(value)) return value.every(fits) ? value : undefined;
  return fits(value) ? [value] : undefined;
}

/** How a number is typed for a field: its unit's scale, prefix, suffix and step. */
export interface NumberScale {
  /** Typed value = stored value x factor (a fraction is typed as a percent). */
  factor: number;
  prefix?: string;
  suffix?: string;
  step: number;
}

export function scaleOf(feature: CatalogueFeature | undefined): NumberScale {
  const format = featureFormat(feature);
  switch (feature?.unit) {
    case 'decimal':
      return { factor: 100, suffix: '%', step: 1 };
    case 'pct_points':
      return { factor: 1, suffix: 'pts', step: 0.5 };
    case 'usd':
    case 'usd_per_share':
      return { factor: 1, prefix: '$', step: format.kind === 'currency-compact' ? 1_000_000 : 0.5 };
    case 'ratio':
      return { factor: 1, suffix: '×', step: 0.05 };
    case 'days':
    case 'sessions':
      return { factor: 1, suffix: feature.unit, step: 1 };
    default:
      return { factor: 1, step: feature?.dtype.startsWith('int') ? 1 : 0.1 };
  }
}

/** The float noise a scaled value picks up (0.07 x 100) removed. */
const tidy = (n: number): number => Number(n.toPrecision(12));

export const toTyped = (stored: number, scale: NumberScale): number => tidy(stored * scale.factor);
export const toStored = (typed: number, scale: NumberScale): number => tidy(typed / scale.factor);

/** A list typed as text ("HIGH, LOW") -> its values (numbers for a number field). */
export function parseList(text: string, kind: FieldKind): (string | number)[] | undefined {
  const parts = text
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return undefined;
  if (kind !== 'number') return parts;
  const numbers = parts.map(Number);
  return numbers.every(Number.isFinite) ? numbers : undefined;
}

/** A tolerance's unit: an absolute amount, or a share of the threshold. */
export type ToleranceUnit = 'absolute' | 'relative';
