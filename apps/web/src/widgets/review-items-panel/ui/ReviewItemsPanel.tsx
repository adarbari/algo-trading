/**
 * The owner's open review items: FIGI conflicts from the universe build and leveraged / inverse
 * ETFs whose leverage needs curating. Each list is a Disclosure with its count and the items.
 */
import {
  DataTable,
  Disclosure,
  ErrorState,
  formatValue,
  Panel,
  Skeleton,
  Stack,
  Text,
  type DataTableColumn,
} from '@algotrade/ui';

import { reviewItems, useFigiReview, useLeveragedReview, type ReviewItem } from '@/entities/review';

const COLUMNS: DataTableColumn<ReviewItem>[] = [
  { id: 'symbol', header: 'Symbol', value: (i) => i.symbol, mono: true, width: 'sm' },
  { id: 'detail', header: 'Why', value: (i) => i.detail, tone: 'secondary', grow: true },
];

type ReviewQuery = ReturnType<typeof useFigiReview>;

function ReviewList({ title, hint, query }: { title: string; hint: string; query: ReviewQuery }) {
  if (query.isPending) return <Skeleton lines={2} label={`Loading ${title}…`} />;
  if (query.isError) {
    return (
      <ErrorState
        compact
        title={`${title} could not load.`}
        detail={query.error.message}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }
  const items = reviewItems(query.data);
  return (
    <Disclosure
      label={title}
      count={formatValue(items.length, { kind: 'number' }).text}
      countTone={items.length > 0 ? 'warning' : 'positive'}
    >
      <Stack gap={2}>
        <Text size="sm" tone="muted">
          {hint}
        </Text>
        {items.length > 0 && (
          <DataTable
            label={title}
            columns={COLUMNS}
            rows={items}
            getRowId={(i) => i.symbol}
            visibleRows={Math.min(items.length, 8)}
          />
        )}
      </Stack>
    </Disclosure>
  );
}

export function ReviewItemsPanel() {
  const figi = useFigiReview();
  const leveraged = useLeveragedReview();
  const session = figi.data?.session ?? leveraged.data?.session;
  return (
    <Panel
      title="Open review items"
      description={
        session
          ? `as of ${formatValue(session, { kind: 'date', style: 'weekday' }).text}`
          : undefined
      }
    >
      <Stack gap={2}>
        <ReviewList
          title="FIGI reviews"
          hint="Symbols whose FIGI is shared or changed: decide which instrument keeps the id."
          query={figi}
        />
        <ReviewList
          title="Leveraged ETFs to curate"
          hint="Leveraged or inverse funds whose leverage the name rules could not settle."
          query={leveraged}
        />
      </Stack>
    </Panel>
  );
}
