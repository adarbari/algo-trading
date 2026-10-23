/**
 * The top-ideas table's columns, in two sets chosen by the page's `columns` search param. Stocks
 * (default): rank, ticker, who picked it, decision (the badge over the criteria it comes from),
 * score, size, price and the watch-outs (flags, then the near-miss reasons). Options: rank, ticker,
 * decision, score, who picked it, then the served facts for the
 * session (days to the nearest expiry, flagged when the server says earnings come first; IV30),
 * the screeners' stored display values (HV30, IV / HV and the best put) and the watch-outs. The
 * regime's size for the idea shows in both when the run stamped one; a fact or display-value
 * column appears only when some idea has a value for it.
 */
import {
  Mono,
  OutcomeDots,
  Stack,
  StatusBadge,
  Text,
  TextLink,
  type DataTableColumn,
  type OutcomeDot,
  type ValueFormat,
} from '@algotrade/ui';

import { fieldColumn, valueFormat, type HelpedColumn } from '@/entities/feature';
import {
  earningsBeforeExpiry,
  factOf,
  IDEA_FACTS,
  type Idea,
  type IdeaColumnSet,
} from '@/entities/idea';
import { screenerResultsPath } from '@/entities/guide';
import { DecisionBadge, decisionLabel, outcomeLabel } from '@/entities/screen';

import { dteReason, earningsCell, expiryDte, iv30, served } from './facts';

/** A display value a screener may store (`[columns]` or a criterion id), shown when present. */
interface MetricColumn {
  key: string;
  header: string;
  format: ValueFormat;
}

const METRIC_COLUMNS: readonly MetricColumn[] = [
  {
    key: 'hv30',
    header: 'HV30',
    format: { kind: 'percent' },
  },
  {
    key: 'iv_hv_ratio',
    header: 'IV / HV',
    format: { kind: 'number', digits: 2 },
  },
  {
    key: 'put_strike',
    header: 'Put strike',
    format: { kind: 'currency' },
  },
  {
    key: 'put_delta',
    header: 'Put delta',
    format: { kind: 'number', digits: 2 },
  },
  {
    key: 'put_premium',
    header: 'Put premium',
    format: { kind: 'currency' },
  },
  {
    key: 'put_roc',
    header: 'Put ROC',
    format: { kind: 'percent' },
  },
];

/** A tooltip only when there is something to say (props are exact: no `title: undefined`). */
const titled = (title: string | undefined) => (title === undefined ? {} : { title });

/** The one display-column rule: a column is shown when some idea has a value for it. */
export function anyValue(ideas: readonly Idea[], value: (idea: Idea) => unknown): boolean {
  return ideas.some((idea) => value(idea) !== null && value(idea) !== undefined);
}

const numeric = (idea: Idea, key: string): number | null => {
  const value = idea.metrics[key];
  return typeof value === 'number' ? value : null;
};

function metricColumns(ideas: readonly Idea[]): DataTableColumn<Idea>[] {
  return METRIC_COLUMNS.filter((m) => anyValue(ideas, (idea) => numeric(idea, m.key))).map((m) => ({
    id: m.key,
    header: m.header,
    value: (idea) => numeric(idea, m.key),
    format: m.format,
  }));
}

/** IV30 as the server formats it (`info.format` of the first idea that has one). */
function ivColumns(ideas: readonly Idea[]): HelpedColumn<Idea>[] {
  const served = ideas.map((idea) => factOf(idea, IDEA_FACTS.iv30)).find((v) => v?.info);
  if (!served || !anyValue(ideas, iv30)) return [];
  return [
    fieldColumn<Idea>(IDEA_FACTS.iv30, {
      id: 'iv30',
      header: 'IV30',
      value: iv30,
      format: valueFormat(served.info),
    }),
  ];
}

const dteColumn = fieldColumn<Idea>(IDEA_FACTS.expiryDte, {
  id: 'dte',
  header: 'Expiry DTE',
  value: expiryDte,
  format: { kind: 'number' },
  width: 'md',
  cell: ({ row, formatted }) =>
    earningsBeforeExpiry(row) ? (
      <Stack direction="row" gap={2} align="center" justify="end">
        <StatusBadge tone="warning" icon="alert" title="Earnings fall on or before this expiry">
          Earnings first
        </StatusBadge>
        <Mono>{formatted.text}</Mono>
      </Stack>
    ) : (
      <Mono tone={expiryDte(row) === null ? 'muted' : 'default'} {...titled(dteReason(row))}>
        {formatted.text}
      </Mono>
    ),
});

const RANK: DataTableColumn<Idea> = {
  id: 'rank',
  header: '#',
  value: (idea) => idea.rank,
  format: { kind: 'number' },
  width: 'xs',
};

/** The size the regime gives a new position (the best pick's run stamped it): a column when some
 * idea has one. */
const SIZE: HelpedColumn<Idea> = {
  id: 'size',
  help: { kind: 'term', id: 'idea_size' },
  header: 'Size',
  value: (idea) => idea.sizeMultiplier,
  format: { kind: 'percent', digits: 0 },
  width: 'sm',
};

