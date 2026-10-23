/**
 * Text: the typography primitive and the TEMPLATE for every design-system component (folder =
 * Name.tsx + Name.module.css + Name.stories.tsx + Name.test.tsx + index.ts + __screenshots__).
 * All running text on a screen goes through it (headings: Heading; codes: Mono); size, weight
 * and colour come only from tokens. Numbers are always tabular.
 */
import type { ReactNode } from 'react';

import type { FontSize, FontWeight } from '../../tokens';
import styles from './Text.module.css';

export type TextTone =
  | 'default'
  | 'secondary'
  | 'muted'
  | 'accent'
  | 'positive'
  | 'warning'
  | 'negative'
  | 'info'
  | 'up'
  | 'down'
  | 'inherit';
export type TextElement = 'span' | 'p' | 'strong' | 'em' | 'label' | 'time' | 'abbr';

export interface TextProps {
  /** Type-scale step: xs 11.5, sm 12, md 12.5, base 13 (default), lg 14, xl 16, 2xl 18, 3xl 22 px. */
  size?: FontSize;
  weight?: FontWeight;
  /** Colour role: `secondary` / `muted` for de-emphasis, status tones, `up` / `down` for price moves. */
  tone?: TextTone;
  /** Monospace (symbols, codes, ids). */
  mono?: boolean;
  /** A number in a column: right-aligned, tabular figures. */
  numeric?: boolean;
  /** Single line with an ellipsis when too long. */
  truncate?: boolean;
  /** The semantic element (`p` for paragraphs; `span` default). */
  as?: TextElement;
  /** Tooltip / full value for truncated text or abbreviations. */
  title?: string;
  children?: ReactNode;
}

export function Text({
  size = 'base',
  weight = 'regular',
  tone = 'default',
  mono = false,
  numeric = false,
  truncate = false,
  as: Element = 'span',
  title,
  children,
}: TextProps) {
  return (
    <Element
      className={styles.text}
      data-size={size}
      data-weight={weight}
      data-tone={tone}
      data-mono={mono || undefined}
      data-numeric={numeric || undefined}
      data-truncate={truncate || undefined}
      title={title}
    >
      {children}
    </Element>
  );
}
