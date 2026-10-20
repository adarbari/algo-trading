/**
 * Related fields (links to their pages) and the screeners that use the field, both derived by
 * the server (ADR 0038); a screener links to its page.
 */
import { Grid, Heading, Mono, Panel, Stack, Text, TextLink } from '@algotrade/ui';

import { fieldPath, screenerPath } from '@/entities/guide';

export interface RelatedScreener {
  id: string;
  name: string;
  rules: readonly string[];
}

export interface RelatedPanelProps {
  related: readonly string[];
  screeners: readonly RelatedScreener[];
  state: 'loading' | 'error' | 'ready';
  onRetry: () => void;
}

export function RelatedPanel({ related, screeners, state, onRetry }: RelatedPanelProps) {
  return (
    <Panel
      title="Related fields and screeners"
      state={state}
      loadingLabel="Loading related fields"
      errorMessage="Related fields and screeners failed to load."
      onRetry={onRetry}
    >
      <Grid columns={2} gap={4} collapse="md" align="start">
        <Stack gap={2} as="section" aria-label="Related fields">
          <Heading level={3}>Related fields</Heading>
          {related.length === 0 ? (
            <Text size="sm" tone="muted">
              The guide names no related field.
            </Text>
          ) : (
            related.map((name) => (
              <TextLink key={name} href={fieldPath(name)} mono size="sm">
                {name}
              </TextLink>
            ))
          )}
        </Stack>
        <Stack gap={2} as="section" aria-label="Screeners that use it">
          <Heading level={3}>Screeners that use it</Heading>
          {screeners.length === 0 ? (
            <Text size="sm" tone="muted">
              No site screen uses this field.
            </Text>
          ) : (
            screeners.map((screener) => (
              <Stack key={screener.id} gap={0}>
                <TextLink href={screenerPath(screener.id)} size="sm">
                  {screener.name}
                </TextLink>
                {screener.rules.map((rule) => (
                  <Mono key={rule} size="sm" tone="muted">
                    {rule}
                  </Mono>
                ))}
              </Stack>
            ))
          )}
        </Stack>
      </Grid>
    </Panel>
  );
}
