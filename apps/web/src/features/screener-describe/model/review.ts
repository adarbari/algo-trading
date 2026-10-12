/**
 * What the review panel shows of a draft answer, laid out for the design system: the criteria the
 * draft loaded (id and field of each row) and a proposed formula's dry run as the figures and
 * sample rows `FormulaPreview` takes. It formats what the server measured and adds nothing: the
 * dry run itself (rows, no-value rate, range, passing, sample) is the server's (ADR 0038). Pure.
 */
import { formatValue, type FormulaSample, type StatItem } from '@algotrade/ui';

import type { components } from '@/shared/api';

export type DraftFormula = components['schemas']['DraftFormula'];
export type ScreenDraft = components['schemas']['ScreenDraft'];

/** The most sample rows the card shows. */
export const SAMPLE_ROWS = 5;

/** The criteria of a draft document with the field each reads (a row with no field is skipped). */
export function appliedRows(
  document: Readonly<Record<string, unknown>>,
): { id: string; field: string }[] {
  const criteria = document['criteria'];
  if (typeof criteria !== 'object' || criteria === null) return [];
  return Object.entries(criteria as Record<string, unknown>).flatMap(([id, criterion]) => {
    const field: unknown =
      typeof criterion === 'object' && criterion !== null && 'field' in criterion
        ? criterion.field
        : null;
    return typeof field === 'string' ? [{ id, field }] : [];
  });
}

/** Does the draft hold any criterion at all? An answer with none is never loaded as the screen. */
export function hasCriteria(document: Readonly<Record<string, unknown>>): boolean {
  const criteria = document['criteria'];
  return typeof criteria === 'object' && criteria !== null && Object.keys(criteria).length > 0;
}

const NUMBER = { kind: 'number', digits: 3 } as const;
const COUNT = { kind: 'number', digits: 0 } as const;
const PERCENT = { kind: 'percent', digits: 1 } as const;

/** The inputs and the unit as one muted line. */
export function inputsLine(formula: DraftFormula): string {
  const inputs = formula.inputs.length > 0 ? `Inputs: ${formula.inputs.join(', ')}` : '';
  return [inputs, formula.unit].filter((part) => part !== '').join(' · ');
}

/** The dry run as the stat strip's figures (a figure the server did not measure is left out). */
export function dryRunStats(formula: DraftFormula): StatItem[] {
  const run = formula.dry_run;
  const stats: StatItem[] = [{ id: 'rows', label: 'Rows checked', value: run.rows, format: COUNT }];
  if (run.no_value_rate !== null) {
    stats.push({ id: 'none', label: 'No value', value: run.no_value_rate, format: PERCENT });
  }
  if (run.minimum !== null && run.maximum !== null) {
    stats.push({
      id: 'range',
      label: 'Range',
      value: `${formatValue(run.minimum, NUMBER).text} to ${formatValue(run.maximum, NUMBER).text}`,
    });
  }
  if (run.criterion_pass !== null) {
    stats.push({ id: 'pass', label: 'Passing', value: run.criterion_pass, format: COUNT });
  }
  return stats;
}

/** The sample rows the server ran the formula on, as the preview's table (a non-number is no value). */
export function sampleOf(formula: DraftFormula): FormulaSample {
  return {
    label: `${formula.name} sample rows`,
    labelHeader: 'Instrument',
    columns: [{ id: 'value', header: formula.name, format: NUMBER }],
    rows: formula.dry_run.sample.slice(0, SAMPLE_ROWS).map((row) => ({
      id: row.instrument_id,
      label: row.instrument_id,
      values: { value: typeof row.value === 'number' ? row.value : null },
    })),
  };
}
