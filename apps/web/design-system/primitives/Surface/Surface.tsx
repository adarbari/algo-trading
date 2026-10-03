/**
 * Surface: a background, a crisp 1 px border and a radius from tokens (never a shadow). The
 * base of panels, bars and wells; Panel (header, actions, states) builds on it. Padding as Box.
 */
import type { AriaAttributes, ReactNode } from 'react';

import type { Radius, Space } from '../../tokens';
import styles from './Surface.module.css';

export type SurfaceElement = 'div' | 'section' | 'header' | 'footer' | 'aside' | 'nav';
export type SurfaceTone = 'bg' | 'surface' | 'row' | 'accent';
export type SurfaceBorder = 'none' | 'all' | 'top' | 'bottom' | 'start' | 'end';

export interface SurfaceProps extends Pick<
  AriaAttributes,
  'aria-label' | 'aria-labelledby' | 'aria-busy'
> {
  as?: SurfaceElement;
  /** Background: `surface` (panels), `row` (wells, hover), `bg` (canvas), `accent` (selected). */
  tone?: SurfaceTone;
  /** Which sides carry the 1 px border. */
  border?: SurfaceBorder;
  /** Border colour: `default`, `soft` (inner dividers), `control`, `accent` (selected). */
  borderTone?: 'default' | 'soft' | 'control' | 'accent';
  /** sm 3 px (bars), md 4 px (controls), lg 6 px (panels). */
  radius?: Radius;
  padding?: Space;
  paddingX?: Space;
  paddingY?: Space;
  /** Grow to fill the parent Stack's main axis. */
  grow?: boolean;
  /** Clip children to the rounded corners. */
  clip?: boolean;
  id?: string;
  children?: ReactNode;
}

export function Surface({
  as: Element = 'div',
  tone = 'surface',
  border = 'all',
  borderTone = 'default',
  radius = 'lg',
  padding,
  paddingX,
  paddingY,
  grow = false,
  clip = false,
  children,
  ...rest
}: SurfaceProps) {
  return (
    <Element
      className={styles.surface}
      data-tone={tone}
      data-border={border}
      data-border-tone={borderTone}
      data-radius={radius}
      data-padding={padding}
      data-padding-x={paddingX}
      data-padding-y={paddingY}
      data-grow={grow || undefined}
      data-clip={clip || undefined}
      {...rest}
    >
      {children}
    </Element>
  );
}
