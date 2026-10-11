/**
 * Why one thing is not known (ADR 0056): its public kind in a line with the kind's Guide term
 * one click away, and the cause chain under it when the server sent one (an admin only). Nothing
 * here knows the role: it draws what it is given.
 */
import { CauseChain, Stack, Text } from '@algotrade/ui';

import { useTermHelp } from '../model/help';
import type { ServedUnknown, UnavailableKindName } from '../model/served';
import { unknownText } from '../model/unknown';

export interface UnknownNoteProps {
  unknown: ServedUnknown;
  /** What a stored null of the field means, where the page has the field's catalogue entry. */
  nullMeaning?: string | null | undefined;
  /**
   * Words for a kind in the page's own subject, where the server's generic ones name another
   * ("not available for this instrument" on an edge's page). A reason the server explains stays.
   */
  kindWords?: Partial<Record<UnavailableKindName, string>>;
}

export function UnknownNote({ unknown, nullMeaning, kindWords }: UnknownNoteProps) {
  const termHelp = useTermHelp();
  return (
    <Stack gap={1}>
      <Stack direction="row" gap={1} align="center" wrap>
        <Text tone="secondary">
          {(unknown.code !== 'EXPLAINED' && kindWords?.[unknown.kind]) ||
            unknownText(unknown, nullMeaning)}
        </Text>
        {termHelp(unknown.guideTerm)}
      </Stack>
      {unknown.cause && unknown.cause.links.length > 0 ? (
        <CauseChain links={unknown.cause.links} />
      ) : null}
    </Stack>
  );
}
