/**
 * What a Screeners row opens: its criteria, its decision counts for the session, the first few
 * hits and the actions. Mounted only while the row is open, so the hits load on demand.
 */
import { Button, Grid, Mono, Skeleton, Stack, Text, TextLink } from '@algotrade/ui';

import { ScreenerOdds } from '@/entities/edge';
import { playbookPath } from '@/entities/guide';
import {
  DEFAULT_DECISIONS,
  DecisionBadge,
  decisionLabel,
  orderedDecisions,
  useScreenerResults,
  type ScreenerRunSummary,
} from '@/entities/screen';

import type { ListRow } from '../model/rows';

/** How many hits the row shows; "View N hits" opens them all. */
export const TOP_HITS = 5;

export interface ScreenerDetailProps {
  row: ListRow;
  /** The row's run summary; undefined: none was served for it (a Python screener). */
  summary: ScreenerRunSummary | undefined;
  onOpen: (id: string) => void;
  onEdit: (id: string) => void;
  /** Ask to delete one of your screeners. */
  onDelete: (id: string) => void;
  /** Duplicate one of your screeners, or copy a preset to edit it. */
  onDuplicate: (row: ListRow) => void;
}

export function ScreenerDetail({
  row,
  summary,
  onOpen,
  onEdit,
  onDelete,
  onDuplicate,
}: ScreenerDetailProps) {
  const run = summary?.latestRun ?? null;
  const hits = useScreenerResults(
    row.id,
    { decisions: DEFAULT_DECISIONS, columns: [], size: TOP_HITS },
    Boolean(run),
  );
  const top = hits.data?.screener?.latestRun?.results.results ?? [];
  const decisions = orderedDecisions(run?.decisions ?? []);
  return (
    <Stack gap={3}>
      <Grid columns={2} gap={4} collapse="md">
        <Stack gap={1} as="ul" aria-label={`Criteria of ${row.id}`}>
          {(summary?.criteria ?? []).map((c) => (
            <Stack as="li" key={c.id} direction="row" gap={2} align="baseline">
              <Mono size="xs">{c.field}</Mono>
              <Text size="xs" tone="muted">
                {c.mode}
              </Text>
            </Stack>
          ))}
        </Stack>
        <Stack gap={1} as="ul" aria-label={`Decisions of ${row.id}`}>
          {decisions.map((d) => (
            <Stack as="li" key={d.decision} direction="row" gap={2} justify="between">
              <Text size="sm">{decisionLabel(d.decision)}</Text>
              <Mono size="sm">{String(d.count)}</Mono>
            </Stack>
          ))}
        </Stack>
      </Grid>
      <ScreenerOdds screenerId={row.id} />
      {run &&
        (hits.isPending ? (
          <Skeleton />
        ) : (
          <Stack gap={1} as="ul" aria-label={`Top hits of ${row.id}`}>
            {top.map((hit) => (
              <Stack as="li" key={hit.instrumentId} direction="row" gap={2} align="center">
                <Mono size="sm">{hit.instrument?.symbol ?? hit.instrumentId}</Mono>
                <DecisionBadge decision={hit.decision} />
              </Stack>
            ))}
          </Stack>
        ))}
      <Stack direction="row" gap={2} wrap>
        {run && row.rules && (
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              onOpen(row.id);
            }}
          >
            {`View ${String(run.picked)} hits`}
          </Button>
        )}
        {row.kind === 'mine' && (
          <Button
            size="sm"
            onClick={() => {
              onEdit(row.id);
            }}
          >
            Edit criteria
          </Button>
        )}
        {row.rules && (
          <Button
            size="sm"
            variant={row.kind === 'mine' ? 'ghost' : 'primary'}
            onClick={() => {
              onDuplicate(row);
            }}
          >
            {row.kind === 'mine' ? 'Duplicate' : 'Duplicate to edit'}
          </Button>
        )}
        {row.kind === 'preset' && row.rules && (
          <TextLink href={playbookPath(row.id)} icon="book" size="sm">
            Playbook
          </TextLink>
        )}
        {row.kind === 'mine' && (
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Delete ${row.id}`}
            onClick={() => {
              onDelete(row.id);
            }}
          >
            Delete
          </Button>
        )}
      </Stack>
    </Stack>
  );
}
