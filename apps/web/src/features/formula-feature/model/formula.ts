/** Naming and describing a formula feature (the API's rules: lowercase name, a unit from the feature units). Pure. */

/** A feature name the API accepts: lowercase letters, digits and underscores, starting with a letter. */
export const isFeatureName = (name: string): boolean => /^[a-z][a-z0-9_]*$/.test(name);

/** Units a formula may carry (the feature framework's units). */
export const UNITS = [
  'decimal',
  'pct_points',
  'ratio',
  'usd',
  'usd_per_share',
  'index_points',
  'shares',
  'count',
  'sessions',
  'days',
  'date',
  'flag',
  'category',
  'text',
] as const;

/** The unit a checked formula most likely has, from its type. */
export function guessUnit(dtype: string): (typeof UNITS)[number] {
  if (dtype === 'bool') return 'flag';
  if (dtype === 'date') return 'date';
  if (dtype === 'str') return 'category';
  return 'ratio';
}
