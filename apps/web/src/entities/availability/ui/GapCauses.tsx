/**
 * The cause chains the server sent behind some gaps (ADR 0056), one `CauseChain` each, for a
 * place that already names the gap (a dataset row). It draws only what it is given: the server
 * withholds a chain from anyone but an admin, so a trader's gaps draw nothing here.
 */
import { CauseChain, Stack } from '@algotrade/ui';

import type { ServedUnavailable } from '../model/served';

export function GapCauses({ gaps }: { gaps: ReadonlyArray<Pick<ServedUnavailable, 'cause'>> }) {
  const causes = gaps.flatMap((gap) => (gap.cause ? [gap.cause] : []));
  if (causes.length === 0) return null;
  return (
    <Stack gap={1}>
      {causes.map((cause, index) => (
        <CauseChain key={index} links={cause.links} />
      ))}
    </Stack>
  );
}
