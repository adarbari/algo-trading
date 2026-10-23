/** The events list under the Explore chart, loaded as its own chunk after the chart itself. */
import type { ChartRange } from '@algotrade/ui';

import { rangeFrom } from '@/entities/instrument';
import { ChartEventListPanel } from '@/widgets/chart-event-list';

export function ChartEventsSection({ symbol, range }: { symbol: string; range: ChartRange }) {
  return <ChartEventListPanel symbol={symbol} from={rangeFrom(range)} />;
}
