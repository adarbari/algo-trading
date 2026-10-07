/**
 * HelpDrawer: a right-hand Drawer for one explanation (a field, a regime indicator, a glossary
 * term), opened from an InfoButton beside the thing it explains. Header: an optional mono
 * `eyebrow` (the catalogue name), the `title`, one muted `meta` line. Body: `HelpLead` (the
 * reading paragraph at a larger size) then titled `HelpSection`s, or a Skeleton / ErrorState
 * while it loads or fails. Footer: the `fullPage` slot (the app passes its router link; the
 * design system does not route) and an "Esc to close" hint. Modal like Drawer: Escape closes,
 * focus returns to the InfoButton.
 */
import type { ReactNode } from 'react';

import { Heading } from '../../primitives/Heading';
import { Stack } from '../../primitives/Stack';
import { Text } from '../../primitives/Text';
import { Drawer } from '../Drawer';
import styles from './HelpDrawer.module.css';

export interface HelpDrawerProps {
  /** Shown (controlled). */
  open: boolean;
  /** Called with `false` on Escape, the close button or a backdrop click. */
  onOpenChange: (open: boolean) => void;
  /** A mono line above the title: the catalogue name ("rollup.momentum@v1.rel_volume") or a section label. */
  eyebrow?: ReactNode;
  /** The heading and accessible name ("Relative volume"). */
  title: ReactNode;
  /** One muted line under the title: theme, unit, cadence. */
  meta?: ReactNode;
  /** `HelpLead` and `HelpSection`s, or a loading / error state. */
  children?: ReactNode;
  /** The "Open full page" link, passed by the app (its router link). */
  fullPage?: ReactNode;
}

export function HelpDrawer({
  open,
  onOpenChange,
  eyebrow,
  title,
  meta,
  children,
  fullPage,
}: HelpDrawerProps) {
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      eyebrow={eyebrow}
      title={title}
      description={meta}
      footer={
        <Stack direction="row" justify="between" align="center" grow>
          <span className={styles.fullPage}>{fullPage}</span>
          <Text size="sm" tone="muted">
            Esc to close
          </Text>
        </Stack>
      }
    >
      <Stack gap={5}>{children}</Stack>
    </Drawer>
  );
}

export interface HelpLeadProps {
  children: ReactNode;
}

/** The first paragraph of an explanation, at a larger reading size. */
export function HelpLead({ children }: HelpLeadProps) {
  return (
    <div className={styles.lead}>
      <Text as="p" size="xl">
        {children}
      </Text>
    </div>
  );
}

export interface HelpSectionProps {
  /** The section title ("Use it for", "When it lies"). */
  title: string;
  /** Its content: paragraphs, cards, a list. */
  children: ReactNode;
}

/** A titled section of an explanation. */
export function HelpSection({ title, children }: HelpSectionProps) {
  return (
    <Stack gap={2} as="section">
      <Heading level={3}>{title}</Heading>
      {children}
    </Stack>
  );
}
