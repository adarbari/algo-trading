/**
 * What a Screeners row opens, as labelled sections: its criteria (label and rule), today's run
 * (decision bar, new / dropped, paused, a notice when the run is partial or missing), the top
 * hits (each opens in Explore), its track record and the actions. Mounted only while the row is
 * open, so the hits load on demand.
 */
import {
  Button,
  formatValue,
  Grid,
  Heading,
  NoticeLine,
  Stack,
  StackedBar,
  Text,
} from '@algotrade/ui';
import { useId, type ReactNode } from 'react';

import {
  DEFAULT_DECISIONS,
  DecisionBadge,
  decisionLabel,
  orderedDecisions,
  useCriterionLines,
  useScreenerResults,
  type ScreenerRunSummary,
} from '@/entities/screen';

import { changesOf, decisionSegments } from '../model/summary';
import type { ListRow } from '../model/rows';
import { Facts } from './Facts';
import { RecordCard } from './RecordCard';

/** How many hits the row shows; "View N hits" opens them all. */
export const TOP_HITS = 5;

export interface ScreenerDetailProps {
  row: ListRow;
  /** The row's run summary; undefined: none was served for it (a Python screener). */
  summary: ScreenerRunSummary | undefined;
  onOpen: (id: string) => void;
  onEdit: (id: string) => void;
  /** Open a hit's ticker in Explore, arriving through this screener. */
  onOpenTicker: (symbol: string, via: string) => void;
  /** Open an edge's evidence. */
  onOpenEdge: (edgeId: string) => void;
  /** Ask to delete one of your screeners. */
  onDelete: (id: string) => void;
  /** Duplicate one of your screeners, or copy a preset to edit it. */
  onDuplicate: (row: ListRow) => void;
  /** The link to the preset's playbook, made by the list (a preset's row only). */
  playbook?: ReactNode;
}

function CriteriaFacts({
  screenerId,
  criteria,
}: {
  screenerId: string;
  criteria: ScreenerRunSummary['criteria'] | undefined;
}) {
  const { lines, isPending } = useCriterionLines(criteria);
  return (
    <Facts
      label={`Criteria of ${screenerId}`}
      loading={isPending}
      emptyMessage="No criteria."
      facts={lines.map((line) => ({
        id: line.id,
        label: line.label,
        value: (
          <>
            {line.rule}{' '}
            <Text as="span" size="xs" tone="muted">
              {line.mode}
            </Text>
          </>
        ),
      }))}
    />
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <Stack as="section" gap={2} aria-labelledby={id}>
      <Heading level={3} size="sm" tone="muted" id={id}>
        {title}
      </Heading>
      {children}
    </Stack>
  );
}

export function ScreenerDetail({
  row,
  summary,
  onOpen,
  onEdit,
  onOpenTicker,
  onOpenEdge,
  onDelete,
  onDuplicate,
  playbook,
}: ScreenerDetailProps) {
  const run = summary?.latestRun ?? null;
  const hits = useScreenerResults(
    row.id,
    { decisions: DEFAULT_DECISIONS, columns: [], size: TOP_HITS },
    Boolean(run),
  );
  const served = hits.data?.screener?.latestRun ?? null;
  const top = served?.results.results ?? [];
  const decisions = orderedDecisions(run?.decisions ?? []);
  const changes = changesOf(run?.changes ?? []);
  const partial = served?.status === 'partial' || served?.coverage === 'PARTIAL';
  return (
    <Stack gap={4}>
      <Section title="Actions">
        <Stack direction="row" gap={2} align="center" wrap>
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
              variant={row.kind === 'mine' ? 'ghost' : 'secondary'}
              onClick={() => {
                onDuplicate(row);
              }}
            >
              {row.kind === 'mine' ? 'Duplicate' : 'Duplicate to edit'}
            </Button>
          )}
          {row.kind === 'preset' && row.rules && playbook}
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
      </Section>
      <Grid columns={2} gap={5} collapse="md">
        <Section title="Criteria">
          {row.rules ? <CriteriaFacts screenerId={row.id} criteria={summary?.criteria} /> : null}
        </Section>
        <Section title="Today">
          {run ? (
            <Stack gap={2}>
              {partial && (
                <NoticeLine label="Partial run" summary={served.unavailable[0]?.kindText} />
              )}
              <StackedBar
                label={`Decisions of ${row.id}`}
                size="sm"
                segments={decisionSegments(run.decisions)}
                emptyMessage="No picks"
              />
              <Facts
                label={`Decision counts of ${row.id}`}
                facts={[
                  ...decisions.map((d) => ({
                    id: d.decision,
                    label: decisionLabel(d.decision),
                    value: formatValue(d.count, { kind: 'number' }).text,
                  })),
                  ...(changes
                    ? [
                        {
                          id: 'changes',
                          label: 'New / dropped',
                          value: `+${String(changes.added)} / −${String(changes.dropped)}`,
                        },
                      ]
                    : []),
                  ...(run.paused > 0
                    ? [{ id: 'paused', label: 'Paused', value: String(run.paused) }]
                    : []),
                ]}
              />
            </Stack>
          ) : (
            <NoticeLine tone="neutral" label="Not run" summary={summary?.notRun?.kindText} />
          )}
        </Section>
        <Section title="Top hits">
          {!run ? (
            <Text size="sm" tone="muted">
              None
            </Text>
          ) : hits.isPending ? (
            <Text size="sm" tone="muted">
              Loading…
            </Text>
          ) : (
            <Stack gap={2} as="ul" aria-label={`Top hits of ${row.id}`}>
              {top.map((hit) => {
                const symbol = hit.instrument?.symbol ?? null;
                return (
                  <Stack as="li" key={hit.instrumentId} gap={0}>
                    <Stack direction="row" gap={2} align="center" wrap>
                      {symbol ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`Open ${symbol} in Explore`}
                          onClick={() => {
                            onOpenTicker(symbol, row.id);
                          }}
                        >
                          {symbol}
                        </Button>
                      ) : (
                        <Text size="sm" mono>
                          {hit.instrumentId}
                        </Text>
                      )}
                      {hit.instrument?.name && (
                        <Text size="sm" tone="secondary" truncate>
                          {hit.instrument.name}
                        </Text>
                      )}
                      <DecisionBadge decision={hit.decision} />
                      {hit.score != null && (
                        <Text size="sm" mono>
                          {formatValue(hit.score, { kind: 'number', digits: 1 }).text}
                        </Text>
                      )}
                    </Stack>
                    {hit.reasons && (
                      <Text size="xs" tone="muted">
                        {hit.reasons}
                      </Text>
                    )}
                  </Stack>
                );
              })}
            </Stack>
          )}
        </Section>
        <Section title="Track record">
          {row.rules ? <RecordCard screenerId={row.id} onOpenEdge={onOpenEdge} /> : null}
        </Section>
      </Grid>
    </Stack>
  );
}
