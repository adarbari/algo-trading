/**
 * The range control of a regime history chart: All, 20y, 10y, 5y, 2y (a SegmentedControl); while
 * an episode's window is shown no preset is selected and its name is written beside the control.
 */
import { SegmentedControl, Stack, Text } from '@algotrade/ui';

import { RANGE_PRESETS, type RangePreset } from '@/entities/regime';

import { useRegimeRange } from '../model/range';

const OPTIONS = RANGE_PRESETS.map(({ value, label }) => ({ value, label }));

export function RegimeRangeControl({ session }: { session: string }) {
  const range = useRegimeRange(session);
  return (
    <Stack direction="row" gap={2} align="center" wrap>
      {range.windowName !== null && (
        <Text size="sm" tone="muted">{`Showing ${range.windowName}`}</Text>
      )}
      <SegmentedControl<RangePreset | 'window'>
        aria-label="Chart range"
        size="sm"
        options={OPTIONS}
        value={range.preset ?? 'window'}
        onValueChange={(value) => {
          if (value !== 'window') range.setPreset(value);
        }}
      />
    </Stack>
  );
}
