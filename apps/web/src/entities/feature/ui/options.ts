/**
 * Catalogue features as picker options (`FeatureCombobox`): the columns a table can add
 * (name, what it means, unit and kind) and the fields a criterion or tie-break can name (the
 * guide's one-line summary, unit and licence), grouped by feature group.
 */
import type { ComboboxOption } from '@algotrade/ui';

import { feature } from '@/shared/api';

import {
  featureGroup,
  featureLabel,
  featureMarks,
  featureTitle,
  isOwn,
  isPersonal,
  unitLabel,
  type CatalogueFeature,
} from '../model/catalogue';

/** Reference facts that identify a row already (the ticker column shows them). */
const IDENTITY = new Set<string>([
  feature('instrument.instrument_id'),
  feature('instrument.symbol'),
  feature('instrument.name'),
]);

/** One option per feature not chosen yet; the description says what it is, in which unit. */
export function columnOptions(
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

/** One option per feature, as a field to name: the guide's summary, unit, licence; formulas badged. */
export function fieldOptions(catalogue: readonly CatalogueFeature[]): ComboboxOption[] {
  return catalogue.map((f) => {
    // The guide's one-line summary says what the field is for; the catalogue text is the fallback.
    const parts = [f.guide?.summary || f.description, unitLabel(f.unit)];
    if (isPersonal(f)) parts.push('personal licence');
    const badge = isOwn(f) ? 'yours' : f.name.startsWith('feature.') ? 'formula' : null;
    return {
      value: f.name,
      label: f.name,
      // The closed input reads as a name, not the long dotted id (that is its tooltip).
      inputLabel: featureLabel(f.name),
      description: parts.filter(Boolean).join(' · '),
      ...(badge ? { badge } : {}),
      group: featureGroup(f),
    };
  });
}
