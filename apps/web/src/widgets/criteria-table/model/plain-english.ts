/**
 * The screen read back as a sentence ("In plain English"): the criteria that must hold, the ones
 * that tolerate a near miss, and the ones that only raise the score. Pure.
 */
import { featureLabel, type CatalogueFeature } from '@/entities/feature';
import type { Criterion } from '@/entities/screen';
import { operatorSymbol, scaleOf, shapeOf, toTyped } from '@/features/screener-builder';

/** 50_000_000 -> `50M`, 1_500_000_000 -> `1.5B`. */
function compact(n: number): string {
  const [divisor, unit] = Math.abs(n) >= 1e9 ? [1e9, 'B'] : [1e6, 'M'];
  return `${String(Number((n / divisor).toPrecision(4)))}${unit}`;
}

function valueText(value: unknown, feature: CatalogueFeature | undefined): string {
  const scale = scaleOf(feature);
  const one = (v: unknown): string => {
    if (typeof v !== 'number') return String(v);
    const typed = toTyped(v, scale);
    const big = scale.prefix === '$' && Math.abs(typed) >= 1e6;
    const text = big ? compact(typed) : String(typed);
    return `${scale.prefix ?? ''}${text}${scale.suffix ?? ''}`;
  };
  return Array.isArray(value) ? value.map(one).join(' and ') : one(value);
}

function clause(criterion: Criterion, feature: CatalogueFeature | undefined): string {
  const { label } = criterion;
  // A label that already reads as the whole condition ("IV30 >= 50%", "Price > $5") is the
  // clause; adding the operator and value again would say it twice ("IV30 >= 50% ≥ 50%").
  if (label !== undefined && /[<>=\d]/.test(label)) return label;
  const name = label ?? featureLabel(criterion.field);
  const shape = shapeOf(criterion.op);
  const op = operatorSymbol(criterion.op);
  if (shape === 'none') return `${name} ${criterion.op === 'is_null' ? 'is empty' : 'has a value'}`;
  if (shape === 'range') return `${name} is between ${valueText(criterion.value, feature)}`;
  if (shape === 'list') {
    return `${name} ${criterion.op === 'in' ? 'is one of' : 'is none of'} ${valueText(criterion.value, feature)}`;
  }
  return `${name} ${op} ${valueText(criterion.value, feature)}`;
}

const join = (parts: readonly string[]): string =>
  parts.length <= 1
    ? (parts[0] ?? '')
    : `${parts.slice(0, -1).join(', ')} and ${parts.at(-1) ?? ''}`;

/** "Find instruments in <universe> where A and B; a near miss on C is tolerated; D only raises the score." */
export function plainEnglish(
  criteria: readonly Criterion[],
  catalogue: readonly CatalogueFeature[],
  selection: string | null,
): string | null {
  const ready = criteria.filter(
    (c) => c.field !== '' && (c.value !== undefined || shapeOf(c.op) === 'none'),
  );
  if (ready.length === 0) return null;
  const text = (mode: Criterion['mode']) =>
    ready
      .filter((c) => c.mode === mode)
      .map((c) =>
        clause(
          c,
          catalogue.find((f) => f.name === c.field),
        ),
      );
  const hard = text('hard');
  const sentences = [
    `Find instruments${selection ? ` in ${selection}` : ''}${hard.length > 0 ? ` where ${join(hard)}` : ''}.`,
  ];
  const soft = text('soft');
  if (soft.length > 0) sentences.push(`A near miss on ${join(soft)} is tolerated and flagged.`);
  const score = text('score');
  if (score.length > 0)
    sentences.push(`Prefer ${join(score)}; missing these only lowers the score.`);
  return sentences.join(' ');
}
