/**
 * Text: the typography primitive and the TEMPLATE for every design-system component (folder =
 * Name.tsx + Name.module.css + Name.stories.tsx + Name.test.tsx + index.ts + __screenshots__).
 * All text on a screen goes through it; size, weight and colour come only from tokens.
 */
import type { ReactNode } from 'react';

import styles from './Text.module.css';

export type TextVariant = 'title' | 'heading' | 'body' | 'label' | 'caption';
export type TextTone =
  'default' | 'muted' | 'accent' | 'positive' | 'negative' | 'warning' | 'up' | 'down';
export type TextElement = 'p' | 'span' | 'h1' | 'h2' | 'h3' | 'h4' | 'strong' | 'em' | 'code';

export interface TextProps {
  /** Typographic role; sets size, line height and weight. */
  variant?: TextVariant;
  tone?: TextTone;
  weight?: 'regular' | 'medium' | 'semibold';
  /** Monospace (symbols, codes, ids). */
  mono?: boolean;
  /** Right-aligned tabular figures for numeric columns. */
  numeric?: boolean;
  /** Single line with an ellipsis when too long. */
  truncate?: boolean;
  /** The semantic element; defaults to h1/h2 for title/heading, p for body, span otherwise. */
  as?: TextElement;
  children?: ReactNode;
}

const DEFAULT_ELEMENT: Record<TextVariant, TextElement> = {
  title: 'h1',
  heading: 'h2',
  body: 'p',
  label: 'span',
  caption: 'span',
};

export function Text({
  variant = 'body',
  tone = 'default',
  weight,
  mono = false,
  numeric = false,
  truncate = false,
  as,
  children,
}: TextProps) {
  const Element = as ?? DEFAULT_ELEMENT[variant];
  return (
    <Element
      className={styles.text}
      data-variant={variant}
      data-tone={tone}
      data-weight={weight}
      data-mono={mono || undefined}
      data-numeric={numeric || undefined}
      data-truncate={truncate || undefined}
    >
      {children}
    </Element>
  );
}
