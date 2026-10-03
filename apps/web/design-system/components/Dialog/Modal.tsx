/**
 * Modal: the shared modal layer under Dialog and Drawer (internal; not exported from the
 * package). A portal over a dimmed backdrop; scroll locked behind it; focus moves into the panel,
 * stays there (Tab cycles) and returns to the element that opened it; Escape and a click on the
 * backdrop close it unless `dismissible` is false. Built on Floating UI's focus manager and
 * dismiss interaction. Lays out the panel: header (title, description, close button), a
 * scrolling body and an optional footer of actions.
 */
import {
  FloatingFocusManager,
  FloatingOverlay,
  FloatingPortal,
  useDismiss,
  useFloating,
  useInteractions,
} from '@floating-ui/react';
import { useCallback, useId, useRef, type ReactNode, type RefObject } from 'react';

import { Heading } from '../../primitives/Heading';
import { Text } from '../../primitives/Text';
import { IconButton } from '../IconButton';
import styles from './Dialog.module.css';

const TABBABLE =
  'input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

export interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
  /** `dialog` (centred) or `drawer` (a full-height sheet on one side). */
  kind: 'dialog' | 'drawer';
  side?: 'start' | 'end';
  size: 'sm' | 'md' | 'lg';
  dismissible: boolean;
  initialFocus?: RefObject<HTMLElement | null>;
  /** Extra class for the panel (the Drawer's own widths). */
  panelClassName?: string | undefined;
  children?: ReactNode;
}

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  footer,
  kind,
  side = 'end',
  size,
  dismissible,
  initialFocus,
  panelClassName,
  children,
}: ModalProps) {
  const id = useId();
  // Default first focus: the first control in the body (not the close button), else the panel.
  const firstFocus = useRef<HTMLElement | null>(null);
  const { refs, context } = useFloating({ open, onOpenChange });
  // Callback refs (not render-time reads of Floating UI's `refs` object).
  const setPanel = useCallback(
    (node: HTMLElement | null) => {
      refs.setFloating(node);
    },
    [refs],
  );
  const dismiss = useDismiss(context, {
    enabled: dismissible,
    outsidePressEvent: 'mousedown',
  });
  const { getFloatingProps } = useInteractions([dismiss]);
  if (!open) return null;
  return (
    <FloatingPortal>
      <FloatingOverlay lockScroll className={styles.overlay} data-kind={kind} data-side={side}>
        <div className={styles.backdrop} aria-hidden="true" />
        <FloatingFocusManager
          context={context}
          modal
          returnFocus
          initialFocus={initialFocus ?? firstFocus}
        >
          <div
            ref={setPanel}
            className={[styles.panel, panelClassName].filter(Boolean).join(' ')}
            role="dialog"
            aria-modal="true"
            aria-labelledby={`${id}-title`}
            aria-describedby={description ? `${id}-description` : undefined}
            data-kind={kind}
            data-side={side}
            data-size={size}
            tabIndex={-1}
            {...getFloatingProps()}
          >
            <div className={styles.header}>
              <div className={styles.titles}>
                <Heading level={2} size="lg" id={`${id}-title`}>
                  {title}
                </Heading>
                {description && (
                  <span id={`${id}-description`}>
                    <Text size="sm" tone="muted">
                      {description}
                    </Text>
                  </span>
                )}
              </div>
              <IconButton
                icon="close"
                label="Close"
                onClick={() => {
                  onOpenChange(false);
                }}
              />
            </div>
            <div
              className={styles.body}
              ref={(node) => {
                firstFocus.current =
                  node?.querySelector<HTMLElement>(TABBABLE) ??
                  node?.closest<HTMLElement>('[role="dialog"]') ??
                  null;
              }}
            >
              {children}
            </div>
            {footer && <div className={styles.footer}>{footer}</div>}
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  );
}
