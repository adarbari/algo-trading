/**
 * The placeholder for a section whose page is not built yet: its name and purpose. A page
 * composes widgets and features with design-system primitives: no HTML elements, no styling,
 * no data fetching of its own (ADR 0025).
 */
import { Heading, Stack, Text } from '@algotrade/ui';

export interface PlaceholderPageProps {
  title: string;
  summary: string;
}

export function PlaceholderPage({ title, summary }: PlaceholderPageProps) {
  return (
    <Stack gap={2}>
      <Heading level={1}>{title}</Heading>
      <Text as="p" tone="secondary">
        {summary}
      </Text>
      <Text as="p" size="sm" tone="muted">
        Not built yet: screens are composed from design-system components (ADR 0011).
      </Text>
    </Stack>
  );
}
