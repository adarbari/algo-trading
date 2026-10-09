/**
 * What a followed edge has done on paper, under its backtest (ADR 0053 amendment 2026-10-09): the
 * live record against the backtest's usual range (the sentence, the counts and the picture of
 * where the live win rate falls), a new version's forward test beside the edge it would replace,
 * and the paper trades. Shown once the edge has paper trades or a forward test; every figure,
 * sentence and bar is the server's, for the session.
 */
import {
  Banner,
  DataTable,
  Distribution,
  Panel,
  Stack,
  StatStrip,
  StatusBadge,
  Text,
  type StatItem,
} from '@algotrade/ui';

import {
  rangeBins,
  rangeMarkers,
  recordLabel,
  recordTone,
  useEdgePaper,
  type ForwardTest,
  type PaperRecord,
} from '@/entities/edge';
import { GuideHelp } from '@/features/guide-help';

import { tradeColumns } from '../model/columns';

const PERCENT = { kind: 'percent', digits: 0 } as const;
const COUNT = { kind: 'number' } as const;

const recordItems = (r: PaperRecord): StatItem[] => [
  { id: 'closed', label: 'Closed', value: r.closed, format: COUNT },
  { id: 'wins', label: 'Won', value: r.wins, format: COUNT },
  { id: 'rate', label: 'Win rate', value: r.winRate, format: PERCENT },
  { id: 'backtest', label: 'Backtest', value: r.backtestRate, format: PERCENT, sub: r.basis },
  { id: 'open', label: 'Open', value: r.open, format: COUNT },
  { id: 'skipped', label: 'Skipped', value: r.skipped, format: COUNT },
];

const forwardItems = (f: ForwardTest): StatItem[] => [
  { id: 'sessions', label: 'Sessions', value: f.sessions, format: COUNT, sub: `of ${f.needed}` },
  { id: 'this', label: 'This version', value: f.this.winRate, format: PERCENT },
  { id: 'this-closed', label: 'Closed', value: f.this.closed, format: COUNT },
  { id: 'old', label: f.replacesName, value: f.replaced.winRate, format: PERCENT },
  { id: 'old-closed', label: 'Closed', value: f.replaced.closed, format: COUNT },
];

export interface EdgeLiveProps {
  /** The edge's id. */
  edgeId: string;
}

export function EdgeLive({ edgeId }: EdgeLiveProps) {
  const paper = useEdgePaper(edgeId).data;
  if (!paper || (paper.record.state === 'no_trades' && !paper.forward)) return null;
  const record = paper.record;
  return (
    <Stack gap={4}>
      {paper.forward && (
        <Stack gap={2}>
          <Banner
            tone="info"
            title="Forward test"
            actions={<GuideHelp entry={{ kind: 'term', id: 'forward_test' }} />}
          >
            {paper.forward.headline}
          </Banner>
          <StatStrip label="Forward test figures" items={forwardItems(paper.forward)} />
        </Stack>
      )}
      <Panel
        title="Live record"
        actions={
          <Stack direction="row" gap={1} align="center">
            <GuideHelp entry={{ kind: 'term', id: 'live_record' }} />
            <GuideHelp entry={{ kind: 'term', id: 'usual_range' }} />
          </Stack>
        }
      >
        <Stack gap={3}>
          <Stack direction="row" gap={2} align="center" wrap>
            <StatusBadge tone={recordTone(record.state)}>{recordLabel(record.state)}</StatusBadge>
            <Text size="sm">{record.headline}</Text>
          </Stack>
          <StatStrip label="Live record figures" items={recordItems(record)} />
          {record.bins.length > 0 && (
            <Distribution
              label="Chance of each win rate if the backtest held"
              bins={rangeBins(record)}
              markers={rangeMarkers(record)}
              format={PERCENT}
              height="sm"
            />
          )}
        </Stack>
      </Panel>
      <Panel title="Paper trades" flush>
        <DataTable
          label="Paper trades"
          columns={tradeColumns}
          rows={paper.trades}
          getRowId={(t) => `${t.signalSession}:${t.instrumentId}`}
          emptyMessage="No paper trades yet"
          visibleRows={8}
        />
      </Panel>
    </Stack>
  );
}
