/**
 * The catalogue grouped for browsing by the field guide's themes (Momentum and trend, Volatility,
 * ...): a field with no guide entry falls under "Other", listed last. Pure readers over the
 * catalogue the server serves; search matches names, titles, descriptions and the guide's text.
 */
import { featureTitle, type CatalogueFeature } from './catalogue';

/** Where a field with no field guide entry goes. */
export const OTHER_THEME = 'Other';

export interface GuideTheme {
  name: string;
  /** Fields in the theme (of those given). */
  count: number;
}

export function themeOf(feature: CatalogueFeature): string {
  return feature.guide?.theme ?? OTHER_THEME;
}

/** The themes in the order they first appear in the catalogue, "Other" last; each with its field count. */
export function guideThemes(catalogue: readonly CatalogueFeature[]): GuideTheme[] {
  const counts = new Map<string, number>();
  for (const feature of catalogue) {
    const theme = themeOf(feature);
    counts.set(theme, (counts.get(theme) ?? 0) + 1);
  }
  const named = [...counts].filter(([name]) => name !== OTHER_THEME);
  const other = counts.get(OTHER_THEME);
  return [...named, ...(other === undefined ? [] : [[OTHER_THEME, other] as const])].map(
    ([name, count]) => ({ name, count }),
  );
}

export function themeFields(
  catalogue: readonly CatalogueFeature[],
  theme: string,
): CatalogueFeature[] {
  return catalogue.filter((f) => themeOf(f) === theme);
}

/** The text a search looks in: name, title, description, how to read it, the intents and the caveats. */
function haystack(feature: CatalogueFeature): string {
  const guide = feature.guide;
  return [
    feature.name,
    featureTitle(feature.name),
    feature.description,
    guide?.reads,
    ...(guide?.uses.flatMap((u) => [u.intent, u.note]) ?? []),
    ...(guide?.caveats ?? []),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

/** The fields every word of `query` appears in (case-insensitive; an empty query keeps all). */
export function searchFields(
  catalogue: readonly CatalogueFeature[],
  query: string,
): CatalogueFeature[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...catalogue];
  return catalogue.filter((f) => {
    const text = haystack(f);
    return words.every((w) => text.includes(w));
  });
}

/** One line on what the field is: the guide's first sentence, else the definition's. */
export function shortMeaning(feature: CatalogueFeature): string {
  const text = (feature.guide?.reads ?? feature.description).trim();
  const end = text.search(/[.!?](\s|$)/);
  const sentence = end < 0 ? text : text.slice(0, end + 1);
  return sentence.length > 140 ? `${sentence.slice(0, 137).trimEnd()}…` : sentence;
}

/** The selection a URL asks for, made consistent with the catalogue: a known field decides its theme; else the theme (or the first), with its first field. */
export function resolveSelection(
  catalogue: readonly CatalogueFeature[],
  asked: { theme?: string | undefined; field?: string | undefined },
): { theme: string; field: CatalogueFeature | null } | null {
  const themes = guideThemes(catalogue);
  const named = catalogue.find((f) => f.name === asked.field);
  if (named) return { theme: themeOf(named), field: named };
  const theme = themes.find((t) => t.name === asked.theme)?.name ?? themes[0]?.name;
  if (theme === undefined) return null;
  return { theme, field: themeFields(catalogue, theme)[0] ?? null };
}
