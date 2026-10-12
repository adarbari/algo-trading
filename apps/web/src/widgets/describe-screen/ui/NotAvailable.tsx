/**
 * The "Not available yet" group of the review: one "requested, not applied" card per feature the
 * sentence asked for that the catalogue lacks: the description, how hard it is to add (a badge),
 * the nearest fields we do have, and the trader's OWN history of asking for it (the server sends
 * only their own rows: never another trader's, never a count across users). Nothing here changes
 * the screen.
 */
import { Mono, Panel, Stack, StatusBadge, Surface, Text, formatValue } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { GuideHelp, termHelp } from '@/features/guide-help';
import {
  earlierAsk,
  feasibilityLabel,
  ownRequest,
  statusLabel,
  useMyFeatureRequests,
  type MissingFeature,
} from '@/features/screener-describe';

export interface NotAvailableProps {
  missing: readonly MissingFeature[];
  /** The help for a catalogue field named as the closest one (null: the Guide does not know it). */
  renderFieldHelp?: ((field: string) => ReactNode) | undefined;
}

function MissingCard({
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

export function NotAvailable({ missing, renderFieldHelp }: NotAvailableProps) {
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
            key={item.key ?? item.new_key_slug ?? item.span}
            item={item}
            mine={mine}
            renderFieldHelp={renderFieldHelp}
          />
        ))}
      </Stack>
    </Panel>
  );
}
