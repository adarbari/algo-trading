/**
 * One edge's frozen-period record for the screener as a block: the edge (a link to its page) with
 * its status, then the odds line, the holding period and when the frozen period began; the
 * server's words when the edge has no record yet. Never an exploratory run.
 */
import { Button, formatValue, OddsLine, Stack, StatusBadge, Text } from '@algotrade/ui';

import { unknownText } from '@/entities/availability';
import { statusLabel, statusTone, type ScreenerEdge } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

export interface EdgeRecordProps {
  edge: ScreenerEdge;
  onOpenEdge: (edgeId: string) => void;
  /** The figures only, under the line that already names the edge and its status. */
  compact?: boolean;
}

const date = (iso: string) => formatValue(iso, { kind: 'date' }).text;

export function EdgeRecord({ edge, onOpenEdge, compact = false }: EdgeRecordProps) {
  const { figures } = edge;
  return (
    <Stack gap={1}>
      {compact ? null : (
        <Stack direction="row" gap={2} align="center" wrap>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              onOpenEdge(edge.edgeId);
            }}
          >
            {edge.edgeName}
          </Button>
          {edge.status ? (
            <StatusBadge tone={statusTone(edge.status)}>{statusLabel(edge.status)}</StatusBadge>
          ) : null}
        </Stack>
      )}
      {figures ? (
        <OddsLine
          hitRate={figures.hitRate}
          baseRate={figures.baseRate}
          sessions={figures.trades}
          {...(figures.liftPts === null ? {} : { liftPts: figures.liftPts })}
          {...(figures.picks === null || compact ? {} : { picks: figures.picks })}
          info={termHelp('screener_track_record')}
        />
      ) : (
        <Text size="sm" tone="muted">
          {`No record yet: ${unknownText(edge.notRun)}`}
        </Text>
      )}
      {figures ? (
        <Text size="xs" tone="muted">
          {[
            `${String(figures.horizonSessions)}-session hold`,
            edge.frozenSince ? `frozen period since ${date(edge.frozenSince)}` : null,
            compact ? null : edge.runLabel,
          ]
            .filter(Boolean)
            .join(' · ')}
        </Text>
      ) : null}
    </Stack>
  );
}
