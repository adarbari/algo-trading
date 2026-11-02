/**
 * A setup's state as one chip (On, Off, Paused, Unknown; the server's value, ADR 0088 decision
 * 16), the same on the Setups library, a setup's page and an Ideas group. `help` is the caller's
 * Guide button for the state value (the entity never imports a feature); the server's reason is printed by the caller that has room for it.
 */
import { Stack, StatusBadge } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { setupStateLabel, setupStateTone, type ServedSetupState } from '../model/edges';

export interface SetupStateChipProps {
  /** The served state; null: the read gave none (nothing is drawn). */
  state: ServedSetupState | null | undefined;
  /** The Guide button that explains the state value. */
  help?: ReactNode;
}

export function SetupStateChip({ state, help }: SetupStateChipProps) {
  if (!state) return null;
  return (
    <Stack direction="row" gap={1} align="center">
      <StatusBadge tone={setupStateTone(state.state)}>{setupStateLabel(state.state)}</StatusBadge>
      {help}
    </Stack>
  );
}
