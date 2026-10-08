/**
 * What a response leaves out and why (ADR 0056): one banner per public kind, the features it
 * affects listed under the kind's title with the kind's Guide term one click away. Where the
 * server sent a cause chain (an admin; it sends none to anyone else) each chain is drawn under
 * its banner. Nothing here knows the role: it draws what it is given.
 */
import { Banner, CauseChain, Stack } from '@algotrade/ui';

import { featureTitle } from '@/entities/feature';

import { useTermHelp } from '../model/help';
import { groupByKind } from '../model/group';
import { KIND_TITLE } from '../model/kinds';
import type { ServedUnavailable } from '../model/served';

export interface UnavailableNoteProps {
  /** The `unavailable` of a session, table, result page or run. */
  gaps: readonly ServedUnavailable[];
}

export function UnavailableNote({ gaps }: UnavailableNoteProps) {
  const termHelp = useTermHelp();
  const groups = groupByKind(gaps);
  if (groups.length === 0) return null;
  return (
    <Stack gap={2}>
      {groups.map((group) => (
        <Stack key={group.kind} gap={1}>
          <Banner tone="warning" title={KIND_TITLE[group.kind]} actions={termHelp(group.guideTerm)}>
            {group.features.map(featureTitle).join(', ')}
          </Banner>
          {group.causes.map((cause, index) => (
            <CauseChain key={index} links={cause.links} />
          ))}
        </Stack>
      ))}
    </Stack>
  );
}
