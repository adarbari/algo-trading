/**
 * Panel: a bordered section of a screen, built on Surface. A header (title as a heading,
 * optional description, actions on the end: chips, buttons, a legend), a body, and an optional
 * footer note. `state` swaps the body for a calm loading, empty or error message (with Retry), so
 * every panel handles the four data states the same way. `flush` drops body padding for tables.
 */
import { useId, type ReactNode } from 'react';

import { Heading } from '../../primitives/Heading';
import { Stack } from '../../primitives/Stack';
import { Surface } from '../../primitives/Surface';
import { Text } from '../../primitives/Text';
import { Button } from '../Button';
import { Icon } from '../Icon';
import styles from './Panel.module.css';

export type PanelState = 'ready' | 'loading' | 'empty' | 'error';

export interface PanelProps {
  /** The panel's heading ("Criteria", "Top ideas · across all your screeners"). */
  title: ReactNode;
  /** Short context beside the title (muted). */
  description?: ReactNode;
  /** Controls on the header's end: chips, small buttons, a legend. */
  actions?: ReactNode;
  /** A muted note under the body (sources, caveats). */
  footer?: ReactNode;
  /** `ready` (default) shows children; `loading`, `empty` and `error` show a message instead. */
  state?: PanelState;
  /** What loads ("Loading ideas…"). */
  loadingLabel?: string;
  /** Shown when `state="empty"`: what is missing and what to do. */
  emptyMessage?: ReactNode;
  /** Shown when `state="error"`: what failed. */
  errorMessage?: ReactNode;
  /** Adds a Retry button to the error state. */
  onRetry?: () => void;
  /** Heading level in the page outline; 2 by default. */
  headingLevel?: 2 | 3;
  /** No body padding (a table or grid that runs edge to edge). */
  flush?: boolean;
  /** Body content when ready. */
  children?: ReactNode;
}

export function Panel({
  title,
  description,
  actions,
  footer,
  state = 'ready',
  loadingLabel = 'Loading…',
  emptyMessage = 'Nothing to show yet.',
  errorMessage = 'This panel could not load.',
  onRetry,
  headingLevel = 2,
  flush = false,
  children,
}: PanelProps) {
  const headingId = useId();
  return (
    <Surface as="section" aria-labelledby={headingId} aria-busy={state === 'loading' || undefined}>
      <div className={styles.header}>
        <div className={styles.titles}>
          <Heading level={headingLevel} id={headingId}>
            {title}
          </Heading>
          {description && (
            <Text size="sm" tone="muted">
              {description}
            </Text>
          )}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
      {state === 'ready' ? (
        <div className={styles.body} data-flush={flush || undefined}>
          {children}
        </div>
      ) : (
        <div className={styles.body} data-state={state}>
          {state === 'loading' && (
            <Stack direction="row" gap={2} align="center">
              <Icon name="spinner" spin tone="muted" />
              <Text tone="muted">{loadingLabel}</Text>
            </Stack>
          )}
          {state === 'empty' && <Text tone="muted">{emptyMessage}</Text>}
          {state === 'error' && (
            <Stack direction="row" gap={2} align="center" wrap>
              <Icon name="alert" tone="negative" />
              <Text tone="negative">{errorMessage}</Text>
              {onRetry && (
                <Button size="sm" icon="refresh" onClick={onRetry}>
                  Retry
                </Button>
              )}
            </Stack>
          )}
        </div>
      )}
      {footer && (
        <div className={styles.footer}>
          <Text size="sm" tone="muted">
            {footer}
          </Text>
        </div>
      )}
    </Surface>
  );
}
