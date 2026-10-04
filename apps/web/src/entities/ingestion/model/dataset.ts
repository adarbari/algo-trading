/**
 * Dataset names as admins read them: the stored table (`bars/1d`,
 * `rollups/instrument/price_stats@v2`) becomes "Daily bars" or "Price stats (v2)".
 */
const NAMED: Record<string, string> = {
  'instruments/reference': 'Reference',
  universe: 'Universe',
  'bars/1d': 'Daily bars',
  'chains/option_quotes': 'Option chains',
};

const VERSIONED = /^(?<name>.+)@v(?<version>\d+)$/;

export function datasetLabel(dataset: string): string {
  const named = NAMED[dataset];
  if (named) return named;
  const last = dataset.split('/').at(-1) ?? dataset;
  const match = VERSIONED.exec(last);
  const base = (match?.groups?.['name'] ?? last).replace(/_/g, ' ');
  const words = base.replace(/\biv(\d*)\b/gi, (_, n: string) => `IV${n}`);
  const label = words.charAt(0).toUpperCase() + words.slice(1);
  return match?.groups?.['version'] ? `${label} (v${match.groups['version']})` : label;
}

/** Whether a dataset is the option chains (its drill-down shows the fetch tiers). */
export function isChains(dataset: string): boolean {
  return dataset.startsWith('chains/');
}
