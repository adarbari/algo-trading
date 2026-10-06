/**
 * The detail under one indicator row: why it matters, what "on" means, what it did before
 * past falls, its lead time and false alarms, a button to have it explained in plain words (when
 * the regime is computed and a text model is configured), and where to read more. Plain text from the
 * card (config/site/regime/cards.toml, reviewed by PR).
 */
import { ExternalLink, Heading, Stack, Text } from '@algotrade/ui';

import type { RegimeIndicator } from '@/entities/regime';
import { ExplainRegime } from '@/features/regime-explain';

export function IndicatorDetail({
  indicator,
  explainable,
}: {
  indicator: RegimeIndicator;
  /** The regime is computed, so the card can be explained on request. */
  explainable: boolean;
}) {
  return (
    <Stack gap={2}>
      <Text size="sm">{indicator.whyItMatters}</Text>
      <Text size="sm" tone="secondary">
        {`When it is on: ${indicator.whatOnMeans}`}
      </Text>
      {indicator.before.length > 0 && (
        <Stack gap={1}>
          <Heading level={4} size="sm" tone="muted">
            What it did before
          </Heading>
          <Stack as="ul" gap={1}>
            {indicator.before.map((entry) => (
              <Stack as="li" key={entry.episode}>
                <Text size="sm" tone="secondary">{`${entry.episode}: ${entry.line}`}</Text>
              </Stack>
            ))}
          </Stack>
        </Stack>
      )}
      <Text size="sm" tone="secondary">{`Lead time: ${indicator.leadTime}`}</Text>
      <Text size="sm" tone="secondary">{`False alarms: ${indicator.falseAlarms}`}</Text>
      {explainable && <ExplainRegime card={indicator.key} label="Explain this in plain words" />}
      {indicator.links.length > 0 && (
        <Stack as="ul" gap={1}>
          {indicator.links.map((link) => (
            <Stack as="li" key={link.url}>
              <ExternalLink size="sm" href={link.url}>
                {link.title}
              </ExternalLink>
            </Stack>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
