/**
 * The CSV button of the trade ledger: saves the trades of the period shown as a file, and says
 * when the file could not be saved. States: idle, saving, failed.
 */
import { Button, Stack, Text } from '@algotrade/ui';

import type { TradePeriod } from '@/entities/edge';

import { useTradesCsv } from '../api/use-trades-csv';

export interface TradesCsvButtonProps {
  edgeId: string;
  period: TradePeriod;
}

export function TradesCsvButton({ edgeId, period }: TradesCsvButtonProps) {
  const csv = useTradesCsv(edgeId);
  return (
    <Stack direction="row" gap={1} align="center">
      <Button
        size="sm"
        variant="secondary"
        loading={csv.isPending}
        onClick={() => {
          csv.mutate(period);
        }}
      >
        CSV
      </Button>
      {csv.isError && <Text tone="negative">The file could not be saved.</Text>}
    </Stack>
  );
}
