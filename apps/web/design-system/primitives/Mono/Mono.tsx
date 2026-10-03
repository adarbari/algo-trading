/**
 * Mono: IBM Plex Mono for tickers, contract symbols, ids, hashes and code. `code` marks it up
 * as code; otherwise a span. Size, weight and tone as Text.
 */
import type { ReactNode } from 'react';

import type { FontSize, FontWeight } from '../../tokens';
import type { TextTone } from '../Text';
import styles from './Mono.module.css';

export interface MonoProps {
  size?: FontSize;
  weight?: Extract<FontWeight, 'regular' | 'medium'>;
  tone?: Extract<TextTone, 'default' | 'secondary' | 'muted' | 'accent' | 'inherit'>;
  /** Render as `<code>` (source, config keys) instead of a span (symbols). */
  code?: boolean;
  /** Single line with an ellipsis when too long. */
  truncate?: boolean;
  title?: string;
  children?: ReactNode;
}

export function Mono({
  size = 'base',
  weight = 'regular',
  tone = 'default',
  code = false,
  truncate = false,
  title,
  children,
}: MonoProps) {
  const Element = code ? 'code' : 'span';
  return (
    <Element
      className={styles.mono}
      data-size={size}
      data-weight={weight}
      data-tone={tone}
      data-truncate={truncate || undefined}
      title={title}
    >
      {children}
    </Element>
  );
}
