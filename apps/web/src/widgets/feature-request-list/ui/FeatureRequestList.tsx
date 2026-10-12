/**
 * The requested features in the server's ranking, with a status filter (a view over the rows the
 * server sent: nothing is counted or re-ranked here).
 */
import { DataTable, Panel, SegmentedControl } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import {
  START_PAGE,
  STATUS_LABEL,
  STATUSES,
  useFeatureRequests,
  type FeatureRequest,
  type RequestStatus,
} from '@/entities/feature-request';
import { GuideHelp } from '@/features/guide-help';

import { requestColumns } from '../model/columns';

type View = 'ALL' | RequestStatus;

export function FeatureRequestList() {
  const [status, setStatus] = useState<RequestStatus | null>(null);
  const requests = useFeatureRequests();
  const columns = useMemo(() => requestColumns(), []);
  const all = requests.data?.rows ?? [];
  const rows = status ? all.filter((r) => r.status === status) : all;
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
            value={status ?? 'ALL'}
            onValueChange={(v) => {
              setStatus(v === 'ALL' ? null : v);
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
