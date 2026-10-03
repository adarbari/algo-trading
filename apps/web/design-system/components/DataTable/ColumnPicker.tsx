/**
 * The DataTable column picker: a "Columns" button that opens a panel listing every hideable
 * column with a checkbox, its label and its description (from the feature catalogue), so the
 * user knows what a column means before adding it. Escape or a click outside closes it and
 * returns focus to the button.
 */
import { useEffect, useId, useRef, useState } from 'react';

import styles from './DataTable.module.css';

export interface PickerColumn {
  id: string;
  header: string;
  description?: string;
  visible: boolean;
  hideable: boolean;
}

export interface ColumnPickerProps {
  columns: readonly PickerColumn[];
  onToggle: (id: string, visible: boolean) => void;
}

export function ColumnPicker({ columns, onToggle }: ColumnPickerProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const shown = columns.filter((c) => c.visible).length;

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event: PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={root} className={styles.picker}>
      {/* TODO(design system PR 2): use Button (variant quiet) once it has merged. */}
      <button
        ref={button}
        type="button"
        className={styles.pickerButton}
        aria-expanded={open}
        aria-controls={`${id}-columns`}
        onClick={() => {
          setOpen(!open);
        }}
      >
        Columns
        <span className={styles.pickerCount}>
          {shown} of {columns.length}
        </span>
      </button>
      <div
        id={`${id}-columns`}
        className={styles.pickerPanel}
        role="group"
        aria-label="Show columns"
        hidden={!open}
      >
        <ul className={styles.pickerList}>
          {columns.map((column) => (
            <li key={column.id} className={styles.pickerItem}>
              {/* TODO(design system PR 2): use Checkbox once it has merged. */}
              <input
                id={`${id}-${column.id}`}
                type="checkbox"
                className={styles.checkbox}
                checked={column.visible}
                disabled={!column.hideable}
                aria-describedby={column.description ? `${id}-${column.id}-desc` : undefined}
                onChange={(event) => {
                  onToggle(column.id, event.target.checked);
                }}
              />
              <label htmlFor={`${id}-${column.id}`} className={styles.pickerLabel}>
                {column.header}
              </label>
              {column.description && (
                <span id={`${id}-${column.id}-desc`} className={styles.pickerDescription}>
                  {column.description}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
