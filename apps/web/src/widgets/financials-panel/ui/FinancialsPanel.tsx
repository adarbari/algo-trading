/**
 * Financials: a company's reported results and the market's forecasts for the latest session.
 * `useFeatureValues` reads every figure in one request, so all of them are for one session;
 * `useInstrumentFacts` gives only the name and the fund flag. A strip of the key metrics leads,
 * then six compact sections (growth, profitability, balance sheet and cash flow, valuation,
 * earnings, analysts) in columns that stack on a phone. Every row is shown: a value the session
 * does not have reads as the word for its kind with its Guide term button; a section whose
 * every row is the same gap (an uncovered name's analysts) says it once. Status and basis
 * fields are badges in the section header. A fund has no financials and says so with the
 * panel's empty state.
 */
import { Grid, Heading, KeyValue, Panel, StatStrip, StatusBadge, Stack } from '@algotrade/ui';

import { unknownWord } from '@/entities/availability';
import { isUnknown, type Values } from '@/entities/feature';
import { useFeatureValues, useInstrumentFacts } from '@/entities/instrument';
import { GuideHelp, termHelp } from '@/features/guide-help';

import { commonGap, gapItem, rowItem, statItem, type RowHelp } from '../model/rows';
import { FINANCIALS_NAMES, KEY_METRICS, SECTIONS, type SectionSpec } from '../model/sections';
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

/**
 * One section: heading, help and badges, then its rows (or the one row of a shared gap). Beside
 * a shared gap the status badges that hold a value stay (NOT_COVERED and NOT_FETCHED share a
 * public kind and the badge tells them apart); a badge that is itself a gap is dropped.
 */
function Section({ section, values }: { section: SectionSpec; values: Values }) {
  const gap = section.collapseGaps ? commonGap(values, section.rows) : null;
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={2} align="center" wrap>
        <Heading level={3}>{section.title}</Heading>
        {termHelp(section.term)}
        {section.statuses
          .filter((name) => !gap || !isUnknown(values.get(name)))
          .map((name) => (
            <Badge key={name} values={values} name={name} />
          ))}
      </Stack>
      <KeyValue
        label={section.title}
        items={
          gap && section.collapseGaps
            ? [gapItem(section.id, section.collapseGaps, gap, HELP)]
            : section.rows.map((spec) => rowItem(values, spec, HELP))
        }
        alignValues="end"
      />
    </Stack>
  );
}

export function FinancialsPanel({ symbol }: FinancialsPanelProps) {
  const identity = useInstrumentFacts(symbol, []);
  const facts = useFeatureValues(symbol, FINANCIALS_NAMES);
  const instrument = identity.data?.instrument;
  const values: Values = facts.values;
  const state =
    identity.isError || facts.isError
      ? 'error'
      : identity.isPending || facts.isPending
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
        void identity.refetch();
        void facts.refetch();
      }}
    >
      <Stack gap={4}>
        <StatStrip
          label={`${symbol} key financials`}
          items={KEY_METRICS.map((spec) => statItem(values, spec, HELP))}
        />
        <Grid columns={2} gap={4} collapse="md">
          {SECTIONS.map((section) => (
            <Section key={section.id} section={section} values={values} />
          ))}
        </Grid>
      </Stack>
    </Panel>
  );
}
