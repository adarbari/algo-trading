/** A run or step duration in seconds as people read it: `1h 21m`, `26m 0s`, `12s`, `0.3s`. */
import { formatValue } from '@algotrade/ui';

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return formatValue(null).text;
  }
  if (seconds < 10) return `${formatValue(seconds, { kind: 'number', digits: 1 }).text}s`;
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = whole % 60;
  if (hours > 0) return `${String(hours)}h ${String(minutes)}m`;
  if (minutes > 0) return `${String(minutes)}m ${String(rest)}s`;
  return `${String(rest)}s`;
}
