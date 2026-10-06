/**
 * "Explain in plain words": a button that asks the text model for a short explanation of the
 * market weather (or of one card) and shows it as a well with the allowed links it cited and a
 * footer saying it is model text. Nothing is asked until the click. Where no text model is
 * configured (or the API refuses with 503) the button is not shown and the page keeps its
 * templated text; an answer whose numbers did not check out shows the API's note instead of
 * the text; any other refusal (too many requests, the model down) is said in one line.
 */
import { Banner, Button, ExternalLink, Stack, Surface, Text } from '@algotrade/ui';
import { useQueryClient } from '@tanstack/react-query';

import { ApiError, errorDetail } from '@/shared/api';

import { useExplainAvailable, useExplainRegime } from '../api/hooks';

export interface ExplainRegimeProps {
  /** A card key: explain that card; omitted: "what is happening?". */
  card?: string;
  /** The button's words (default "Explain in plain words"). */
  label?: string;
}

const FOOTER = 'Written by a text model from the facts on this page; it may be wrong.';
const AVAILABLE_KEY = ['regime-explain', 'available'] as const;

export function ExplainRegime({ card, label = 'Explain in plain words' }: ExplainRegimeProps) {
  const available = useExplainAvailable();
  const explain = useExplainRegime();
  const client = useQueryClient();
  if (available.data !== true) return null;
  const ask = () => {
    explain.mutate(
      { card },
      {
        onError: (error) => {
          if (error instanceof ApiError && error.status === 503) {
            client.setQueryData(AVAILABLE_KEY, false); // the model went away: hide the button
          }
        },
      },
    );
  };
  const answer = explain.data;
  return (
    <Stack gap={2} align="start">
      <Button size="sm" onClick={ask} loading={explain.isPending}>
        {label}
      </Button>
      {explain.isError && !(explain.error instanceof ApiError && explain.error.status === 503) && (
        <Banner tone="negative">{errorDetail(explain.error)}</Banner>
      )}
      {answer && !answer.checked && (
        <Text size="sm" tone="muted">
          {answer.note ?? 'The explanation could not be checked, so it is not shown.'}
        </Text>
      )}
      {answer?.checked && (
        <Surface tone="row" border="all" radius="md" padding={3}>
          <Stack gap={2}>
            <Text>{answer.text}</Text>
            {answer.citations.length > 0 && (
              <Stack as="ul" direction="row" gap={3} wrap>
                {answer.citations.map((citation) => (
                  <Stack as="li" key={citation.url}>
                    <ExternalLink size="sm" href={citation.url}>
                      {citation.title}
                    </ExternalLink>
                  </Stack>
                ))}
              </Stack>
            )}
            <Text size="sm" tone="muted">
              {FOOTER}
            </Text>
          </Stack>
        </Surface>
      )}
    </Stack>
  );
}
