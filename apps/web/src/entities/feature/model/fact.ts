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

function formatOf(spec: FactSpec, value: ServedValue): ValueFormat {
  const format = valueFormat(value.info);
  return spec.signed && format.kind === 'percent' ? { kind: 'delta', unit: 'percent' } : format;
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
