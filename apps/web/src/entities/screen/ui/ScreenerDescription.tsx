/** A screener's one-line description under its name, clamped to two lines (the Screeners list row and the Builder's preview of it). */
import { Text } from '@algotrade/ui';

export interface ScreenerDescriptionProps {
  description: string;
}

export function ScreenerDescription({ description }: ScreenerDescriptionProps) {
  return (
    <Text as="p" size="sm" tone="secondary" clamp={2}>
      {description}
    </Text>
  );
}
