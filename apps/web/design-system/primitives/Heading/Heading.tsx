/**
 * Heading: section titles h1-h4. The level is the document outline; the size follows it
 * (h1 page title 18 px, h2-h3 panel heading 13 px, h4 12 px, all semibold) unless `size`
 * overrides it. Working screens never use centred or oversized marketing headers.
 */
import type { ReactNode } from 'react';

import type { FontSize } from '../../tokens';
import styles from './Heading.module.css';

export type HeadingLevel = 1 | 2 | 3 | 4;

export interface HeadingProps {
  /** Outline level: h1 once per page, h2 per panel. */
  level: HeadingLevel;
  /** Override the size the level implies. */
  size?: Extract<FontSize, 'sm' | 'base' | 'lg' | 'xl' | '2xl' | '3xl'>;
  tone?: 'default' | 'muted';
  /** Single line with an ellipsis when too long. */
  truncate?: boolean;
  /** Target of a section's `aria-labelledby`. */
  id?: string;
  children?: ReactNode;
}

const LEVEL_SIZE: Record<HeadingLevel, NonNullable<HeadingProps['size']>> = {
  1: '2xl',
  2: 'base',
  3: 'base',
  4: 'sm',
};

export function Heading({
  level,
  size,
  tone = 'default',
  truncate = false,
  id,
  children,
}: HeadingProps) {
  const Element = `h${level}` as const;
  return (
    <Element
      className={styles.heading}
      data-size={size ?? LEVEL_SIZE[level]}
      data-tone={tone}
      data-truncate={truncate || undefined}
      id={id}
    >
      {children}
    </Element>
  );
}
