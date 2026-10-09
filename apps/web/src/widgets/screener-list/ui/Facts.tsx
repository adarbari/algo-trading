/**
 * Label and value pairs of an opened row, one per line, the value at the end: the rows of a
 * section (criteria and their rules, today's decision counts, the track record's figures).
 */
import { Stack, Text } from '@algotrade/ui';
import type { ReactNode } from 'react';

export interface Fact {
  id: string;
  label: ReactNode;
  value: ReactNode;
}

export interface FactsProps {
  facts: readonly Fact[];
  /** Accessible name of the list. */
  label: string;
  loading?: boolean;
  /** Shown when there are no facts. */
  emptyMessage?: string;
}

export function Facts({ facts, label, loading = false, emptyMessage = 'None' }: FactsProps) {
  if (loading) {
    return (
      <Text size="sm" tone="muted">
        Loading…
      </Text>
    );
  }
  if (facts.length === 0) {
    return (
      <Text size="sm" tone="muted">
        {emptyMessage}
      </Text>
    );
  }
  return (
    <Stack as="ul" gap={1} aria-label={label}>
      {facts.map((fact) => (
        <Stack as="li" key={fact.id} direction="row" gap={3} justify="between" align="baseline">
          <Text size="sm" tone="secondary">
            {fact.label}
          </Text>
          <Text size="sm">{fact.value}</Text>
        </Stack>
      ))}
    </Stack>
  );
}
