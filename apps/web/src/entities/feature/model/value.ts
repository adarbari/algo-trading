/**
 * A feature value as the read model serves it (GraphQL `FeatureValue`, ADR 0038): how it reads
 * (from the server's `info.format`, with the unit and dtype choosing digits and currency), and
 * what to say when it is UNKNOWN for the session (the server's reason, never a guess).
 */
import type { ValueFormat } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

export type FeatureFormatName = gqlTypes.FeatureFormat;
export type UnknownCodeName = gqlTypes.UnknownCode;

/** The parts of `FeatureInfo` the formatting reads. */
export interface ServedInfo {
  format: FeatureFormatName;
  unit?: string | null | undefined;
  dtype?: string | undefined;
  nullMeaning?: string | undefined;
}

/** A `FeatureValue` as an operation selects it. */
export interface ServedValue {
  name: string;
  value?: unknown;
  unknown?: { code: UnknownCodeName; detail: string } | null | undefined;
  info: ServedInfo;
}

const numberDigits = (info: ServedInfo): number => {
  if (info.unit === 'ratio') return 2;
  if (info.unit === 'pct_points') return 1;
  return info.dtype?.startsWith('float') ? 2 : 0;
};

/** The design system's format for a served value. */
export function valueFormat(info: ServedInfo): ValueFormat {
  switch (info.format) {
    case 'PERCENT':
      return { kind: 'percent' };
    case 'CURRENCY':
      return { kind: 'currency' };
    case 'COMPACT':
      return info.unit === 'usd' ? { kind: 'currency-compact' } : { kind: 'compact' };
    case 'NUMBER':
      return { kind: 'number', digits: numberDigits(info) };
    case 'DATE':
      return { kind: 'date' };
    default:
      return { kind: 'text' };
  }
}

/** The value to hand a formatter: a flag reads Yes / No. */
export function shownValue(value: unknown): unknown {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return value;
}

/** True when the server has no value for the session (`unknown` says why). */
export function isUnknown(value: ServedValue | undefined): boolean {
  return value === undefined || value.value === null || value.value === undefined;
}

/**
 * What a cell with no value says (ADR 0042): "n/a" where the feature does not apply to the
 * instrument, "Illiquid" where the options are too thin to price, else "Unknown". The one place
 * the label is chosen; the server decides the code.
 */
export function unknownLabel(code: UnknownCodeName | null | undefined): string {
  if (code === 'NOT_APPLICABLE') return 'n/a';
  if (code === 'ILLIQUID') return 'Illiquid';
  return 'Unknown';
}

/**
 * Why a value is UNKNOWN, in words: the table had no partition for the session, the instrument
 * had no row, or what a stored null means for this feature (`info.nullMeaning`).
 */
export function unknownReason(value: ServedValue | undefined): string {
  const unknown = value?.unknown;
  if (!value || !unknown) return 'not known';
  if (unknown.code === 'NO_PARTITION') return `not stored for this session (${unknown.detail})`;
  if (unknown.code === 'NO_ROW' || unknown.code === 'NULL') {
    return codeReason(unknown.code, value.info.nullMeaning);
  }
  return unknown.detail;
}

/** Why a table cell is UNKNOWN, from its code alone (a table sends codes, not details). */
export function codeReason(
  code: UnknownCodeName | null,
  nullMeaning: string | null | undefined,
): string {
  switch (code) {
    case 'NO_PARTITION':
      return 'not stored for this session';
    case 'NO_ROW':
      return 'no row for this instrument in this session';
    case 'NULL':
      return nullMeaning || 'not known for this session';
    case 'NOT_APPLICABLE':
      return 'does not apply to this instrument (e.g. not optionable; an ETF, fund, preferred or blank-check company has no earnings)';
    case 'ILLIQUID':
      return 'options too thin to price: no near-the-money quote within the spread limit';
    case null:
      return 'not known';
    default:
      return code.toLowerCase().replace(/_/g, ' ');
  }
}
