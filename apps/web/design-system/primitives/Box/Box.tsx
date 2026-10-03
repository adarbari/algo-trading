/**
 * Box: a semantic block (section, header, main, nav, footer, aside, div) with token padding.
 * The neutral building block for page regions; colour and borders are Surface's job, flow
 * layout is Stack's and Grid's.
 */
import type { AriaAttributes, ReactNode } from 'react';

import type { Space } from '../../tokens';
import styles from './Box.module.css';

export type BoxElement = 'div' | 'section' | 'header' | 'main' | 'nav' | 'footer' | 'aside';

export interface BoxProps extends Pick<
  AriaAttributes,
  'aria-label' | 'aria-labelledby' | 'aria-busy' | 'aria-live'
> {
  /** The semantic element rendered (landmarks). */
  as?: BoxElement;
  /** Padding on all sides, a step of the 4 px scale. */
  padding?: Space;
  /** Horizontal padding (overrides `padding` inline). */
  paddingX?: Space;
  /** Vertical padding (overrides `padding` block). */
  paddingY?: Space;
  /** `page`: full width up to the page maximum, centred. */
  width?: 'auto' | 'page';
  /** Grow to fill the parent Stack's main axis. */
  grow?: boolean;
  /** Target of an `aria-labelledby` elsewhere. */
  id?: string;
  children?: ReactNode;
}

export function Box({
  as: Element = 'div',
  padding,
  paddingX,
  paddingY,
  width = 'auto',
  grow = false,
  children,
  ...rest
}: BoxProps) {
  return (
    <Element
      className={styles.box}
      data-padding={padding}
      data-padding-x={paddingX}
      data-padding-y={paddingY}
      data-width={width}
      data-grow={grow || undefined}
      {...rest}
    >
      {children}
    </Element>
  );
}
