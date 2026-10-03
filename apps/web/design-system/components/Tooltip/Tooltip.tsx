/**
 * Tooltip: a short description of a control, shown on hover (after a delay) and immediately on
 * keyboard focus; Escape hides it. The text is the trigger's accessible description: the
 * trigger is rendered through `children(props)` and receives `aria-describedby`, so it must be
 * focusable (a Button, IconButton, link). Never put essential information or interactive
 * content in a tooltip. Positioned with Floating UI above the trigger (flips when there is no
 * room); rendered in a portal.
 */
import {
  autoUpdate,
  flip,
  FloatingPortal,
  offset,
  shift,
  useDismiss,
  useFloating,
  useFocus,
  useHover,
  useInteractions,
  type Placement,
} from '@floating-ui/react';
import { useCallback, useId, useState, type ReactNode } from 'react';

import { duration, space } from '../../tokens';
import styles from './Tooltip.module.css';

/** What the trigger receives: spread it on the focusable element. */
export interface TooltipTriggerProps {
  'aria-describedby': string;
}

export interface TooltipProps {
  /** The tooltip text: one short sentence or a definition. */
  content: ReactNode;
  /** Renders the focusable trigger: `(p) => <IconButton {...p} ... />`. */
  children: (props: TooltipTriggerProps) => ReactNode;
  /** Side of the trigger; flips when there is no room. Default `top`. */
  placement?: 'top' | 'bottom' | 'start' | 'end';
  /** Hover delay before showing: `default` (base motion x 4: 600 ms) or `none`. */
  delay?: 'default' | 'none';
  /** Start open (stories and docs). */
  defaultOpen?: boolean;
}

const SIDE: Record<NonNullable<TooltipProps['placement']>, Placement> = {
  top: 'top',
  bottom: 'bottom',
  start: 'left',
  end: 'right',
};

export function Tooltip({
  content,
  children,
  placement = 'top',
  delay = 'default',
  defaultOpen = false,
}: TooltipProps) {
  const id = useId();
  const [open, setOpen] = useState(defaultOpen);
  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    placement: SIDE[placement],
    strategy: 'fixed',
    whileElementsMounted: autoUpdate,
    middleware: [offset(space[1]), flip({ padding: space[2] }), shift({ padding: space[2] })],
  });
  // Callback refs (not render-time reads of Floating UI's `refs` object).
  const setPanel = useCallback(
    (node: HTMLElement | null) => {
      refs.setFloating(node);
    },
    [refs],
  );
  const setAnchor = useCallback(
    (node: HTMLElement | null) => {
      refs.setReference(node);
    },
    [refs],
  );
  const hover = useHover(context, {
    move: false,
    delay: { open: delay === 'none' ? 0 : duration.base * 4, close: 0 },
  });
  const focus = useFocus(context);
  const dismiss = useDismiss(context);
  const { getReferenceProps, getFloatingProps } = useInteractions([hover, focus, dismiss]);

  return (
    <>
      <span ref={setAnchor} className={styles.anchor} {...getReferenceProps()}>
        {children({ 'aria-describedby': `${id}-tooltip` })}
      </span>
      <FloatingPortal>
        <div
          ref={setPanel}
          id={`${id}-tooltip`}
          role="tooltip"
          className={styles.tooltip}
          hidden={!open}
          style={floatingStyles}
          {...getFloatingProps()}
        >
          {content}
        </div>
      </FloatingPortal>
    </>
  );
}
