/** How it is computed: the definition, what a null means and the inputs. */
import { Mono, Panel, Stack, Text } from '@algotrade/ui';

import type { CatalogueFeature } from '@/entities/feature';

export interface ComputedPanelProps {
  feature: CatalogueFeature;
}

export function ComputedPanel({ feature }: ComputedPanelProps) {
  return (
    <Panel title="How it is computed">
      <Stack gap={2}>
        <Text as="p" tone="secondary">
          {feature.description}
        </Text>
        {feature.nullMeaning && (
          <Text size="sm" tone="muted">
            {`Null when: ${feature.nullMeaning}`}
          </Text>
        )}
        {feature.inputs.length > 0 && (
          <Stack gap={1}>
            <Text size="sm" tone="muted">
              Inputs:
            </Text>
            {feature.inputs.map((input) => (
              <Mono key={input} size="sm" tone="secondary">
                {input}
              </Mono>
            ))}
          </Stack>
        )}
      </Stack>
    </Panel>
  );
}
