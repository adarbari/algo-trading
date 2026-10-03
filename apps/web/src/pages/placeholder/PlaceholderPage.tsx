/**
 * The placeholder for a section whose page is not built yet: its name and purpose. A page
 * composes widgets and features with design-system primitives: no HTML elements, no styling,
 * no data fetching of its own (ADR 0025).
 */
import { Stack, Text } from '@algotrade/ui';

export interface PlaceholderPageProps {
  title: string;
  summary: string;
}

export function PlaceholderPage({ title, summary }: PlaceholderPageProps) {
  return (
    <Stack gap={2}>
      <Text variant="title">{title}</Text>
      <Text tone="muted">{summary}</Text>
      <Text variant="caption" tone="muted">
        Not built yet: screens follow the approved mockups (ADR 0011).
      </Text>
    </Stack>
  );
}
