/**
 * SortableList: an ordered list whose items the user reorders, by dragging an item's handle
 * (pointer) or from the keyboard: focus the handle, Space to grab, Up / Down to move, Space to
 * drop, Escape to cancel. Every move is announced through a live region. Controlled: `items`
 * in, `onReorder(newOrder)` out when a move is dropped. Items render arbitrary content through
 * `renderItem`. Use it for a priority order the user owns (rule priority, column order).
 */
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from 'react';

import { VisuallyHidden } from '../../primitives/VisuallyHidden';
import { Icon } from '../Icon';
import styles from './SortableList.module.css';

/** What `renderItem` learns about the item it draws. */
export interface SortableItemState {
  /** Zero-based position in the order currently shown (including a move in progress). */
  index: number;
  /** The item is being dragged with the pointer. */
  dragging: boolean;
  /** The item is grabbed with the keyboard. */
  grabbed: boolean;
}

export interface SortableListProps<T> {
  /** The items, in order (controlled). */
  items: readonly T[];
  /** A stable unique key per item. */
  getKey: (item: T) => string;
  /** Plain-text name of an item: the handle's accessible name and the move announcements. */
  getLabel: (item: T) => string;
  /** The content of one item (the handle is drawn by the list). */
  renderItem: (item: T, state: SortableItemState) => ReactNode;
  /** Called with the new order when a move is dropped (not for a cancelled or no-op move). */
  onReorder: (items: T[]) => void;
  /** Accessible name of the list ("Screener priority"). */
  label: string;
  /** Handles are inert; the order cannot change. */
  disabled?: boolean;
  /** Shown instead of the list when `items` is empty (an `EmptyState`). */
  empty?: ReactNode;
}

type Mode = 'pointer' | 'keyboard';

interface Move<T> {
  mode: Mode;
  key: string;
  from: number;
  order: T[];
}

function moved<T>(order: readonly T[], from: number, to: number): T[] {
  const next = [...order];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item as T);
  return next;
}

