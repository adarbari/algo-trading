/**
 * Section "How it has done" of an option setup's page (ADR 0088): the setup's own history on the
 * cash it sets aside as an evidence strip (a typical trade with its range, a bad trade with how
 * many trades it averages), then how sure that is (how many trades kept the premium, the return
 * at each cost level, the worst trade in each stress window) and the years. Every figure is the
 * server's and labelled backtested (hypothetical); history-derived evidence is owner-only, so a
 * viewer without it sees the server's `unknown` and nothing else.
 */
import {
  formatValue,
  Heading,
  KeyValue,
  Panel,
  Stack,
  StatStrip,
  StatusBadge,
  Text,
  type KeyValueItem,
  type StatItem,
} from '@algotrade/ui';

import { UnknownNote } from '@/entities/availability';
import { sliceStateLabel, type OptionEvidence } from '@/entities/edge';
import { Labelled, termHelp } from '@/features/guide-help';

import { costItems, stressItems, yearItems } from '../model/rows';

export interface SetupOptionRecordProps {
  evidence: OptionEvidence;
}

const pct = (fraction: number): string =>
  formatValue(fraction, { kind: 'percent', digits: 1 }).text;

function strip(e: OptionEvidence): StatItem[] {
  const range =
    e.typicalLo != null && e.typicalHi != null
      ? `from ${pct(e.typicalLo)} to ${pct(e.typicalHi)}`
      : undefined;
  return [
    {
      id: 'typical',
      label: <Labelled text="A typical trade" help="option_typical" />,
      value: e.typical,
      format: { kind: 'percent', digits: 1 },
      ...(range ? { sub: range } : {}),
    },
    {
      id: 'bad',
      label: <Labelled text="A bad trade" help="option_bad_trade" />,
      value: e.badMean,
      format: { kind: 'percent', digits: 1 },
      sub: `the worst ${String(e.badTrades)} of ${String(e.trades)} trades`,
    },
    {
      id: 'trades',
      label: <Labelled text="Trades" help="option_trades" />,
      value: e.trades,
      format: { kind: 'number' },
    },
  ];
}

function sureItems(e: OptionEvidence): KeyValueItem[] {
  return [
    {
      id: 'kept',
      label: 'Kept the premium',
      value: `${String(e.kept)} of ${String(e.trades)} trades`,
      action: termHelp('option_kept'),
    },
    ...(e.costs?.state === 'measured' ? costItems(e.costs.levels) : []),
  ];
}

export function SetupOptionRecord({ evidence }: SetupOptionRecordProps) {
  const basis = ['Backtested (hypothetical)', evidence.basisScreener]
    .filter((part) => part != null)
    .join(' · ');
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={1} align="center">
        <Heading level={2}>How it has done</Heading>
        {termHelp('setup_how_done')}
      </Stack>
      {evidence.unknown ? (
        <UnknownNote unknown={evidence.unknown} />
      ) : (
        <>
          <StatStrip
            variant="evidence"
            label="The setup's own history, on the cash set aside"
            items={strip(evidence)}
            basis={{ kind: 'backtested', label: basis }}
          />
          {evidence.inSampleOnly ? (
            <Stack direction="row" gap={1} align="center">
              <StatusBadge tone="warning">In-sample only</StatusBadge>
              {termHelp('option_in_sample_only')}
            </Stack>
          ) : null}
          <Panel title="How sure, costs and stress" actions={termHelp('option_how_sure')}>
            <Stack gap={3}>
              <KeyValue label="How sure and costs" items={sureItems(evidence)} />
              {evidence.costs && evidence.costs.state !== 'measured' ? (
                <Stack direction="row" gap={1} align="center">
                  <Text tone="secondary">{sliceStateLabel(evidence.costs.state)}</Text>
                  {termHelp('cost_state')}
                </Stack>
              ) : null}
              {evidence.stress.length > 0 ? (
                <KeyValue
                  label="The worst trade in each stress window"
                  items={stressItems(evidence.stress)}
                />
              ) : null}
              {evidence.stressUnknown ? <UnknownNote unknown={evidence.stressUnknown} /> : null}
            </Stack>
          </Panel>
          <Panel title="By year" actions={termHelp('option_by_year')}>
            {evidence.byYear.length > 0 ? (
              <KeyValue label="By year" items={yearItems(evidence.byYear)} />
            ) : (
              <Text tone="secondary">No years to show</Text>
            )}
          </Panel>
        </>
      )}
    </Stack>
  );
}
