/**
 * The panel's rows as the design system draws them. A known value reads with the server's
 * format; an UNKNOWN reads as the word for its kind (`unknownWord`) with the reason under it
 * and its Guide term button, whatever the kind (a LICENCE gap is shown, never dropped).
 */
import type { KeyValueItem, StatItem } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { unknownText, unknownWord } from '@/entities/availability';
import { factItem, isUnknown, type Values } from '@/entities/feature';

import type { RowSpec } from './sections';

/** A row's help: the field's Guide entry, and for a gap the kind's term. */
export interface RowHelp {
  field: (name: string) => ReactNode;
  term: (id: string) => ReactNode;
}

/** The row for one spec: the value, or the word for why it is not known. */
export function rowItem(
  values: Values,
  spec: RowSpec,
  help: RowHelp,
): KeyValueItem & { id: string } {
  const served = values.get(spec.name);
  const field = help.field(spec.name);
  if (served && !isUnknown(served)) {
    const item = factItem(values, spec);
    if (item) return { ...item, action: field };
  }
  const unknown = served?.unknown;
  return {
    id: spec.id,
    label: spec.label,
    value: unknownWord(unknown),
    hint: unknownText(unknown, served?.info.nullMeaning),
    action: (
      <>
        {field}
        {unknown ? help.term(unknown.guideTerm) : null}
      </>
    ),
  };
}

/** A headline cell for one spec: a gap names its Guide term beside the label. */
export function statItem(values: Values, spec: RowSpec, help: RowHelp): StatItem {
  const { id, label, value, format, hint } = rowItem(values, spec, {
    field: () => null,
    term: help.term,
  });
  const served = values.get(spec.name);
  const gap = !served || isUnknown(served) ? served?.unknown : null;
  return {
    id,
    label: gap ? (
      <>
        {label}
        {help.term(gap.guideTerm)}
      </>
    ) : (
      label
    ),
    value,
    ...(format ? { format } : {}),
    ...(hint ? { sub: hint } : {}),
  };
}
