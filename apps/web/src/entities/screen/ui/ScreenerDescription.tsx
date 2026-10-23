/** A screener's one-line description under its name, clamped to two lines (the Screeners list row and the Builder's preview of it). */
import { LineClamp, Text } from '@algotrade/ui';

export interface ScreenerDescriptionProps {
  description: string;
}

export function ScreenerDescription({ description }: ScreenerDescriptionProps) {
  return (
    <LineClamp title={description}>
      <Text as="p" size="sm" tone="secondary">
        {description}
      </Text>
    </LineClamp>
  );
}
