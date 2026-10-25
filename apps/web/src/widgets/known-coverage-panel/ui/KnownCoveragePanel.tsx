/**
 * The served session's fundamentals share count known against the rows stored: per security
 * type its names, rows, known values and their share (the completeness grid counts rows, which
 * read green with every ETF stored and none known), then why an operating company has none.
 * Admin only; the server decides the shares and the causes.
 */
import {
  DataTable,
  EmptyState,
  ErrorState,
  formatValue,
  Panel,
  Skeleton,
  Stack,
} from '@algotrade/ui';

import { unknownText } from '@/entities/availability';
import { useKnownCoverage } from '@/entities/ingestion';
import { termHelp } from '@/features/guide-help';

import { gapColumns, typeColumns } from '../model/columns';

export function KnownCoveragePanel() {
  const coverage = useKnownCoverage();
  const served = coverage.data;
  const found = served && !served.unknown ? served : null;
  return (
    <Panel
      title="Known values · Fundamentals"
      description={
        served ? formatValue(served.session, { kind: 'date', style: 'weekday' }).text : ''
      }
      actions={termHelp('known_value_coverage')}
    >
      {coverage.isPending ? (
        <Skeleton variant="table" rows={4} columns={5} label="Loading known values…" />
      ) : coverage.isError ? (
        <ErrorState
          compact
          title="Known values could not load."
          detail={coverage.error.message}
          onRetry={() => void coverage.refetch()}
          retrying={coverage.isFetching}
        />
      ) : !found ? (
        <EmptyState
          compact
          title="No known-value counts for this session"
          description={
            served?.unknown
              ? `They are ${unknownText(served.unknown)}.`
              : 'The nightly run records them with its coverage checks.'
          }
        />
      ) : (
        <Stack gap={4}>
          <DataTable
            label="Fundamentals share count by security type"
            columns={typeColumns()}
            rows={found.byType}
            getRowId={(r) => r.securityType}
            visibleRows={Math.min(found.byType.length, 8)}
          />
          {found.gaps.length > 0 && (
            <DataTable
              label="Operating companies without a share count"
              columns={gapColumns()}
              rows={found.gaps}
              getRowId={(r) => r.gap}
              visibleRows={found.gaps.length}
            />
          )}
        </Stack>
      )}
    </Panel>
  );
}
