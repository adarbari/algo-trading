/**
 * A fact as a KeyValue row: a catalogue feature's served value for the session, formatted with
 * the server's `info.format`, "Unknown" with the reason when the session has no partition for
 * it, nothing when it does not apply to the instrument. Shared by every panel that lists facts.
 */
import type { KeyValueItem, ValueFormat } from '@algotrade/ui';

import { unknownText } from '@/entities/availability';
import type { SiteFeature } from '@/shared/api';

import { isUnknown, shownValue, valueFormat, type ServedValue } from './value';

const UNKNOWN = 'Unknown';

/** The served values by catalogue name. */
export type Values = ReadonlyMap<string, ServedValue>;

export interface FactSpec {
  id: string;
  label: string;
  name: SiteFeature;
  /** A change: shown signed, with an up / down tone. */
  signed?: boolean;
}

/** A row with its stable id (a headline stat uses the same id). */
export type Fact = KeyValueItem & { id: string };

const DELTA_DIGITS: Readonly<Record<string, number>> = { currency: 2, compact: 0 };

function formatOf(spec: FactSpec, value: ServedValue): ValueFormat {
  const format = valueFormat(value.info);
  if (!spec.signed) return format;
  if (format.kind === 'percent') return { kind: 'delta', unit: 'percent' };
  // a value already in percentage points reads +3.2 pts, never scaled again
  if (value.info.unit === 'pct_points') return { kind: 'delta', unit: 'points', digits: 1 };
  const digits = format.kind === 'number' ? format.digits : DELTA_DIGITS[format.kind];
  return digits === undefined ? format : { kind: 'delta', unit: 'number', digits };
}

/** A fact's row: its value, "Unknown" with the reason when the session has no partition for
 * it, nothing when it does not apply to the instrument. */
export function factItem(values: Values, spec: FactSpec): Fact | null {
  const value = values.get(spec.name);
  if (!value) return null;
  if (isUnknown(value)) {
    if (value.unknown?.kind !== 'SYSTEM') return null;
    return {
      id: spec.id,
      label: spec.label,
      value: UNKNOWN,
      hint: unknownText(value.unknown, value.info.nullMeaning),
    };
  }
  return {
    id: spec.id,
    label: spec.label,
    value: shownValue(value.value) as string | number,
    format: formatOf(spec, value),
  };
}
