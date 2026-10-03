/**
 * Popover: a panel anchored to a trigger, opened by a click (a column picker, a filter editor,
 * a small menu of options). Non-modal by default: Escape or a click outside closes it and focus
 * returns to the trigger; `trapFocus` keeps Tab inside while it is open. The trigger is the
 * caller's control (usually a Button), rendered through `trigger(props)` so it gets the ref and
 * the `aria-expanded` / `aria-controls` / `aria-haspopup` wiring. Positioned with Floating UI
 * (flips and shifts to stay on screen, follows scrolling); rendered in a portal above the page.
 */
import {
  autoUpdate,
  flip,
  FloatingFocusManager,
  FloatingPortal,
  offset,
  shift,
  size as fitSize,
  useDismiss,
  useFloating,
  useInteractions,
  type Placement,
} from '@floating-ui/react';
import { useCallback, useId, useState, type ReactNode, type Ref } from 'react';

import { space } from '../../tokens';
import styles from './Popover.module.css';

/** Props the trigger element must receive (Button and IconButton accept all of them). */
export interface PopoverTriggerProps {
  ref: Ref<HTMLButtonElement>;
  'aria-expanded': boolean;
  'aria-controls': string | undefined;
  'aria-haspopup': 'dialog';
  onClick: () => void;
}

export type PopoverPlacement = 'bottom-start' | 'bottom-end' | 'top-start' | 'top-end' | 'bottom';

export interface PopoverProps {
  /** Renders the trigger with the props it needs: `trigger={(p) => <Button {...p}>Columns</Button>}`. */
  trigger: (props: PopoverTriggerProps) => ReactNode;
  /** Accessible name of the panel ("Columns", "Edit criterion"). */
  label: string;
  /** Controlled open state (pair with `onOpenChange`). */
  open?: boolean;
  /** Initial open state when uncontrolled. */
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Side and alignment against the trigger; flips when there is no room. Default `bottom-start`. */
  placement?: PopoverPlacement;
  /** `auto` (content width, at least the popover token), `wide` (a sidebar-wide list). */
  width?: 'auto' | 'wide';
  /** Inner padding: `default` or `none` (a list that draws its own rows). */
  padding?: 'default' | 'none';
  /** Keep keyboard focus inside the panel while it is open (a small form). */
  trapFocus?: boolean;
  children: ReactNode;
}

export function Popover({
  trigger,
  label,
  open,
  defaultOpen = false,
  onOpenChange,
  placement = 'bottom-start',
  width = 'auto',
  padding = 'default',
  trapFocus = false,
  children,
}: PopoverProps) {
  const id = useId();
  const [ownOpen, setOwnOpen] = useState(defaultOpen);
  const isOpen = open ?? ownOpen;
  const setOpen = (next: boolean) => {
    if (open === undefined) setOwnOpen(next);
    onOpenChange?.(next);
  };

  const { refs, floatingStyles, context } = useFloating({
    open: isOpen,
    onOpenChange: setOpen,
    placement: placement as Placement,
    strategy: 'fixed',
    whileElementsMounted: autoUpdate,
    middleware: [
      offset(space[1]),
      flip({ padding: space[2] }),
      shift({ padding: space[2] }),
      fitSize({
        padding: space[2],
        apply({ availableHeight, elements }) {
          elements.floating.style.setProperty('--popover-available-height', `${availableHeight}px`);
        },
      }),
    ],
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
  const dismiss = useDismiss(context);
  const { getFloatingProps } = useInteractions([dismiss]);

  return (
    <>
      {trigger({
        ref: setAnchor,
        'aria-expanded': isOpen,
        'aria-controls': isOpen ? `${id}-popover` : undefined,
        'aria-haspopup': 'dialog',
        onClick: () => {
          setOpen(!isOpen);
        },
      })}
      {isOpen && (
        <FloatingPortal>
          <FloatingFocusManager context={context} modal={trapFocus} returnFocus>
            <div
              ref={setPanel}
              id={`${id}-popover`}
              className={styles.popover}
              role="dialog"
              aria-label={label}
              data-width={width}
              data-padding={padding}
              style={floatingStyles}
              {...getFloatingProps()}
            >
              {children}
            </div>
          </FloatingFocusManager>
        </FloatingPortal>
      )}
    </>
  );
}
