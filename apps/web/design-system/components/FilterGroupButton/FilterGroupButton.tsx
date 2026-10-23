/**
 * FilterGroupButton: one group of a filter bar ("Setup", "What changed") as a small button that
 * opens a popover holding that group's controls (`OptionList`, `RangeFilter`, `WindowFilter`,
 * `SegmentedControl`). While the group holds filters (`activeCount` above 0) the button is `selected` (the
 * accent border and shows the count as a badge. Keyboard: Enter / Space opens, Escape
 * closes and focus returns to the button; the popover is a dialog named by `label`.
 */
import { useState, type ReactNode } from 'react';

import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { Button } from '../Button';
import { Popover } from '../Popover';
import styles from './FilterGroupButton.module.css';

export interface FilterGroupButtonProps {
  /** The group's name ("Setup"): the button text and the popover's accessible name. */
  label: string;
  /** How many filters of the group are in force (0 or absent: none). */
  activeCount?: number;
  /** The word after the count in the accessible name ("active": "Setup, 2 active"). */
  activeLabel?: string;
  /** The popover body: the group's filter controls. */
  children: ReactNode;
  /** The popover starts open (a story's open state). */
  defaultOpen?: boolean;
}

export function FilterGroupButton({
  label,
  activeCount = 0,
  activeLabel = 'active',
  children,
  defaultOpen = false,
}: FilterGroupButtonProps) {
  const [open, setOpen] = useState(defaultOpen);
  const active = activeCount > 0;
  return (
    <span className={styles.root} data-active={active || undefined}>
      <Popover
        label={label}
        open={open}
        onOpenChange={setOpen}
        trapFocus
        trigger={(props) => (
          <Button {...props} size="sm" iconEnd="chevron-down" selected={active}>
            {label}
            {active && (
              <>
                <span className={styles.badge} aria-hidden="true">
                  {activeCount}
                </span>
                <VisuallyHidden>{`, ${activeCount} ${activeLabel}`}</VisuallyHidden>
              </>
            )}
          </Button>
        )}
      >
        {children}
      </Popover>
    </span>
  );
}
