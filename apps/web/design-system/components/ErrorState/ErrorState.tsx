/**
 * ErrorState: something failed to load. Says what failed in plain words, optionally a detail
 * line (an error code or the server's message, in mono) and a Retry button that shows a
 * spinner while `retrying`. Announced as an alert. For a whole panel or section; a failed field
 * uses Field's error text.
 */
import type { ReactNode } from 'react';

import { Text } from '../../primitives/Text';
import { Button } from '../Button';
import { Icon } from '../Icon';
import styles from './ErrorState.module.css';

export interface ErrorStateProps {
  /** What failed, in plain words ("The preview could not run."). */
  title?: ReactNode;
  /** Why, or what to try. */
  message?: ReactNode;
  /** Technical detail (status, error id) in mono. */
  detail?: ReactNode;
  /** Adds a Retry button. */
  onRetry?: () => void;
  /** The retry is in flight: the button shows a spinner and ignores clicks. */
  retrying?: boolean;
  /** Less padding, left-aligned: inside tables and small panels. */
  compact?: boolean;
}

export function ErrorState({
  title = 'Something went wrong.',
  message,
  detail,
  onRetry,
  retrying = false,
  compact = false,
}: ErrorStateProps) {
  return (
    <div className={styles.root} role="alert" data-compact={compact || undefined}>
      <div className={styles.title}>
        <Icon name="alert" tone="negative" />
        <Text weight="medium" tone="negative">
          {title}
        </Text>
      </div>
      {message && <Text tone="secondary">{message}</Text>}
      {detail && (
        <Text size="xs" tone="muted" mono>
          {detail}
        </Text>
      )}
      {onRetry && (
        <div className={styles.action}>
          <Button size="sm" icon="refresh" loading={retrying} onClick={onRetry}>
            Retry
          </Button>
        </div>
      )}
    </div>
  );
}
