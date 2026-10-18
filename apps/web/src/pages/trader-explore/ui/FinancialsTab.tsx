/** The Explore Financials tab: the company's financials panel, loaded as its own chunk. */
import { FinancialsPanel } from '@/widgets/financials-panel';

export function FinancialsTab({ symbol }: { symbol: string }) {
  return <FinancialsPanel symbol={symbol} />;
}
