/**
 * The latest session's live verification vs IBKR: checks by status (a StackedBar), the failing checks
 * (ours vs IBKR's value, the difference and tolerance; a row opens its ticker in Explore), and
 * the counts per check on demand.
 */
import {
  DataTable,
  Disclosure,
  EmptyState,
  ErrorState,
  formatValue,
  Panel,
  Skeleton,
  Stack,
  StackedBar,
  type DataTableColumn,
  type DataTone,
} from '@algotrade/ui';

import { RunStatusBadge } from '@/entities/run';
import {
  failedShare,
  failingChecks,
  statusCounts,
  useVerification,
  VERIFY_STATUSES,
  type CheckCounts,
  type FailingCheck,
  type VerifyStatus,
} from '@/entities/verification';

const TONES: Record<VerifyStatus, DataTone> = {
  PASS: 'positive',
  WARN: 'warning',
  FAIL: 'negative',
  NA: 'muted',
};
const LABELS: Record<VerifyStatus, string> = {
  PASS: 'Pass',
  WARN: 'Warn',
  FAIL: 'Fail',
  NA: 'Not graded',
};
const VALUE = { kind: 'number', digits: 4 } as const;

const FAILING: DataTableColumn<FailingCheck>[] = [
  { id: 'symbol', header: 'Symbol', value: (r) => r.symbol, mono: true, width: 'sm' },
  { id: 'check', header: 'Check', value: (r) => r.check, mono: true, width: 'sm' },
  {
    id: 'status',
    header: 'Result',
    value: (r) => r.status,
    cell: ({ row }) => <RunStatusBadge status={row.status} />,
    width: 'xs',
  },
  { id: 'ours', header: 'Ours', value: (r) => r.ours, format: VALUE },
  { id: 'theirs', header: 'IBKR', value: (r) => r.theirs, format: VALUE },
  {
    id: 'diff',
    header: 'Diff',
    description: 'in the tolerance unit (see note)',
    value: (r) => r.diff,
    format: VALUE,
  },
  { id: 'tolerance', header: 'Tolerance', value: (r) => r.tolerance, format: VALUE },
  { id: 'note', header: 'Note', value: (r) => r.note, tone: 'muted', grow: true, sortable: false },
];

const BY_CHECK: DataTableColumn<CheckCounts>[] = [
  { id: 'check', header: 'Check', value: (c) => c.check, mono: true, grow: true },
  ...VERIFY_STATUSES.map((s): DataTableColumn<CheckCounts> => ({
    id: s,
    header: s,
    value: (c) => c.counts[s] ?? 0,
    format: { kind: 'number' },
    width: 'xs',
  })),
];

export interface VerificationPanelProps {
  /** Open a ticker in Explore (a click on a failing check's row). */
  onOpen?: (symbol: string) => void;
}

export function VerificationPanel({ onOpen }: VerificationPanelProps) {
  const verification = useVerification();
  const served = verification.data;
  const v = served && !served.unknown ? served : null;
  const share = v ? failedShare(v) : null;
  return (
    <Panel
      title={
        served
          ? `Verification vs IBKR · ${formatValue(served.session, { kind: 'date', style: 'weekday' }).text}`
          : 'Verification vs IBKR'
      }
      description={
        v &&
        `${formatValue(v.instruments, { kind: 'number' }).text} instruments · ${formatValue(share, { kind: 'percent', digits: 1 }).text} of graded checks failed`
      }
    >
      {verification.isPending ? (
        <Skeleton lines={4} label="Loading the verification…" />
      ) : verification.isError ? (
        <ErrorState
          compact
          title="The verification could not load."
          detail={verification.error.message}
          onRetry={() => void verification.refetch()}
          retrying={verification.isFetching}
        />
      ) : !v ? (
        <EmptyState
          compact
          title="No verification for this session"
          description="The nightly verify step compares a sample with IBKR when IB Gateway is reachable."
        />
      ) : (
        <Stack gap={4}>
          <StackedBar
            label="Verification checks by status"
            segments={VERIFY_STATUSES.map((s) => ({
              id: s,
              label: LABELS[s],
              value: statusCounts(v)[s],
              tone: TONES[s],
            }))}
          />
          {v.failing.length === 0 ? (
            <EmptyState
              compact
              icon="check"
              title="No failing checks"
              description="Every graded value is within its tolerance."
            />
          ) : (
            <DataTable
              label="Failing verification checks"
              columns={FAILING}
              rows={failingChecks(v)}
              getRowId={(r) => `${r.instrumentId}|${r.check}`}
              visibleRows={Math.min(v.failing.length, 8)}
              {...(onOpen
                ? {
                    onRowActivate: (r: FailingCheck) => {
                      onOpen(r.symbol);
                    },
                  }
                : {})}
            />
          )}
          <Disclosure
            label="Checks by status"
            count={formatValue(v.byCheck.length, { kind: 'number' }).text}
          >
            <DataTable
              label="Verification checks by status"
              columns={BY_CHECK}
              rows={v.byCheck}
              getRowId={(c) => c.check}
              visibleRows={Math.min(v.byCheck.length, 12)}
            />
          </Disclosure>
        </Stack>
      )}
    </Panel>
  );
}
