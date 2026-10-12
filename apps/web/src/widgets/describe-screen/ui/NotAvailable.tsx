/**
 * The "Not available yet" group of the review: one "requested, not applied" card per feature the
 * sentence asked for that the catalogue lacks: the description, how hard it is to add (a badge),
 * the nearest fields we do have, and the trader's OWN history of asking for it (the server sends
 * only their own rows: never another trader's, never a count across users). Nothing here changes
 * the screen.
 */
import {
  Button,
  Divider,
  Mono,
  Panel,
  Stack,
  StatusBadge,
  Surface,
  Text,
  formatValue,
} from '@algotrade/ui';
import type { ReactNode } from 'react';

import { GuideHelp, termHelp } from '@/features/guide-help';
import {
  earlierAsk,
  feasibilityLabel,
  ownRequest,
  statusLabel,
  useMyFeatureRequests,
  type MissingFeature,
  type ScreenDraft,
} from '@/features/screener-describe';

export interface NotAvailableProps {
  missing: readonly MissingFeature[];
  /** The screen's "not covered" notes: saved with it, each removable. */
  notes: readonly string[];
  onRemoveNote: (note: string) => void;
  /** The help for a catalogue field named as the closest one (null: the Guide does not know it). */
  renderFieldHelp?: ((field: string) => ReactNode) | undefined;
}

/** How a draft names a missing feature: the catalogue key, else the proposed slug, else its words. */
export function missingKey(item: MissingFeature): string {
  return item.key ?? item.new_key_slug ?? item.span;
}

/**
 * What a redraft changed in the missing features the screen keeps as notes: the descriptions of
 * the ones the new draft no longer has (`gone`) and of the ones it adds (`added`), by their keys.
 */
export function missingDelta(
  prior: ScreenDraft,
  next: ScreenDraft,
): { gone: string[]; added: string[] } {
  const was = new Map((prior.missing ?? []).map((item) => [missingKey(item), item.description]));
  const now = new Map((next.missing ?? []).map((item) => [missingKey(item), item.description]));
  return {
    gone: [...was].filter(([key]) => !now.has(key)).map(([, description]) => description),
    added: [...now].filter(([key]) => !was.has(key)).map(([, description]) => description),
  };
}

export function MissingCard({
  item,
  mine,
  renderFieldHelp,
}: {
  item: MissingFeature;
  mine: Parameters<typeof earlierAsk>[1];
  renderFieldHelp: NotAvailableProps['renderFieldHelp'];
}) {
  const feasibility = feasibilityLabel(item.feasibility);
  const own = ownRequest(item, mine);
  const status = own ? statusLabel(own.status) : null;
  const before = earlierAsk(item, mine);
  return (
    <Surface tone="row" padding={3} radius="md">
      <Stack gap={2}>
        <Text weight="semibold">{item.description}</Text>
        <Stack direction="row" gap={2} align="center" wrap>
          <StatusBadge tone="neutral">Requested, not applied</StatusBadge>
          <GuideHelp entry={{ kind: 'term', id: 'describe_requested_not_applied' }} />
          <StatusBadge tone={feasibility.tone}>{feasibility.label}</StatusBadge>
          <GuideHelp entry={feasibility.help} />
          {status && (
            <>
              <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
              <GuideHelp entry={status.help} />
            </>
          )}
        </Stack>
        <Text size="sm" tone="muted">
          {item.why_needed}
        </Text>
        {item.closest.length > 0 && (
          <Stack direction="row" gap={1} align="center" wrap>
            <Text size="sm" tone="muted">
              Closest:
            </Text>
            {item.closest.map((field) => (
              <Stack key={field} direction="row" gap={1} align="center">
                <Mono size="sm">{field}</Mono>
                {renderFieldHelp?.(field)}
              </Stack>
            ))}
          </Stack>
        )}
        {before && (
          <Text size="sm" tone="muted">
            {`You asked for this before, on ${formatValue(before.firstAsked, { kind: 'date', style: 'short' }).text}`}
          </Text>
        )}
      </Stack>
    </Surface>
  );
}

/** The screen's "not covered" notes, each removable (nothing when there are none). */
export function NotCovered({
  notes,
  onRemoveNote,
}: {
  notes: readonly string[];
  onRemoveNote: (note: string) => void;
}) {
  if (notes.length === 0) return null;
  return (
    <Stack gap={2}>
      <Divider tone="soft" />
      <Stack direction="row" gap={1} align="center">
        <Text size="sm" weight="semibold">
          Not covered
        </Text>
        {termHelp('describe_not_covered')}
      </Stack>
      {notes.map((note) => (
        <Stack key={note} direction="row" gap={2} align="center" wrap>
          <Text size="sm">{note}</Text>
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Remove note: ${note}`}
            onClick={() => {
              onRemoveNote(note);
            }}
          >
            Remove
          </Button>
        </Stack>
      ))}
    </Stack>
  );
}

export function NotAvailable({ missing, notes, onRemoveNote, renderFieldHelp }: NotAvailableProps) {
  // The history is a nicety: a failed read leaves the cards without it.
  const history = useMyFeatureRequests(missing.length > 0);
  const mine = history.data ?? [];
  return (
    <Panel
      title="Not available yet"
      description="Requested, not applied: the screen runs without these"
      headingLevel={3}
      actions={termHelp('describe_not_available_yet')}
    >
      <Stack gap={3}>
        {missing.map((item) => (
          <MissingCard
            key={missingKey(item)}
            item={item}
            mine={mine}
            renderFieldHelp={renderFieldHelp}
          />
        ))}
        <NotCovered notes={notes} onRemoveNote={onRemoveNote} />
      </Stack>
    </Panel>
  );
}
