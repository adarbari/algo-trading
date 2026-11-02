/** The source line under an option calculator: what the prices are, and that these are calculations. */
import { Text } from '@algotrade/ui';

export function CalculatorFooter() {
  return (
    <Text size="sm" tone="muted">
      Middle prices from tonight&apos;s end-of-day chain; real fills are worse; calculations, not
      results or recommendations.
    </Text>
  );
}
