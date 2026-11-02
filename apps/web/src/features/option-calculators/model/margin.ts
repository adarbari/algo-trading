/**
 * The buying-power calculator's words from the server's figures: what is held in the chosen
 * account and in the other, the premium over it, the size against trading and the stress sentence.
 * Formatted, never derived.
 */
import { formatValue } from '@algotrade/ui';

import type { components } from '@/shared/api';

export type MarginPreview = components['schemas']['MarginPreview'];

/** Which account's figure leads. */
export type Account = 'cash' | 'margin';

const usd = (value: number) => formatValue(value, { kind: 'currency' }).text;
const pct = (value: number, digits: number) => formatValue(value, { kind: 'percent', digits }).text;

/** The headline figure of the chosen account and the other account's, each with its label. */
export function heldFigures(
  preview: MarginPreview,
  account: Account,
): { headline: { label: string; value: string }; other: { label: string; value: string } } {
  const cash = { label: 'Cash-secured would hold', value: usd(preview.cash_secured) };
  const margin = { label: 'Margin account would hold', value: usd(preview.margin_held) };
  return account === 'cash'
    ? {
        headline: { label: 'Cash or margin held', value: cash.value },
        other: margin,
      }
    : {
        headline: { label: 'Cash or margin held', value: margin.value },
        other: cash,
      };
}

/** The premium collected on all the contracts. */
export const premiumTotal = (preview: MarginPreview): string => usd(preview.premium_total);

/** `2.1% of what's held, for 28 days.` */
export function premiumLine(preview: MarginPreview, account: Account): string {
  const share = account === 'cash' ? preview.premium_over_cash : preview.premium_over_margin;
  const days = preview.days === 1 ? '1 day' : `${String(preview.days)} days`;
  return `${pct(share, 1)} of what's held, for ${days}`;
}

/** The size lines to show: each part the server could not state is left out. */
export function sizeLines(preview: MarginPreview): string[] {
  const lines: string[] = [];
  if (preview.volume_share !== null)
    lines.push(`${pct(preview.volume_share, 1)} of today's volume in this contract`);
  if (preview.open_interest_share !== null)
    lines.push(`${pct(preview.open_interest_share, 1)} of the open contracts at this strike`);
  return lines;
}

/** The names of the reference episodes the nightly stores a drawdown for. */
const EPISODE_LABELS: Readonly<Record<string, string>> = {
  covid_2020: 'Covid crash, early 2020',
  hikes_2022: 'Rate-hike bear market, 2022',
  tariffs_2025: 'Tariff shock, spring 2025',
};

/** `If ORBT fell like its worst stored episode (Covid crash, early 2020, -34%), this put would be ...` */
export function stressSentence(symbol: string, preview: MarginPreview): string | null {
  const stress = preview.stress;
  if (!stress) return null;
  const episode = EPISODE_LABELS[stress.episode] ?? stress.episode.replace(/_/g, ' ');
  const n = preview.contracts === 1 ? '1 contract' : `${String(preview.contracts)} contracts`;
  return (
    `If ${symbol} fell like its worst stored episode (${episode}, ${pct(stress.drop, 0)}), ` +
    `this put would be ${usd(stress.in_the_money)} in the money on ${n}, before the premium. ` +
    'Margin multiplies losses as well as returns.'
  );
}
