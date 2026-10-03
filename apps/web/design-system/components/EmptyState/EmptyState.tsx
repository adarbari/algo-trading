/**
 * EmptyState: what to show when there is nothing to show yet: a short title saying what is
 * missing, one line on why or what to do, and an optional action ("Add a criterion"). Calm and
 * muted, never an illustration. `bordered` draws the dashed outline of a placeholder area (an
 * empty board, a tab not built yet); `compact` fits inside a table or a small panel.
 */
import type { ReactNode } from 'react';

import { Text } from '../../primitives/Text';
import { Icon, type IconName } from '../Icon';
import styles from './EmptyState.module.css';

export interface EmptyStateProps {
  /** What is missing ("No ideas for Mon 5 Oct"). */
  title: ReactNode;
  /** Why, or what to do next. */
  description?: ReactNode;
  /** One action (a Button), or a couple. */
  action?: ReactNode;
  /** A small glyph above the title (e.g. `search` for no matches, `filter`). */
  icon?: IconName;
  /** Dashed placeholder outline (default false). */
  bordered?: boolean;
  /** Less padding, left-aligned: inside tables and small panels. */
  compact?: boolean;
}

export function EmptyState({
  title,
  description,
  action,
  icon,
  bordered = false,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={styles.root}
      data-bordered={bordered || undefined}
      data-compact={compact || undefined}
    >
      {icon && <Icon name={icon} size="lg" tone="muted" />}
      <Text weight="medium">{title}</Text>
      {description && (
        <Text size="sm" tone="muted">
          {description}
        </Text>
      )}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
