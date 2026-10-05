/**
 * Trader > Screeners > one screener (Results, `/screeners/$id`): the latest run as a review
 * table, with "Edit criteria" for the Builder. Reviewing comes first, editing is one click away.
 */
import { Button, Heading, Stack, Text } from '@algotrade/ui';

import { ScreenerResults } from '@/widgets/screener-results';

export interface ScreenerResultsPageProps {
  /** The screener shown. */
  id: string;
  /** Open the Builder for this screener. */
  onEdit: () => void;
  /** Open a ticker in Explore. */
  onOpenTicker: (symbol: string) => void;
}

export function ScreenerResultsPage({ id, onEdit, onOpenTicker }: ScreenerResultsPageProps) {
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} align="center" justify="between" wrap>
        <Stack gap={1}>
          <Heading level={1}>{id}</Heading>
          <Text size="sm" tone="secondary">
            What this screener found in its latest run. Add any catalogue feature as a column; your
            columns and filters are saved as your view of it.
          </Text>
        </Stack>
        <Button variant="secondary" onClick={onEdit}>
          Edit criteria
        </Button>
      </Stack>
      <ScreenerResults id={id} onOpen={onOpenTicker} />
    </Stack>
  );
}
