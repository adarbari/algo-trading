/**
 * Dialog: a modal window for a short, focused task or a confirmation ("Delete screener?", "Save
 * as…"). Controlled (`open` + `onOpenChange`). A title (its accessible name), an optional
 * description, the body, and a footer of actions (the primary action last). Focus moves into the
 * dialog (the first focusable element, or `initialFocus`), Tab stays inside, and focus returns to
 * the opener on close; Escape, the close button and a click on the backdrop close it
 * (`dismissible={false}` for a step that must be answered). Page scroll is locked behind it.
 */
import type { ReactNode, RefObject } from 'react';

import { Modal } from './Modal';

export interface DialogProps {
  /** Shown (controlled). */
  open: boolean;
  /** Called with `false` on Escape, the close button or a backdrop click. */
  onOpenChange: (open: boolean) => void;
  /** The heading and accessible name ("Delete screener?"). */
  title: ReactNode;
  /** One line under the title; also the accessible description. */
  description?: ReactNode;
  /** Actions, primary last: `<Button>Cancel</Button><Button variant="primary">Delete</Button>`. */
  footer?: ReactNode;
  /** Width: `sm` (confirmations), `md` (default, a short form), `lg` (a table or a long form). */
  size?: 'sm' | 'md' | 'lg';
  /** Escape and backdrop clicks close it (default true). */
  dismissible?: boolean;
  /** The element focused on open; default the first focusable element. */
  initialFocus?: RefObject<HTMLElement | null>;
  children?: ReactNode;
}

export function Dialog({ size = 'md', dismissible = true, ...rest }: DialogProps) {
  return <Modal kind="dialog" size={size} dismissible={dismissible} {...rest} />;
}
