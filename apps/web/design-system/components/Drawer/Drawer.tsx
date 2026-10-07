/**
 * Drawer: a side sheet over the page for detail that keeps the screen behind it in context (a
 * ticker's detail from a table row, a run's log, filters on a phone). Modal like Dialog: focus
 * moves in, stays inside, and returns to the opener; Escape, the close button and a backdrop
 * click close it; page scroll is locked. Full height on the `end` (default) or `start` side;
 * `sm` / `md` / `lg` widths, never wider than the screen.
 */
import type { ReactNode, RefObject } from 'react';

import { Modal } from '../Dialog';
import styles from './Drawer.module.css';

export interface DrawerProps {
  /** Shown (controlled). */
  open: boolean;
  /** Called with `false` on Escape, the close button or a backdrop click. */
  onOpenChange: (open: boolean) => void;
  /** The heading and accessible name ("AAPL · Apple"). */
  title: ReactNode;
  /** A small mono line above the title (a catalogue name, a section label). */
  eyebrow?: ReactNode;
  /** One line under the title; also the accessible description. */
  description?: ReactNode;
  /** Actions pinned to the bottom of the sheet. */
  footer?: ReactNode;
  /** The side it slides in from: `end` (default) or `start`. */
  side?: 'start' | 'end';
  /** Width: `sm` (a sidebar), `md` (default), `lg`. */
  size?: 'sm' | 'md' | 'lg';
  /** Escape and backdrop clicks close it (default true). */
  dismissible?: boolean;
  /** The element focused on open; default the first focusable element. */
  initialFocus?: RefObject<HTMLElement | null>;
  children?: ReactNode;
}

const WIDTH = { sm: styles.widthSm, md: styles.widthMd, lg: styles.widthLg } as const;

export function Drawer({ side = 'end', size = 'md', dismissible = true, ...rest }: DrawerProps) {
  return (
    <Modal
      kind="drawer"
      side={side}
      size={size}
      dismissible={dismissible}
      panelClassName={WIDTH[size]}
      {...rest}
    />
  );
}
