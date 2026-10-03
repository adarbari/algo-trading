/** The chart window switch (3M / 1Y / 2Y / All), passed to a Chart as its toolbar. */
import { CHART_RANGES, SegmentedControl, type ChartRange } from '@algotrade/ui';

export interface RangeControlProps {
  value: ChartRange;
  onChange: (range: ChartRange) => void;
}

export function RangeControl({ value, onChange }: RangeControlProps) {
  return (
    <SegmentedControl<ChartRange>
      aria-label="Range"
      size="sm"
      options={CHART_RANGES.map((r) => ({ value: r, label: r }))}
      value={value}
      onValueChange={onChange}
    />
  );
}
