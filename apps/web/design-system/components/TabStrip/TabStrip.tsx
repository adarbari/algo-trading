/**
 * TabStrip: a row of open items (documents, instruments, views) as pill tabs the user can close,
 * with the selected item's content in its panel. Controlled: the caller owns `value` and the
 * list. Arrow keys, Home and End move focus and select; Delete or Backspace closes the focused
 * tab (and focuses its neighbour; announced through aria-keyshortcuts); every tab also has a
 * close button for pointer and touch, hidden from the accessibility tree because a tab list may
 * hold only tabs. The
 * row scrolls sideways when the tabs do not fit, the selected one scrolled into view. For
 * switching between fixed views of one subject use Tabs.
 */
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

import { IconButton } from '../IconButton';
import styles from './TabStrip.module.css';

export interface TabStripItem {
  id: string;
  label: ReactNode;
  /** The close button's accessible name ("Close NVDA"); default "Close". */
  closeLabel?: string;
  /** Monospace label (symbols, ids). */
  mono?: boolean;
}

export interface TabStripProps {
  items: readonly TabStripItem[];
  /** The selected tab id (none selected when it names no item). */
  value: string | null;
  onChange: (id: string) => void;
  /** Called with the id of the tab to close; omit for tabs that cannot be closed. */
  onClose?: (id: string) => void;
  /** Accessible name of the tab list, e.g. "Open items". */
  label: string;
  /** The selected tab's content, rendered in its tabpanel. Omit to render the tab list only. */
  children?: ReactNode;
}

export function TabStrip({ items, value, onChange, onClose, label, children }: TabStripProps) {
  const base = useId();
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const tabId = (id: string) => `${base}-tab-${id}`;
  const panelId = `${base}-panel`;
  const selectedId = items.some((item) => item.id === value) ? value : null;

  useEffect(() => {
    if (!selectedId) return;
    const reveal = () =>
      refs.current.get(selectedId)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    reveal();
    // The web fonts change the tab widths when they arrive: reveal again so the selected tab is
    // in view whatever the order of the font and the first render.
    let live = true;
    void (document.fonts as FontFaceSet | undefined)?.ready.then(() => {
      if (live) reveal();
    });
    return () => {
      live = false;
    };
  }, [selectedId]);

  function select(id: string) {
    refs.current.get(id)?.focus();
    if (id !== value) onChange(id);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, id: string) {
    const at = items.findIndex((item) => item.id === id);
    const step = (by: number) => items[(at + by + items.length) % items.length];
    if ((event.key === 'Delete' || event.key === 'Backspace') && onClose) {
      event.preventDefault();
      const next = items[at + 1] ?? items[at - 1];
      onClose(id);
      if (next) refs.current.get(next.id)?.focus();
      return;
    }
    const target =
      event.key === 'ArrowRight'
        ? step(1)
        : event.key === 'ArrowLeft'
          ? step(-1)
          : event.key === 'Home'
            ? items[0]
            : event.key === 'End'
              ? items.at(-1)
              : undefined;
    if (!target) return;
    event.preventDefault();
    select(target.id);
  }

  const hasPanel = children !== undefined && selectedId !== null;
  return (
    <div className={styles.root}>
      <div className={styles.list} role="tablist" aria-label={label}>
        {items.map((item, index) => {
          const selected = item.id === selectedId;
          return (
            <div
              key={item.id}
              className={styles.item}
              role="presentation"
              data-selected={selected || undefined}
            >
              <button
                ref={(node) => {
                  if (node) refs.current.set(item.id, node);
                  else refs.current.delete(item.id);
                }}
                id={tabId(item.id)}
                type="button"
                role="tab"
                className={styles.tab}
                data-mono={item.mono || undefined}
                data-closable={onClose ? true : undefined}
                aria-keyshortcuts={onClose ? 'Delete' : undefined}
                aria-selected={selected}
                aria-controls={selected && hasPanel ? panelId : undefined}
                tabIndex={selected || (selectedId === null && index === 0) ? 0 : -1}
                onClick={() => {
                  select(item.id);
                }}
                onKeyDown={(event) => {
                  onKeyDown(event, item.id);
                }}
              >
                {item.label}
              </button>
              {onClose && (
                <span className={styles.close} aria-hidden="true">
                  <IconButton
                    icon="close"
                    size="sm"
                    label={item.closeLabel ?? 'Close'}
                    tabIndex={-1}
                    onClick={() => {
                      onClose(item.id);
                    }}
                  />
                </span>
              )}
            </div>
          );
        })}
      </div>
      {hasPanel && (
        <div
          className={styles.panel}
          role="tabpanel"
          id={panelId}
          aria-labelledby={selectedId ? tabId(selectedId) : undefined}
        >
          {children}
        </div>
      )}
    </div>
  );
}
