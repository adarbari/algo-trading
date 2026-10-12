/**
 * The requested features in the server's ranking, with a status filter (a view over the rows the
 * server sent: nothing is counted or re-ranked here). The chosen status lives in the URL.
 */
import { DataTable, Panel, SegmentedControl } from '@algotrade/ui';
import { useMemo } from 'react';

import {
  isRequestStatus,
  START_PAGE,
  STATUS_LABEL,
  STATUSES,
  useFeatureRequests,
  type FeatureRequest,
  type RequestStatus,
} from '@/entities/feature-request';
import { GuideHelp } from '@/features/guide-help';

import { requestColumns } from '../model/columns';

export interface FeatureRequestListProps {
  /** The status shown (from the URL); null, or one the server does not serve: every status. */
  status?: string | null;
  onStatusChange: (status: RequestStatus | null) => void;
}

type View = 'ALL' | RequestStatus;

export function FeatureRequestList({ status, onStatusChange }: FeatureRequestListProps) {
  const requests = useFeatureRequests();
  const columns = useMemo(() => requestColumns(), []);
  const all = requests.data?.rows ?? [];
  const shown = isRequestStatus(status) ? status : null;
  const rows = shown ? all.filter((r) => r.status === shown) : all;
  const state =
    requests.isError && !requests.data
      ? 'error'
      : requests.isPending
        ? 'loading'
        : rows.length === 0
          ? 'empty'
          : 'ready';
  return (
    <Panel
      title="Feature requests"
      flush
      state={state}
      loadingLabel="Loading feature requests…"
      emptyMessage={
        all.length === 0 ? 'No feature has been requested.' : 'No request has this status.'
      }
      errorMessage="The feature requests failed to load."
      onRetry={() => void requests.refetch()}
      actions={
        <>
          <SegmentedControl<View>
            aria-label="Status"
            size="sm"
            value={shown ?? 'ALL'}
            onValueChange={(v) => {
              onStatusChange(v === 'ALL' ? null : v);
            }}
            options={[
              { value: 'ALL', label: 'All' },
              ...STATUSES.map((s) => ({ value: s, label: STATUS_LABEL[s] })),
            ]}
          />
          <GuideHelp entry={{ kind: 'start', id: START_PAGE }} />
        </>
      }
    >
      <DataTable<FeatureRequest>
        label="Feature requests"
        columns={columns}
        rows={rows}
        getRowId={(r) => r.ref}
        getRowLabel={(r) => r.ref}
        sortMode="client"
        emptyMessage="No request has this status."
      />
    </Panel>
  );
}
