/**
 * The screen read back as a sentence ("In plain English"): the criteria that must hold, the ones
 * that tolerate a near miss, and the ones that only raise the score. Pure.
 */
import {
  featureLabel,
  operatorSymbol,
  scaleOf,
  shapeOf,
  toTyped,
  type CatalogueFeature,
} from '@/entities/feature';
import { groupText, type Criterion, type CriterionGroup } from '@/entities/screen';

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
  const name = featureLabel(criterion.field);
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

/**
 * "Find instruments where A and B; a near miss on C is tolerated; D only raises the score." A
 * group (ADR 0071) reads inside the sentence as its expression, "(A or B)", "not C",
 * "(A and B) or C", whatever the modes of its members. The screen's notes (what it does not
 * cover: data the trader asked for, not authored prose) end it as "Not covered: ...".
 */
export function plainEnglish(
  criteria: readonly Criterion[],
  catalogue: readonly CatalogueFeature[],
  notes: readonly string[] = [],
  groups: readonly CriterionGroup[] = [],
): string | null {
  const ready = criteria.filter(
    (c) => c.field !== '' && (c.value !== undefined || shapeOf(c.op) === 'none'),
  );
  const clauses = new Map(
    ready.map((c) => [
      c.id,
      clause(
        c,
        catalogue.find((f) => f.name === c.field),
      ),
    ]),
  );
  const byId = new Map(groups.map((g) => [g.id, g]));
  const nested = new Set(groups.flatMap((g) => g.members));
  const gates = groups
    .filter((g) => !nested.has(g.id))
    .flatMap((g) => {
      const text = groupText(g, (id) => clauses.get(id) ?? null, byId);
      return text === null ? [] : [{ text, compound: g.kind === 'any' }];
    });
  if (ready.length === 0) return null;
  const loose = ready.filter((c) => c.group === undefined);
  const text = (mode: Criterion['mode']) =>
    loose.filter((c) => c.mode === mode).map((c) => clauses.get(c.id) ?? '');
  const alone = gates.length === 1 && text('hard').length === 0;
  const hard = [
    ...text('hard'),
    ...gates.map((g) => (g.compound && !alone ? `(${g.text})` : g.text)),
  ];
  const sentences = [`Find instruments${hard.length > 0 ? ` where ${join(hard)}` : ''}.`];
  const soft = text('soft');
  if (soft.length > 0) sentences.push(`A near miss on ${join(soft)} is tolerated and flagged.`);
  const score = text('score');
  if (score.length > 0)
    sentences.push(`Prefer ${join(score)}; missing these only lowers the score.`);
  if (notes.length > 0) sentences.push(`Not covered: ${notes.join('; ')}.`);
  return sentences.join(' ');
}

/** A group's expression for a heading or a read-only row ("(A or B)" without outer parens). */
export function groupExpression(
  group: CriterionGroup,
  criteria: readonly Criterion[],
  catalogue: readonly CatalogueFeature[],
  groups: readonly CriterionGroup[],
): string {
  const byCriterion = new Map(criteria.map((c) => [c.id, c]));
  return (
    groupText(
      group,
      (id) => {
        const c = byCriterion.get(id);
        return c
          ? clause(
              c,
              catalogue.find((f) => f.name === c.field),
            )
          : null;
      },
      new Map(groups.map((g) => [g.id, g])),
    ) ?? ''
  );
}
