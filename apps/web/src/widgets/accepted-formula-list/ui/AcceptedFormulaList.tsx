/**
 * The formulas traders accepted in Describe it, one row per distinct formula in the server's
 * order (most users first): the formula, its unit and description, how many distinct users
 * accepted it and how often, when, the site feature it duplicates and the backlog item it exactly
 * matches. Counts only, never who. A row opens to its canonical form (what the server grouped
 * by). Nothing is counted, grouped or matched here.
 */
import {
  ExpandableTable,
  KeyValue,
  Mono,
  Panel,
  StatusBadge,
  TextLink,
  type ExpandableTableColumn,
  type ExpandableTableRow,
} from '@algotrade/ui';
import { useState } from 'react';

import {
  START_PAGE,
  TERM_OF_ACCEPTED,
  TERM_OF_BACKLOG_MATCH,
  TERM_OF_DUPLICATE,
  TERM_OF_FINGERPRINT,
  useAcceptedFormulas,
  type AcceptedFormula,
} from '@/entities/accepted-formula';
import { fieldPath } from '@/entities/guide';
import { GuideHelp, termHelp } from '@/features/guide-help';

const columns = (): readonly ExpandableTableColumn[] => [
  { id: 'formula', label: <>Formula {termHelp(TERM_OF_FINGERPRINT)}</>, grow: 2.4, narrow: true },
  { id: 'unit', label: 'Unit' },
  { id: 'description', label: 'Description', grow: 2 },
  { id: 'users', label: 'Users', align: 'end', narrow: true },
  { id: 'accepted', label: 'Accepted', align: 'end' },
  { id: 'first', label: 'First accepted' },
  { id: 'last', label: 'Last accepted' },
  { id: 'duplicate', label: <>Duplicates {termHelp(TERM_OF_DUPLICATE)}</>, grow: 1.6 },
  { id: 'backlog', label: <>Backlog {termHelp(TERM_OF_BACKLOG_MATCH)}</> },
];

const EMPTY = (
  <Mono size="sm" tone="muted">
    —
  </Mono>
);

function toRow(
  f: AcceptedFormula,
  open: boolean,
  onOpenChange: (open: boolean) => void,
): ExpandableTableRow {
  return {
    id: f.fingerprint,
    open,
    onOpenChange,
    cells: {
      formula: <Mono size="sm">{f.expression}</Mono>,
      unit: f.unit ? <Mono size="sm">{f.unit}</Mono> : EMPTY,
      description: f.description || EMPTY,
      users: f.users,
      accepted: f.acceptedCount,
      first: <Mono size="sm">{f.firstAccepted}</Mono>,
      last: <Mono size="sm">{f.lastAccepted}</Mono>,
      duplicate: f.duplicateOf ? (
        <>
          <StatusBadge tone="warning">DUPLICATE</StatusBadge>{' '}
          <TextLink href={fieldPath(f.duplicateOf)} mono size="sm">
            {f.duplicateOf}
          </TextLink>
        </>
      ) : (
        EMPTY
      ),
      backlog: f.backlogKey ? <Mono size="sm">{f.backlogKey}</Mono> : EMPTY,
    },
    detail: (
      <KeyValue
        layout="stacked"
        items={[
          { id: 'canonical', label: 'Canonical form', value: f.canonical, mono: true },
          { id: 'fingerprint', label: 'Fingerprint', value: f.fingerprint, mono: true },
        ]}
      />
    ),
  };
}

export function AcceptedFormulaList() {
  const formulas = useAcceptedFormulas();
  const [openId, setOpenId] = useState<string | null>(null);
  const rows = formulas.data?.rows ?? [];
  const state =
    formulas.isError && !formulas.data
      ? 'error'
      : formulas.isPending
        ? 'loading'
        : rows.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Panel
      title="Accepted formulas"
      flush
      state={state}
      loadingLabel="Loading accepted formulas…"
      emptyMessage="No formula has been accepted."
      errorMessage="The accepted formulas failed to load."
      onRetry={() => void formulas.refetch()}
      actions={
        <>
          <GuideHelp entry={{ kind: 'term', id: TERM_OF_ACCEPTED }} />
          <GuideHelp entry={{ kind: 'start', id: START_PAGE }} />
        </>
      }
    >
      <ExpandableTable
        label="Accepted formulas"
        columns={columns()}
        rows={rows.map((f) =>
          toRow(f, openId === f.fingerprint, (open) => {
            setOpenId(open ? f.fingerprint : null);
          }),
        )}
      />
    </Panel>
  );
}