/** The ticker over the company name and its sector (the sector ETF's ticker). */
const tickerColumn: DataTableColumn<Idea> = {
  id: 'symbol',
  header: 'Ticker',
  value: (idea) => idea.symbol ?? idea.instrumentId,
  hideable: false,
  width: 'md',
  grow: true,
  cell: ({ row }) => {
    const under = [row.name, served(row, IDEA_FACTS.sectorEtf)?.text].filter(Boolean).join(' · ');
    return (
      <Stack gap={0}>
        <Mono weight="medium">{row.symbol ?? row.instrumentId}</Mono>
        {under && (
          <Text size="xs" tone="muted" truncate title={under}>
            {under}
          </Text>
        )}
      </Stack>
    );
  },
};

/** Every screener that picked the idea (the best first), each a link to its results with the
 * place the ticker holds in that screener's list. */
const pickedByColumn: HelpedColumn<Idea> = {
  id: 'picked-by',
  help: { kind: 'term', id: 'picked_by' },
  header: 'Picked by',
  value: (idea) => idea.pickedBy.length,
  width: 'lg',
  grow: true,
  sortable: false,
  essential: true,
  cell: ({ row }) => (
    <Stack direction="row" gap={1} wrap>
      {row.pickedBy.map((pick) => (
        <TextLink key={pick.screenerId} href={screenerResultsPath(pick.screenerId)} size="sm">
          {pick.position > 1 ? `${pick.screenerName} #${String(pick.position)}` : pick.screenerName}
        </TextLink>
      ))}
    </Stack>
  ),
};

/** The idea's score under the Ideas rule (its best pick's weight over position). */
const scoreColumn: HelpedColumn<Idea> = {
  id: 'score',
  help: { kind: 'term', id: 'ideas_ranking' },
  header: 'Score',
  value: (idea) => idea.score,
  format: { kind: 'number', digits: 2 },
  width: 'xs',
  essential: true,
};

const OUTCOME_DOT: Readonly<Record<string, OutcomeDot['tone']>> = {
  PASS: 'positive',
  NEAR: 'warning',
  FAIL: 'negative',
};

/** One square per criterion of the best pick, coloured by the outcome the server stored. */
function criterionDots(idea: Idea): OutcomeDot[] {
  return idea.best.criteria.map((c) => ({
    label: `${decisionLabel(c.id)}: ${outcomeLabel(c.outcome)}`,
    tone: OUTCOME_DOT[c.outcome] ?? 'muted',
  }));
}

/** The decision badge over the criteria it is derived from (one square each). */
const decisionColumn: HelpedColumn<Idea> = {
  id: 'decision',
  header: 'Decision',
  help: { kind: 'term', id: 'idea_decision' },
  value: (idea) => idea.best.decision,
  essential: true,
  width: 'md',
  cell: ({ row }) => (
    <Stack gap={1}>
      <DecisionBadge decision={row.best.decision} />
      <OutcomeDots items={criterionDots(row)} label="Criteria" />
    </Stack>
  ),
};

/** The close over the one-session move, each in the format the server sent. */
const priceColumn: HelpedColumn<Idea> = {
  id: 'price',
  help: { kind: 'term', id: 'idea_price' },
  header: 'Price',
  value: (idea) => idea.facts[IDEA_FACTS.close]?.value,
  width: 'sm',
  cell: ({ row }) => {
    const close = served(row, IDEA_FACTS.close);
    const move = served(row, IDEA_FACTS.ret1d);
    return (
      <Stack gap={0} align="end">
        <Text numeric tone={close ? 'default' : 'muted'}>
          {close?.text ?? 'Unknown'}
        </Text>
        {move && (
          <Text size="xs" numeric tone={move.tone}>
            {move.text}
          </Text>
        )}
      </Stack>
    );
  },
};

/** The watch-outs as badges, the near-miss reasons under them in muted text, else the next
 * earnings (only when there is neither). */
const watchOutColumn: HelpedColumn<Idea> = {
  id: 'watch-out',
  header: 'Watch out',
  help: { kind: 'term', id: 'idea_watch_out' },
  value: (idea) => idea.watchOut.length,
  width: 'lg',
  grow: true,
  cell: ({ row }) => {
    const reasons = row.best.reasons;
    if (row.watchOut.length === 0 && !reasons) {
      const shown = earningsCell(row);
      return (
        <Text size="sm" tone="muted" {...(shown.title === undefined ? {} : { title: shown.title })}>
          {shown.text}
        </Text>
      );
    }
    return (
      <Stack gap={1}>
        {row.watchOut.length > 0 && (
          <Stack direction="row" gap={1} wrap>
            {row.watchOut.map((w) => (
              <StatusBadge key={w.id} tone="warning">
                {w.label}
              </StatusBadge>
            ))}
          </Stack>
        )}
        {reasons && (
          <Text size="xs" tone="muted" truncate title={reasons}>
            {reasons}
          </Text>
        )}
      </Stack>
    );
  },
};

/** The columns for these ideas in the chosen set (what is served decides which facts show). */
export function ideaColumns(
  ideas: readonly Idea[],
  set: IdeaColumnSet = 'stocks',
): HelpedColumn<Idea>[] {
  const size = anyValue(ideas, (idea) => idea.sizeMultiplier) ? [SIZE] : [];
  if (set === 'options') {
    return [
      RANK,
      tickerColumn,
      decisionColumn,
      scoreColumn,
      pickedByColumn,
      ...size,
      dteColumn,
      ...ivColumns(ideas),
      ...metricColumns(ideas),
      watchOutColumn,
    ];
  }
  return [
    RANK,
    tickerColumn,
    pickedByColumn,
    decisionColumn,
    scoreColumn,
    ...size,
    priceColumn,
    watchOutColumn,
  ];
}
