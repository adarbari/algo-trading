/**
 * One screener run's record as key-value rows: what it screened, the rules it ran, what it
 * picked and recorded, and what changed against the run before. A figure the run did not record
 * says so (never zero); each label carries its Guide button. Nothing is derived here: every
 * count is the server's.
 */
import { Mono, StatusBadge, type KeyValueItem } from '@algotrade/ui';

import { stamp, statusTone, type ScreenerRunRecord } from '@/entities/screener-run';
import { Labelled } from '@/features/guide-help';

const NOT_RECORDED = 'Not recorded';

const count = (n: number | null | undefined) => (n === null || n === undefined ? NOT_RECORDED : n);

const tables = (names: readonly string[]) => (names.length === 0 ? 'None' : names.join(', '));

/** The run's facts: session, status, times, rules, picks, regime, coverage and tables. */
export function factRows(run: ScreenerRunRecord): KeyValueItem[] {
  return [
    {
      id: 'session',
      label: <Labelled text="Session" help="session" />,
      value: run.session,
      mono: true,
    },
    {
      id: 'status',
      label: <Labelled text="Status" help="screener_run_status" />,
      value: <StatusBadge tone={statusTone(run.status)}>{run.status}</StatusBadge>,
    },
    {
      id: 'owner',
      label: <Labelled text="Owner" help="screener_run_owner" />,
      value: run.owner,
    },
    {
      id: 'started',
      label: <Labelled text="Started" help="screener_run_started" />,
      value: <Mono size="sm">{stamp(run.startedAt)}</Mono>,
    },
    {
      id: 'knowledge',
      label: <Labelled text="Knowledge time" help="knowledge_time" />,
      value: <Mono size="sm">{stamp(run.knowledgeTs)}</Mono>,
    },
    {
      id: 'config',
      label: <Labelled text="Config" help="screener_run_config" />,
      value:
        run.configVersion === null && !run.configHash
          ? NOT_RECORDED
          : `version ${run.configVersion === null ? NOT_RECORDED.toLowerCase() : String(run.configVersion)}, hash ${run.configHash ?? NOT_RECORDED.toLowerCase()}`,
      mono: true,
    },
    {
      id: 'picked',
      label: <Labelled text="Picked" help="screener_run_picked" />,
      value: count(run.picked),
    },
    { id: 'paused', label: <Labelled text="Paused" help="paused" />, value: count(run.paused) },
    {
      id: 'regime',
      label: <Labelled text="Regime" help="regime" />,
      value: run.regime ?? NOT_RECORDED,
    },
    {
      id: 'coverage',
      label: <Labelled text="Coverage" help="screener_run_coverage" />,
      value: run.coverage ?? NOT_RECORDED,
    },
    {
      id: 'missing',
      label: <Labelled text="Missing tables" help="screener_run_missing_tables" />,
      value: tables(run.missingTables),
      mono: true,
    },
    {
      id: 'optional',
      label: <Labelled text="Missing optional tables" help="screener_run_missing_tables" />,
      value: tables(run.missingOptionalTables),
      mono: true,
    },
  ];
}

/** Every decision with its count over the whole run (null: the run never finished). */
export function decisionRows(run: ScreenerRunRecord): KeyValueItem[] {
  return (run.decisions ?? []).map((d) => ({
    id: d.decision,
    label: d.decision,
    value: d.count,
    format: { kind: 'number' },
  }));
}

/** What the run changed against the run before it (null: no comparison was stored). */
export function changeRows(run: ScreenerRunRecord): KeyValueItem[] {
  const changes = run.changes;
  const label = <Labelled text="Previous run" help="screener_run_changes" />;
  if (!changes) return [{ id: 'previous', label, value: NOT_RECORDED }];
  const previous = changes.previousRunId
    ? `${changes.previousRunId}, session ${changes.previousSession ?? NOT_RECORDED.toLowerCase()}, version ${
        changes.previousVersion === null
          ? NOT_RECORDED.toLowerCase()
          : String(changes.previousVersion)
      }`
    : 'None';
  return [
    { id: 'previous', label, value: previous, mono: true },
    { id: 'new', label: 'New picks', value: count(changes.newPicks) },
    { id: 'dropped', label: 'Dropped', value: count(changes.dropped) },
  ];
}
