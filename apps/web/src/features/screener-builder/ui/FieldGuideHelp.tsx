/**
 * A field's guide under its criterion ("How to read it", opened on demand): how to read the
 * field, each guided intent with its criterion in words and a "Use" button that sets the row
 * to it, when the reading lies (the caveats, each naming the field that exposes it), and the
 * sources. The same guide the drafting model reads (ADR 0041 amended).
 */
import { Button, Disclosure, Mono, Stack, Text } from '@algotrade/ui';
import { useState } from 'react';

import type { CatalogueFeature, FieldGuide, GuideUse } from '@/entities/feature';

import { guideCriterionText, guideModeText } from '../model/guide';

export interface FieldGuideHelpProps {
  guide: FieldGuide;
  feature: CatalogueFeature;
  /** Set the criterion to this intent's operator, value, mode and tolerance. */
  onApply: (use: GuideUse) => void;
  disabled?: boolean;
}

export function FieldGuideHelp({ guide, feature, onApply, disabled = false }: FieldGuideHelpProps) {
  const [open, setOpen] = useState(false);
  return (
    <Disclosure label="How to read it" variant="plain" open={open} onOpenChange={setOpen}>
      {open && (
        <Stack gap={3} as="div">
          <Text size="sm" as="p">
            {guide.reads}
          </Text>
          {guide.uses.length > 0 && (
            <Stack gap={1} as="div">
              <Text size="sm" weight="medium" as="p">
                The criterion per intent
              </Text>
              <Stack gap={1} as="ul" aria-label="Guided intents">
                {guide.uses.map((use) => (
                  <Stack key={use.intent} direction="row" gap={2} align="baseline" wrap as="li">
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Use: ${use.intent}`}
                      onClick={() => {
                        onApply(use);
                      }}
                      disabled={disabled}
                    >
                      Use
                    </Button>
                    <Text size="sm">{use.intent}</Text>
                    <Mono size="xs" tone="secondary">
                      {guideCriterionText(use, feature)}
                    </Mono>
                    <Text size="xs" tone="muted">
                      {guideModeText(use, feature)}
                      {use.note ? ` · ${use.note}` : ''}
                    </Text>
                  </Stack>
                ))}
              </Stack>
            </Stack>
          )}
          {guide.caveats.length > 0 && (
            <Stack gap={1} as="div">
              <Text size="sm" weight="medium" as="p">
                When the reading lies
              </Text>
              <Stack gap={1} as="ul" aria-label="Caveats">
                {guide.caveats.map((caveat) => (
                  <Stack key={caveat} as="li">
                    <Text size="sm" tone="secondary">
                      {caveat}
                    </Text>
                  </Stack>
                ))}
              </Stack>
            </Stack>
          )}
          {guide.sources.length > 0 && (
            <Text size="xs" tone="muted" as="p">
              Sources: {guide.sources.join('; ')}
            </Text>
          )}
        </Stack>
      )}
    </Disclosure>
  );
}
