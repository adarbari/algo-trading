/**
 * ShowMore: the control under a list that loads in pages. It says how far the list has come
 * ("Showing 50 of 312", a polite live region) and offers the next page; while it loads the
 * button is busy, when it failed the line says so and the button retries, and when everything
 * is shown it is a line only. The caller owns the data: this renders what it is told and
 * calls `onMore`. Wraps under its own line on a narrow container; touch sizing from Button.
 */
import { Button } from '../Button';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import styles from './ShowMore.module.css';

export interface ShowMoreProps {
  /** How many rows the list shows now. */
  shown: number;
  /** How many rows exist in all (the server's count). */
  total: number;
  /** How many rows the next page adds at most (default 50: the button reads "Show 50 more"). */
  pageSize?: number;
  /** `idle` (default), `loading` (the next page is on its way) or `error` (it failed). */
  status?: 'idle' | 'loading' | 'error';
  /** Ask for the next page (also the retry after an error). */
  onMore: () => void;
}

export function ShowMore({ shown, total, pageSize = 50, status = 'idle', onMore }: ShowMoreProps) {
  const left = Math.max(total - shown, 0);
  const next = Math.min(pageSize, left);
  const line =
    status === 'error'
      ? `Showing ${shown} of ${total} · the next page failed to load`
      : left === 0
        ? `All ${total} shown`
        : `Showing ${shown} of ${total}`;
  return (
    <div className={styles.root}>
      <Stack direction="row" gap={3} align="center" wrap>
        <span className={styles.line} role="status" aria-live="polite">
          <Text size="sm" tone={status === 'error' ? 'negative' : 'muted'}>
            {line}
          </Text>
        </span>
        {left > 0 && (
          <Button size="sm" loading={status === 'loading'} onClick={onMore}>
            {status === 'error' ? 'Try again' : `Show ${next} more`}
          </Button>
        )}
      </Stack>
    </div>
  );
}
