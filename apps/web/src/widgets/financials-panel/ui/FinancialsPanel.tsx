/**
 * Financials: a company's reported results and the market's forecasts for the latest session,
 * from one GraphQL read (`useInstrumentFacts`). A strip of the key metrics leads, then five
 * compact sections (growth, profitability, balance sheet and cash flow, valuation, earnings) in
 * columns that stack on a phone. Every row is shown: a value the session does not have reads as
 * the word for its kind with its Guide term button. Status and basis fields are badges in the
 * section header. A fund has no financials and says so with the panel's empty state.
 */
import { Grid, Heading, KeyValue, Panel, StatStrip, StatusBadge, Stack } from '@algotrade/ui';
import { useMemo } from 'react';

import { unknownWord } from '@/entities/availability';
import { isUnknown, type Values } from '@/entities/feature';
import { useInstrumentFacts } from '@/entities/instrument';
import { GuideHelp, termHelp } from '@/features/guide-help';

import { rowItem, statItem, type RowHelp } from '../model/rows';
import { FINANCIALS_PARTS, KEY_METRICS, SECTIONS } from '../model/sections';
import { financialsTone } from '../model/tones';

export interface FinancialsPanelProps {
  symbol: string;
}

const HELP: RowHelp = {
  field: (name) => <GuideHelp entry={{ kind: 'field', id: name }} />,
  term: termHelp,
};

function Badge({ values, name }: { values: Values; name: string }) {
  const served = values.get(name);
  const known = served && !isUnknown(served);
  const word = known ? String(served.value) : unknownWord(served?.unknown);
  return (
    <Stack direction="row" gap={1} align="center">
      <StatusBadge tone={known ? financialsTone(word) : 'neutral'}>{word}</StatusBadge>
      {HELP.field(name)}
      {!known && served?.unknown ? HELP.term(served.unknown.guideTerm) : null}
    </Stack>
  );
}

export function FinancialsPanel({ symbol }: FinancialsPanelProps) {
  const first = useInstrumentFacts(symbol, FINANCIALS_PARTS[0] ?? []);
  const second = useInstrumentFacts(symbol, FINANCIALS_PARTS[1] ?? []);
  const instrument = first.data?.instrument;
  const rest = second.data?.instrument;
  const values = useMemo<Values>(
    () =>
      new Map([...(instrument?.features ?? []), ...(rest?.features ?? [])].map((v) => [v.name, v])),
    [instrument, rest],
  );
  const state =
    first.isError || second.isError
      ? 'error'
      : first.isPending || second.isPending
        ? 'loading'
        : !instrument || instrument.isEtf
          ? 'empty'
          : 'ready';
  return (
    <Panel
      title={`${symbol} · financials`}
      description={instrument?.name || undefined}
      actions={termHelp('financials_panel')}
      state={state}
      loadingLabel={`Loading ${symbol}…`}
      errorMessage={`${symbol} failed to load.`}
      emptyMessage={
        <Stack direction="row" gap={1} align="center">
          {instrument?.isEtf
            ? `${symbol} is a fund and has no financials.`
            : `${symbol} is not in the reference snapshot.`}
          {termHelp('financials_panel')}
        </Stack>
      }
      onRetry={() => {
        void first.refetch();
        void second.refetch();
      }}
    >
      <Stack gap={4}>
        <StatStrip
          label={`${symbol} key financials`}
          items={KEY_METRICS.map((spec) => statItem(values, spec, HELP))}
        />
        <Grid columns={2} gap={4} collapse="md">
          {SECTIONS.map((section) => (
            <Stack key={section.id} gap={2}>
              <Stack direction="row" gap={2} align="center" wrap>
                <Heading level={3}>{section.title}</Heading>
                {termHelp(section.term)}
                {section.statuses.map((name) => (
                  <Badge key={name} values={values} name={name} />
                ))}
              </Stack>
              <KeyValue
                label={section.title}
                items={section.rows.map((spec) => rowItem(values, spec, HELP))}
                alignValues="end"
              />
            </Stack>
          ))}
        </Grid>
      </Stack>
    </Panel>
  );
}
