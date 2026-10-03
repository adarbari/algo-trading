/**
 * Stack: the layout primitive. Lays children out in a row or column with a token gap. Screens
 * lay out only through primitives (ADR 0025), so semantics (`as`) and spacing are props here.
 */
import type { AriaAttributes, ReactNode } from 'react';

import styles from './Stack.module.css';

export type StackGap = 0 | 1 | 2 | 3 | 4 | 6 | 8;
export type StackElement =
  'div' | 'section' | 'header' | 'footer' | 'main' | 'nav' | 'aside' | 'ul' | 'ol' | 'li';

export interface StackProps extends Pick<
  AriaAttributes,
  'aria-label' | 'aria-labelledby' | 'aria-busy'
> {
  /** Main axis. */
  direction?: 'row' | 'column';
  /** Space between children, a step of the 4 px scale. */
  gap?: StackGap;
  /** Inner padding, a step of the 4 px scale. */
  padding?: StackGap;
  align?: 'start' | 'center' | 'end' | 'stretch' | 'baseline';
  justify?: 'start' | 'center' | 'end' | 'between';
  wrap?: boolean;
  /** Grow to fill the parent stack's main axis. */
  grow?: boolean;
  /** The semantic element rendered (landmarks and lists). */
  as?: StackElement;
  children?: ReactNode;
}

export function Stack({
  direction = 'column',
  gap = 2,
  padding = 0,
  align = 'stretch',
  justify = 'start',
  wrap = false,
  grow = false,
  as: Element = 'div',
  children,
  ...aria
}: StackProps) {
  return (
    <Element
      className={styles.stack}
      data-direction={direction}
      data-gap={gap}
      data-padding={padding}
      data-align={align}
      data-justify={justify}
      data-wrap={wrap || undefined}
      data-grow={grow || undefined}
      {...aria}
    >
      {children}
    </Element>
  );
}
