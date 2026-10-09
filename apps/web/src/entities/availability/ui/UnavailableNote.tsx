/**
 * What a response leaves out and why (ADR 0056): one banner per public kind, the features it
 * affects listed under the kind's title with the kind's Guide term one click away. Where the
 * server sent a cause chain (an admin; it sends none to anyone else) each chain is drawn under
 * its banner. Nothing here knows the role: it draws what it is given. Collapsed it is one line
 * (the count of fields left out and the first reason, from the server's words); a click opens the
 * banners.
 */
import { Banner, CauseChain, NoticeLine, Stack } from '@algotrade/ui';

import { useTermHelp } from '../model/help';
import { groupByKind } from '../model/group';
import { KIND_TITLE } from '../model/kinds';
import type { ServedUnavailable } from '../model/served';

/** `rollup.iv30@v1.iv30` -> `Iv30`: the column part of a catalogue name, in words. */
function featureName(name: string): string {
  const words = name.slice(name.lastIndexOf('.') + 1).replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export interface UnavailableNoteProps {
  /** The `unavailable` of a session, table, result page or run. */
  gaps: readonly ServedUnavailable[];
  /** A catalogue name in words (the page passes `featureTitle`); default: its column, humanised. */
  titleOf?: (name: string) => string;
}

export function UnavailableNote({ gaps, titleOf = featureName }: UnavailableNoteProps) {
  const termHelp = useTermHelp();
  const groups = groupByKind(gaps);
  if (groups.length === 0) return null;
  const fields = new Set(groups.flatMap((group) => group.features)).size;
  const first = gaps.find((gap) => gap.kind === groups[0]?.kind);
  return (
    <NoticeLine
      label={`${String(fields)} unavailable`}
      summary={first ? first.kindText : undefined}
    >
      <Stack gap={2}>
        {groups.map((group) => (
          <Stack key={group.kind} gap={1}>
            <Banner
              tone="warning"
              title={KIND_TITLE[group.kind]}
              actions={termHelp(group.guideTerm)}
            >
              {group.features.map(titleOf).join(', ')}
            </Banner>
            {group.causes.map((cause, index) => (
              <CauseChain key={index} links={cause.links} />
            ))}
          </Stack>
        ))}
      </Stack>
    </NoticeLine>
  );
}
