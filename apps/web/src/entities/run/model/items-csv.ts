/** A run's items as CSV (key, code, status): RFC 4180 quoting, one header row, LF line ends. */
import type { RunItem } from './types';

function field(value: string): string {
  return /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

export function itemsCsv(items: readonly RunItem[]): string {
  const rows = items.map((i) => [i.key, i.code, i.status].map(field).join(','));
  return ['key,code,status', ...rows].join('\n') + '\n';
}

/** The download's file name: `<run id>-items.csv` with unsafe characters replaced. */
export function itemsFileName(runId: string): string {
  return `${runId.replace(/[^\w.-]+/g, '_')}-items.csv`;
}
