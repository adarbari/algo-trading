/**
 * A feature value as the read model serves it (GraphQL `FeatureValue`, ADR 0038): how it reads
 * (from the server's `info.format`, with the unit and dtype choosing digits and currency), and
 * what to say when it is UNKNOWN for the session (the server's reason, never a guess).
 */
import type { ValueFormat } from '@algotrade/ui';

import type { gqlTypes } from '@/shared/api';

export type FeatureFormatName = gqlTypes.FeatureFormat;

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
  /** Why it is not known (ADR 0056); `entities/availability` words it. */
  unknown?:
    | {
        code: gqlTypes.UnknownCode;
        reason?: gqlTypes.NullReason | null | undefined;
        kind: gqlTypes.UnavailableKind;
        guideTerm: string;
        kindText: string;
        cause?:
          | {
              links: readonly {
                level: gqlTypes.CauseLevel;
                subject: string;
                status: string;
                message: string;
                runId?: string | null | undefined;
              }[];
            }
          | null
          | undefined;
      }
    | null
    | undefined;
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
