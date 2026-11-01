/**
 * The account menu's Light / Dark / System choice (ADR 0085): a segmented control under a
 * "Theme" label with its Guide help button. A change applies at once and saves in the
 * background; a failed save keeps the choice for this session and says so.
 */
import { SegmentedControl, Stack, useToast } from '@algotrade/ui';

import {
  readDeviceTheme,
  useSaveTheme,
  useTheme,
  type ThemeChoice as Choice,
} from '@/entities/appearance';
import { Labelled } from '@/features/guide-help';

const OPTIONS = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
] as const satisfies readonly { value: Choice; label: string }[];

export function ThemeChoice() {
  const stored = useTheme(true);
  const save = useSaveTheme();
  const toast = useToast();
  return (
    <Stack gap={1}>
      <Labelled text="Theme" help="theme" />
      <SegmentedControl
        aria-label="Theme"
        size="sm"
        options={OPTIONS}
        value={stored ?? readDeviceTheme() ?? 'system'}
        onValueChange={(theme) => {
          save.mutate(theme, {
            onError: () => {
              toast.show({
                tone: 'warning',
                title: 'Theme not saved: it applies until you reload.',
              });
            },
          });
        }}
      />
    </Stack>
  );
}
