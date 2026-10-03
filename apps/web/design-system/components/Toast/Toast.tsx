/**
 * Toast: a brief confirmation or failure after an action ("Screener saved", "Export failed"),
 * shown in the corner and gone after a few seconds. Tone icon + text (colour is never the only
 * signal), an optional action ("Undo", "View") and a dismiss button. Show toasts with
 * `useToast()` under a `ToastProvider` (mounted once by the app); `Toast` itself is the
 * presentational card the provider stacks. Negative toasts are announced as alerts and stay
 * until dismissed by default; the others as a status. Lasting problems belong in a Banner.
 */
import type { ReactNode } from 'react';

import { Text } from '../../primitives/Text';
import { Button } from '../Button';
import { Icon, type IconName } from '../Icon';
import { IconButton } from '../IconButton';
import styles from './Toast.module.css';

export type ToastTone = 'info' | 'positive' | 'warning' | 'negative';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastProps {
  /** `info` (default), `positive` (done), `warning` or `negative` (failed). */
  tone?: ToastTone;
  /** What happened, in a few words ("Screener saved"). */
  title: ReactNode;
  /** One more line of detail. */
  description?: ReactNode;
  /** One follow-up ("Undo", "View run"). */
  action?: ToastAction;
  /** Adds the dismiss button. */
  onDismiss?: () => void;
}

const ICON: Record<ToastTone, IconName> = {
  info: 'info',
  positive: 'check',
  warning: 'alert',
  negative: 'alert',
};

export function Toast({ tone = 'info', title, description, action, onDismiss }: ToastProps) {
  return (
    <div className={styles.toast} data-tone={tone} role={tone === 'negative' ? 'alert' : 'status'}>
      <span className={styles.icon}>
        <Icon name={ICON[tone]} tone={tone} />
      </span>
      <div className={styles.text}>
        <Text weight="medium">{title}</Text>
        {description !== undefined && (
          <Text size="sm" tone="muted">
            {description}
          </Text>
        )}
      </div>
      {action && (
        <Button size="sm" variant="ghost" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
      {onDismiss && <IconButton icon="close" label="Dismiss" size="sm" onClick={onDismiss} />}
    </div>
  );
}
