/**
 * "Start here" of the setups library: the first three setups of the best verdict group, as tiles
 * that open the setup (its idea as the description, its verdict as a badge). Shown only while
 * the list is not filtered or searched, so a narrowed list is not preceded by unrelated tiles.
 */
import { Grid, Heading, LinkCard, Stack, StatusBadge } from '@algotrade/ui';

import { verdictLabel, verdictTone, type EdgeRow } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

const COUNT = 3;

export interface StartHereProps {
  /** The rows in the list's order (best verdict first). */
  rows: readonly EdgeRow[];
  /** The page's path to one setup. */
  hrefOf: (id: string) => string;
}

export function StartHere({ rows, hrefOf }: StartHereProps) {
  const picked = rows.slice(0, COUNT);
  if (picked.length === 0) return null;
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={2}>Start here</Heading>
        {termHelp('setups_start_here')}
      </Stack>
      <Grid columns={3} gap={3} collapse="md">
        {picked.map((row, index) => (
          <LinkCard
            key={row.id}
            href={hrefOf(row.id)}
            kicker={String(index + 1)}
            title={row.name}
            description={row.thesis}
            footer={
              <StatusBadge tone={verdictTone(row.summary.verdict)}>
                {verdictLabel(row.summary.verdict)}
              </StatusBadge>
            }
          />
        ))}
      </Grid>
    </Stack>
  );
}
