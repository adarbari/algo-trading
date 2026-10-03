/**
 * Tabs: switches between views of the same subject (Compare, Chart, Options, ...). A `tablist`
 * of underline tabs (the accent underline marks the selected one) and the selected view's
 * panel. Controlled: the caller owns `value`. Keyboard: Left / Right (wrapping), Home / End
 * move focus and select (automatic activation); only the selected tab is in the Tab order.
 */
import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

import styles from './Tabs.module.css';

export interface TabItem {
  id: string;
  label: ReactNode;
  /** A count after the label (e.g. screener hits). */
  count?: number;
  disabled?: boolean;
}

export interface TabsProps {
  items: readonly TabItem[];
  /** The selected tab id. */
  value: string;
  onChange: (id: string) => void;
  /** Accessible name of the tab list, e.g. "View". */
  label: string;
  /** The selected tab's content, rendered in its tabpanel. Omit to render the tab list only. */
  children?: ReactNode;
  /** Text size: `md` (default) or `sm` (dense toolbars). */
  size?: 'sm' | 'md';
}

export function Tabs({ items, value, onChange, label, children, size = 'md' }: TabsProps) {
  const base = useId();
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const enabled = items.filter((item) => !item.disabled);
  const tabId = (id: string) => `${base}-tab-${id}`;
  const panelId = `${base}-panel`;

  function select(id: string) {
    refs.current.get(id)?.focus();
    if (id !== value) onChange(id);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, id: string) {
    const at = enabled.findIndex((item) => item.id === id);
    const step = (by: number) => enabled[(at + by + enabled.length) % enabled.length];
    const target =
      event.key === 'ArrowRight'
        ? step(1)
        : event.key === 'ArrowLeft'
          ? step(-1)
          : event.key === 'Home'
            ? enabled[0]
            : event.key === 'End'
              ? enabled.at(-1)
              : undefined;
    if (!target) return;
    event.preventDefault();
    select(target.id);
  }

  const hasPanel = children !== undefined;
  return (
    <div className={styles.root}>
      <div className={styles.list} role="tablist" aria-label={label} data-size={size}>
        {items.map((item) => {
          const selected = item.id === value;
          return (
            <button
              key={item.id}
              ref={(node) => {
                if (node) refs.current.set(item.id, node);
                else refs.current.delete(item.id);
              }}
              id={tabId(item.id)}
              type="button"
              role="tab"
              className={styles.tab}
              aria-selected={selected}
              aria-controls={selected && hasPanel ? panelId : undefined}
              tabIndex={selected ? 0 : -1}
              disabled={item.disabled}
              onClick={() => {
                select(item.id);
              }}
              onKeyDown={(event) => {
                onKeyDown(event, item.id);
              }}
            >
              {item.label}
              {item.count !== undefined && (
                <>
                  {' '}
                  <span className={styles.count}>{item.count}</span>
                </>
              )}
            </button>
          );
        })}
      </div>
      {hasPanel && (
        <div className={styles.panel} role="tabpanel" id={panelId} aria-labelledby={tabId(value)}>
          {children}
        </div>
      )}
    </div>
  );
}
