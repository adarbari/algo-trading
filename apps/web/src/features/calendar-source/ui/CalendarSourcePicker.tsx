/**
 * The calendar's source picker: the scope list, or the names a chosen screener's latest run
 * picked.
 */
import { Select } from '@algotrade/ui';

import { SCOPE_SOURCE } from '../model/use-calendar-source';

export interface CalendarSourcePickerProps {
  value: string;
  screeners: readonly string[];
  onChange: (value: string) => void;
}

export function CalendarSourcePicker({ value, screeners, onChange }: CalendarSourcePickerProps) {
  return (
    <Select
      aria-label="Names"
      size="sm"
      width="auto"
      value={value}
      onValueChange={onChange}
      options={[
        { value: SCOPE_SOURCE, label: 'Scope list' },
        ...screeners.map((id) => ({ value: id, label: `Screener: ${id}` })),
      ]}
    />
  );
}
