/** Catalogue features as picker options: name, what it means, its unit and kind, grouped. */
import type { ComboboxOption } from '@algotrade/ui';

import {
  featureGroup,
  featureTitle,
  featureMarks,
  unitLabel,
  type CatalogueFeature,
} from '@/entities/feature';

/** Reference facts that identify a row already (the ticker column shows them). */
const IDENTITY = new Set(['instrument.instrument_id', 'instrument.symbol', 'instrument.name']);

/** One option per feature not chosen yet; the description says what it is, in which unit. */
export function featureOptions(
  catalogue: readonly CatalogueFeature[],
  chosen: readonly string[],
): ComboboxOption[] {
  const taken = new Set(chosen);
  return catalogue
    .filter((f) => !taken.has(f.name) && !IDENTITY.has(f.name))
    .map((f) => {
      const unit = unitLabel(f.unit);
      const meta = [unit, f.kind].filter(Boolean).join(' · ');
      return {
        value: f.name,
        label: f.name,
        description: `${featureTitle(f.name)}: ${f.description}${meta ? ` (${meta})` : ''}`,
        badge: [f.kind, ...featureMarks(f)].join(' · '),
        group: featureGroup(f),
      };
    });
}
