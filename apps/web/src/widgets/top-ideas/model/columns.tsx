/**
 * The top-ideas table's columns, in two sets chosen by the page's `columns` search param. Stocks
 * (default): rank, ticker, why it is here, decision, score, criteria, price
 * and the watch-outs. Options: rank, ticker, decision, score, then the served facts for the
 * session (days to the nearest expiry, flagged when the server says earnings come first; IV30),
 * the screeners' stored display values (HV30, IV / HV and the best put) and the watch-outs. The
 * regime's size for the idea shows in both when the run stamped one; a fact or display-value
 * column appears only when some idea has a value for it.
 */
import {
  Button,
  Mono,
  OutcomeDots,
  Stack,
  StatusBadge,
  Text,
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
import { DecisionBadge, decisionLabel, outcomeLabel } from '@/entities/screen';

import { dteReason, earningsCell, expiryDte, iv30, served } from './facts';

/** A display value a screener may store (`[columns]` or a criterion id), shown when present. */
interface MetricColumn {
  key: string;
  header: string;
  description?: string;
  format: ValueFormat;
}

const METRIC_COLUMNS: readonly MetricColumn[] = [
  {
    key: 'hv30',
    header: 'HV30',
    description: '30-day historical volatility',
    format: { kind: 'percent' },
  },
  {
    key: 'iv_hv_ratio',
    header: 'IV / HV',
    description: 'IV30 over HV30',
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
    description: 'Best put: return on capital',
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
    description: m.description ?? m.header,
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
      description: '30-day implied volatility',
      value: iv30,
      format: valueFormat(served.info),
    }),
  ];
}

const dteColumn = fieldColumn<Idea>(IDEA_FACTS.expiryDte, {
  id: 'dte',
  header: 'Expiry DTE',
  description: 'Days to the nearest expiry; flagged when earnings come first',
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
  description: 'Your screener priority, then score',
  value: (idea) => idea.rank,
  format: { kind: 'number' },
  width: 'xs',
};

/** The size the regime gives a new position (the best pick's run stamped it): a column when some
 * idea has one. */
const SIZE: DataTableColumn<Idea> = {
  id: 'size',
  header: 'Size',
  description: 'Share of the normal size the regime allows',
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

/** Why the idea is here: the best pick's reasons, its screener, and how many others picked it. */
const whyColumn = (onOpenScreener: (screenerId: string) => void): DataTableColumn<Idea> => ({
  id: 'why',
  header: "Why it's here",
  value: (idea) => idea.best.reasons || null,
  width: 'xl',
  grow: true,
  sortable: false,
  cell: ({ row }) => (
    <Stack gap={0}>
      {row.best.reasons && (
        <Text size="sm" truncate title={row.best.reasons}>
          {row.best.reasons}
        </Text>
      )}
      <Stack direction="row" gap={1} align="center">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            onOpenScreener(row.best.screenerId);
          }}
        >
          {row.best.screenerName}
        </Button>
        {row.picks.length > 1 && (
          <Text size="xs" tone="muted">
            {`+${String(row.picks.length - 1)} more`}
          </Text>
        )}
      </Stack>
    </Stack>
  ),
});

const scoreColumn: DataTableColumn<Idea> = {
  id: 'score',
  header: 'Score',
  description: 'Score of the best pick',
  value: (idea) => idea.best.score,
  format: { kind: 'number', digits: 0 },
  width: 'xs',
  essential: true,
};

const decisionColumn: DataTableColumn<Idea> = {
  id: 'decision',
  header: 'Decision',
  description: 'Best decision across the screeners',
  value: (idea) => idea.best.decision,
  essential: true,
  cell: ({ row }) => <DecisionBadge decision={row.best.decision} />,
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

const criteriaColumn: DataTableColumn<Idea> = {
  id: 'criteria',
  header: 'Criteria',
  value: (idea) => idea.best.criteria.map((c) => c.outcome).join(),
  sortable: false,
  width: 'md',
  cell: ({ row }) => <OutcomeDots items={criterionDots(row)} label="Criteria" />,
};

/** The close over the one-session move, each in the format the server sent. */
const priceColumn: DataTableColumn<Idea> = {
  id: 'price',
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

/** The watch-outs, else the next earnings in muted text. */
const watchOutColumn: DataTableColumn<Idea> = {
  id: 'watch-out',
  header: 'Watch out',
  description: 'Reasons to look twice',
  value: (idea) => idea.watchOut.length,
  width: 'lg',
  grow: true,
  cell: ({ row }) => {
    if (row.watchOut.length === 0) {
      const shown = earningsCell(row);
      return (
        <Text size="sm" tone="muted" {...(shown.title === undefined ? {} : { title: shown.title })}>
          {shown.text}
        </Text>
      );
    }
    return (
      <Stack direction="row" gap={1} wrap>
        {row.watchOut.map((w) => (
          <StatusBadge key={w.id} tone="warning">
            {w.label}
          </StatusBadge>
        ))}
      </Stack>
    );
  },
};

/** The columns for these ideas in the chosen set (what is served decides which facts show). */
export function ideaColumns(
  ideas: readonly Idea[],
  onOpenScreener: (screenerId: string) => void,
  set: IdeaColumnSet = 'stocks',
): DataTableColumn<Idea>[] {
  const size = anyValue(ideas, (idea) => idea.sizeMultiplier) ? [SIZE] : [];
  if (set === 'options') {
    return [
      RANK,
      tickerColumn,
      decisionColumn,
      scoreColumn,
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
    whyColumn(onOpenScreener),
    decisionColumn,
    scoreColumn,
    ...size,
    criteriaColumn,
    priceColumn,
    watchOutColumn,
  ];
}
