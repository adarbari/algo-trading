/**
 * Related fields (links to their pages) and the playbooks that use the field, both derived by
 * the server (ADR 0038). A playbook is plain text with its rules until the playbook pages exist.
 */
import { Grid, Heading, Mono, Panel, Stack, Text, TextLink } from '@algotrade/ui';

import { fieldPath } from '@/entities/guide';

export interface RelatedPlaybook {
  id: string;
  name: string;
  rules: readonly string[];
}

export interface RelatedPanelProps {
  related: readonly string[];
  playbooks: readonly RelatedPlaybook[];
  state: 'loading' | 'error' | 'ready';
  onRetry: () => void;
}

export function RelatedPanel({ related, playbooks, state, onRetry }: RelatedPanelProps) {
  return (
    <Panel
      title="Related fields and playbooks"
      state={state}
      loadingLabel="Loading related fields"
      errorMessage="Related fields and playbooks failed to load."
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
        <Stack gap={2} as="section" aria-label="Playbooks that use it">
          <Heading level={3}>Playbooks that use it</Heading>
          {playbooks.length === 0 ? (
            <Text size="sm" tone="muted">
              No site screen uses this field.
            </Text>
          ) : (
            playbooks.map((playbook) => (
              <Stack key={playbook.id} gap={0}>
                <Text size="sm">{playbook.name}</Text>
                {playbook.rules.map((rule) => (
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
