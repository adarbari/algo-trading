/**
 * The DataTable column picker: a "Columns" button (with the shown count) that opens a Popover
 * listing every column with a Checkbox, its label and its description (from the feature
 * catalogue), so the user knows what a column means before adding it. Columns that cannot be
 * hidden are disabled. Escape or a click outside closes it and returns focus to the button.
 */
import { Button } from '../Button';
import { Checkbox } from '../Checkbox';
import { Popover } from '../Popover';
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
  const shown = columns.filter((c) => c.visible).length;
  return (
    <div className={styles.picker}>
      <Popover
        label="Columns"
        placement="bottom-end"
        width="wide"
        padding="none"
        trigger={(props) => (
          <Button {...props} size="sm" icon="columns">
            Columns{' '}
            <span className={styles.pickerCount}>
              {shown} of {columns.length}
            </span>
          </Button>
        )}
      >
        <div role="group" aria-label="Show columns">
          <ul className={styles.pickerList}>
            {columns.map((column) => (
              <li key={column.id} className={styles.pickerItem}>
                <Checkbox
                  label={column.header}
                  {...(column.description === undefined ? {} : { description: column.description })}
                  checked={column.visible}
                  disabled={!column.hideable}
                  onCheckedChange={(checked) => {
                    onToggle(column.id, checked);
                  }}
                />
              </li>
            ))}
          </ul>
        </div>
      </Popover>
    </div>
  );
}
