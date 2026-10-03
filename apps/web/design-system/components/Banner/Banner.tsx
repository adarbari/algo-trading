/**
 * Banner: a message across the top of a page or panel that stays until its cause is gone:
 * `info` (a note), `warning` (partial data, a degraded source) or `negative` (a failed run). The
 * tint, border and icon follow the status tokens, and the text always says the state (colour is
 * never the only signal). `asOf` makes it the stale-data notice: "Stale data · as of 2 Oct 2026"
 * in the warning tone. Optional actions and a dismiss button. A negative banner is announced as
 * an alert, the others as a status.
 */
import type { ReactNode } from 'react';

import { formatValue } from '../../format';
import { Text } from '../../primitives/Text';
import { Icon, type IconName } from '../Icon';
import { IconButton } from '../IconButton';
import styles from './Banner.module.css';

export type BannerTone = 'info' | 'warning' | 'negative';

export interface BannerProps {
  /** `info` (default), `warning` or `negative`; a stale-data banner defaults to `warning`. */
  tone?: BannerTone;
  /** A short bold lead ("Partial run"). */
  title?: ReactNode;
  /** The message: what happened and what it means for this screen. */
  children?: ReactNode;
  /** The stale-data notice: the date (ISO day or Date) the data shown is as of. */
  asOf?: string | Date;
  /** Buttons or a link on the end ("View run", "Retry"). */
  actions?: ReactNode;
  /** Adds a dismiss button. */
  onDismiss?: () => void;
}

const ICON: Record<BannerTone, IconName> = { info: 'info', warning: 'alert', negative: 'alert' };

export function Banner({ tone, title, children, asOf, actions, onDismiss }: BannerProps) {
  const resolved: BannerTone = tone ?? (asOf === undefined ? 'info' : 'warning');
  const lead =
    asOf === undefined ? (
      title
    ) : (
      <>
        {title ?? 'Stale data'} · as of {formatValue(asOf, { kind: 'date', style: 'short' }).text}
      </>
    );
  return (
    <div
      className={styles.banner}
      data-tone={resolved}
      role={resolved === 'negative' ? 'alert' : 'status'}
    >
      <span className={styles.icon}>
        <Icon name={ICON[resolved]} tone={resolved === 'info' ? 'info' : resolved} />
      </span>
      <div className={styles.text}>
        {lead !== undefined && <Text weight="semibold">{lead}</Text>}
        {children !== undefined && <Text tone="secondary">{children}</Text>}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
      {onDismiss && <IconButton icon="close" label="Dismiss" size="sm" onClick={onDismiss} />}
    </div>
  );
}
