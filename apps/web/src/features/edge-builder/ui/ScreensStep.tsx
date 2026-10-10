/**
 * Step 2, Screens: which existing screens implement the edge. A screen decides which stocks
 * qualify and their order; each chosen one gets its own result. "Edit in Screen Builder" and
 * "+ New screen" open the Screen Builder and come back here.
 */
import { Button, Checkbox, EmptyState, Skeleton, Stack, Text } from '@algotrade/ui';
import { useMemo } from 'react';

import { ScreenerRecord } from '@/entities/edge';
import { useScreeners } from '@/entities/screen';

import type { StepProps } from './step';

export interface ScreensStepProps extends StepProps {
  /** Open the Screen Builder on this screen (null: a new one). */
  onOpenScreen: (id: string | null) => void;
}

export function ScreensStep({ draft, onChange, onOpenScreen }: ScreensStepProps) {
  const screeners = useScreeners();
  const ids = useMemo(
    () =>
      [...new Set([...(screeners.data ?? []).map((s) => s.configId), ...draft.screeners])].sort(),
    [screeners.data, draft.screeners],
  );
  const toggle = (id: string, on: boolean) => {
    onChange({
      screeners: on ? [...draft.screeners, id] : draft.screeners.filter((s) => s !== id),
    });
  };
  if (screeners.isPending) return <Skeleton lines={4} label="Loading screens…" />;
  return (
    <Stack gap={3}>
      {ids.length === 0 ? (
        <EmptyState compact title="No screens yet" />
      ) : (
        <Stack gap={2} as="ul" aria-label="Screens">
          {ids.map((id) => (
            <Stack as="li" key={id} direction="row" gap={3} align="start" justify="between" wrap>
              <Checkbox
                label={id}
                checked={draft.screeners.includes(id)}
                onCheckedChange={(on) => {
                  toggle(id, on);
                }}
                description={<ScreenerRecord screenerId={id} />}
              />
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  onOpenScreen(id);
                }}
              >
                {`Edit ${id} in Screen Builder`}
              </Button>
            </Stack>
          ))}
        </Stack>
      )}
      <Stack direction="row" gap={2} align="center" wrap>
        <Button
          variant="secondary"
          onClick={() => {
            onOpenScreen(null);
          }}
        >
          + New screen
        </Button>
        {draft.screeners.length === 0 && (
          <Text size="sm" tone="muted">
            Choose at least one screen.
          </Text>
        )}
      </Stack>
    </Stack>
  );
}