export function SortableList<T>({
  items,
  getKey,
  getLabel,
  renderItem,
  onReorder,
  label,
  disabled = false,
  empty,
}: SortableListProps<T>) {
  const hintId = useId();
  const [move, setMove] = useState<Move<T> | null>(null);
  const [message, setMessage] = useState('');
  const moveRef = useRef<Move<T> | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const handles = useRef(new Map<string, HTMLButtonElement>());
  const refocus = useRef(false);

  const update = useCallback((next: Move<T> | null) => {
    moveRef.current = next;
    setMove(next);
  }, []);

  const order = move?.order ?? items;
  const total = order.length;
  const position = (list: readonly T[], key: string) =>
    list.findIndex((item) => getKey(item) === key) + 1;
  const nameAt = (list: readonly T[], key: string) => {
    const item = list.find((candidate) => getKey(candidate) === key);
    return item === undefined ? '' : getLabel(item);
  };

  const finish = (commit: boolean) => {
    const current = moveRef.current;
    if (!current) return;
    update(null);
    const name = nameAt(current.order, current.key);
    if (!commit) {
      setMessage(
        `Reorder cancelled. ${name} is at position ${String(current.from + 1)} of ${String(total)}.`,
      );
      return;
    }
    const to = position(current.order, current.key);
    setMessage(`${name} dropped at position ${String(to)} of ${String(total)}.`);
    if (to !== current.from + 1) onReorder(current.order);
  };

  const shift = (key: string, to: number) => {
    const current = moveRef.current;
    if (!current) return;
    const at = current.order.findIndex((item) => getKey(item) === key);
    if (to < 0 || to >= current.order.length || to === at) return;
    refocus.current = current.mode === 'keyboard';
    update({ ...current, order: moved(current.order, at, to) });
    if (current.mode === 'keyboard') {
      setMessage(
        `${nameAt(current.order, key)} moved to position ${String(to + 1)} of ${String(total)}.`,
      );
    }
  };

  // A reorder moves DOM nodes, which can drop focus from a keyboard-grabbed handle.
  useLayoutEffect(() => {
    if (!refocus.current) return;
    refocus.current = false;
    const key = moveRef.current?.key;
    if (key !== undefined) handles.current.get(key)?.focus();
  });

  // A pointer drag follows the pointer anywhere on the page until released.
  const pointerKey = move?.mode === 'pointer' ? move.key : null;
  useEffect(() => {
    if (pointerKey === null) return;
    const onMove = (event: globalThis.PointerEvent) => {
      const rows = [...(listRef.current?.children ?? [])] as HTMLElement[];
      const others = rows.filter((row) => row.dataset['key'] !== pointerKey);
      const to = others.filter((row) => {
        const box = row.getBoundingClientRect();
        return box.top + box.height / 2 < event.clientY;
      }).length;
      shift(pointerKey, to);
    };
    const onUp = () => {
      finish(true);
    };
    const onCancel = () => {
      finish(false);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') finish(false);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onCancel);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onCancel);
      window.removeEventListener('keydown', onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- shift/finish read refs and props at call time
  }, [pointerKey]);

  const onPointerDown = (event: PointerEvent<HTMLButtonElement>, key: string, index: number) => {
    if (disabled || event.button !== 0 || moveRef.current) return;
    event.preventDefault();
    update({ mode: 'pointer', key, from: index, order: [...items] });
    setMessage(`Dragging ${nameAt(items, key)}.`);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, key: string, index: number) => {
    if (disabled) return;
    const current = moveRef.current;
    if (event.key === ' ') {
      event.preventDefault();
      if (current) finish(true);
      else {
        update({ mode: 'keyboard', key, from: index, order: [...items] });
        setMessage(
          `Grabbed ${nameAt(items, key)}, position ${String(index + 1)} of ${String(total)}. ` +
            'Up and Down arrows move it, Space drops it, Escape cancels.',
        );
      }
    } else if (current?.key === key && current.mode === 'keyboard') {
      const at = current.order.findIndex((item) => getKey(item) === key);
      if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
        event.preventDefault();
        shift(key, at + (event.key === 'ArrowUp' ? -1 : 1));
      } else if (event.key === 'Escape') {
        event.preventDefault();
        finish(false);
      }
    }
  };

  if (items.length === 0 && empty !== undefined) return <>{empty}</>;

  return (
    <div className={styles.root}>
      <ul ref={listRef} className={styles.list} aria-label={label}>
        {order.map((item, index) => {
          const key = getKey(item);
          const active = move?.key === key;
          return (
            <li
              key={key}
              className={styles.item}
              data-key={key}
              data-dragging={(active && move.mode === 'pointer') || undefined}
              data-grabbed={(active && move.mode === 'keyboard') || undefined}
              data-disabled={disabled || undefined}
            >
              <button
                type="button"
                className={styles.handle}
                ref={(node) => {
                  if (node) handles.current.set(key, node);
                  else handles.current.delete(key);
                }}
                aria-label={`Reorder ${getLabel(item)}`}
                aria-describedby={hintId}
                aria-pressed={active && move.mode === 'keyboard'}
                disabled={disabled}
                onPointerDown={(event) => {
                  onPointerDown(event, key, index);
                }}
                onKeyDown={(event) => {
                  onKeyDown(event, key, index);
                }}
                onKeyUp={(event) => {
                  if (event.key === ' ') event.preventDefault();
                }}
                onBlur={() => {
                  if (!refocus.current && moveRef.current?.mode === 'keyboard' && active)
                    finish(false);
                }}
              >
                <Icon name="drag-handle" size="md" />
              </button>
              <div className={styles.content}>
                {renderItem(item, {
                  index,
                  dragging: active && move.mode === 'pointer',
                  grabbed: active && move.mode === 'keyboard',
                })}
              </div>
            </li>
          );
        })}
      </ul>
      <VisuallyHidden id={hintId}>
        Press Space to grab, Up and Down arrows to move, Space to drop, Escape to cancel.
      </VisuallyHidden>
      <div aria-live="assertive" aria-atomic="true">
        <VisuallyHidden>{message}</VisuallyHidden>
      </div>
    </div>
  );
}
