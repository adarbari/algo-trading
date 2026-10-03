/**
 * Stack: one-dimensional flow layout. Lays children out in a row or column with a token gap;
 * `wrap` turns a row into a cluster (chips, toolbars). Screens lay out only through primitives
 * (ADR 0025), so semantics (`as`) and spacing are props here; padding is Box's job.
 */
import type { AriaAttributes, ReactNode } from 'react';

import type { Space } from '../../tokens';
import styles from './Stack.module.css';

export type StackElement =
  'div' | 'section' | 'header' | 'footer' | 'main' | 'nav' | 'aside' | 'ul' | 'ol' | 'li';

export interface StackProps extends Pick<
  AriaAttributes,
  'aria-label' | 'aria-labelledby' | 'aria-busy'
> {
  /** Main axis. */
  direction?: 'row' | 'column';
  /** Space between children, a step of the 4 px scale. */
  gap?: Space;
  /** Cross-axis alignment. */
  align?: 'start' | 'center' | 'end' | 'stretch' | 'baseline';
  /** Main-axis distribution. */
  justify?: 'start' | 'center' | 'end' | 'between';
  /** Wrap onto new lines when out of room (a cluster). */
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
