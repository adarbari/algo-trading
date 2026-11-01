/**
 * Section "When it fails" of a setup's page: how the verdict's basis did in each market regime
 * (calm, caution, stress, crisis), and under a disclosure by holding period. Each is its own
 * read, fetched when the section is reached.
 */
import { Disclosure, Heading, Stack } from '@algotrade/ui';
import { useState } from 'react';

import { termHelp } from '@/features/guide-help';

import { EdgeHorizons } from './EdgeHorizons';
import { EdgeRegimes } from './EdgeRegimes';

export interface SetupFailsProps {
  edgeId: string;
}

export function SetupFails({ edgeId }: SetupFailsProps) {
  const [open, setOpen] = useState(false);
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={2}>When it fails</Heading>
        {termHelp('setup_when_fails')}
      </Stack>
      <EdgeRegimes edgeId={edgeId} />
      <Disclosure label="By holding period" open={open} onOpenChange={setOpen}>
        {open && <EdgeHorizons edgeId={edgeId} />}
      </Disclosure>
    </Stack>
  );
}
