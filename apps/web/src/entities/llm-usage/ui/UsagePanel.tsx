/**
 * A panel over the usage read: it asks for the one shared operation and draws loading, error and
 * empty (nothing recorded yet) for its body, which receives the loaded usage. Every usage widget
 * is one of these, so the page never sits on a spinner and a failed read says so once per panel.
 */
import { EmptyState, ErrorState, Panel, Skeleton } from '@algotrade/ui';
import type { ReactNode } from 'react';

import { useLlmUsage } from '../api/queries';
import type { LlmUsage } from '../model/types';

export interface UsagePanelProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** The body needs recorded calls (default); false: it also reads the caps with none recorded. */
  needsCalls?: boolean;
  /** Placeholder rows while loading. */
  rows?: number;
  /** The body is a table that runs to the panel's edges. */
  flush?: boolean;
  children: (usage: LlmUsage) => ReactNode;
}

export function UsagePanel({
  title,
  description,
  actions,
  needsCalls = true,
  rows = 4,
  flush = false,
  children,
}: UsagePanelProps) {
  const query = useLlmUsage();
  const usage = query.data;
  return (
    <Panel
      title={title}
      description={description}
      actions={actions}
      flush={flush && Boolean(usage?.recorded)}
    >
      {query.isPending ? (
        <Skeleton variant="table" rows={rows} columns={4} label="Loading text-model usage…" />
      ) : query.isError ? (
        <ErrorState
          compact
          title="Text-model usage could not load."
          detail={query.error.message}
          onRetry={() => void query.refetch()}
          retrying={query.isFetching}
        />
      ) : !usage ? (
        <EmptyState compact title="No usage to show" description="The store could not be read." />
      ) : needsCalls && !usage.recorded ? (
        <EmptyState
          compact
          title="No text-model calls recorded yet"
          description="Each call, paid or free, is logged here once it is made."
        />
      ) : (
        children(usage)
      )}
    </Panel>
  );
}
