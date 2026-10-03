/**
 * Grid: two-dimensional layout. Columns are a count (equal tracks) or a named template token
 * (`label-value`, `main-aside`, `sidebar-start`, `sidebar-end`); `collapse` drops to one column
 * when the grid's own width is under a breakpoint token (a container query, so it works in a
 * side panel as well as on a page).
 */
import type { AriaAttributes, ReactNode } from 'react';

import type { Breakpoint, Space } from '../../tokens';
import styles from './Grid.module.css';

export type GridColumns =
  1 | 2 | 3 | 4 | 6 | 12 | 'label-value' | 'main-aside' | 'sidebar-start' | 'sidebar-end';
export type GridElement = 'div' | 'section' | 'ul' | 'ol' | 'dl';

export interface GridProps extends Pick<
  AriaAttributes,
  'aria-label' | 'aria-labelledby' | 'aria-busy'
> {
  /** A column count, or a template token (`label-value`: fixed label + value; `main-aside`: 3 : 2). */
  columns?: GridColumns;
  /** Space between cells, a step of the 4 px scale. */
  gap?: Space;
  /** Space between rows when it differs from `gap`. */
  rowGap?: Space;
  /** Cell alignment on the block axis. */
  align?: 'start' | 'center' | 'stretch' | 'baseline';
  /** One column when the grid is narrower than this breakpoint (sm 480, md 720, lg 960 px). */
  collapse?: 'none' | Breakpoint;
  /** The semantic element of the grid itself. */
  as?: GridElement;
  children?: ReactNode;
}

export function Grid({
  columns = 2,
  gap = 2,
  rowGap,
  align = 'stretch',
  collapse = 'none',
  as: Element = 'div',
  children,
  ...aria
}: GridProps) {
  const grid = (
    <Element
      className={styles.grid}
      data-columns={columns}
      data-gap={gap}
      data-row-gap={rowGap}
      data-align={align}
      data-collapse={collapse}
      {...aria}
    >
      {children}
    </Element>
  );
  if (collapse === 'none') return grid;
  return <div className={styles.container}>{grid}</div>;
}
