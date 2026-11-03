/**
 * The Regime page's header: the weather word with its sentence, the three scores and the macro score's two tiers, and
 * "What changed this week": the indicators whose verdict turned on or off since five sessions
 * ago (the server's `changed`), each with its one-line meaning. Data, empty (nothing stored)
 * and error states; loading is a Skeleton.
 */
import { Heading, Panel, Skeleton, Stack, StatusBadge, Text } from '@algotrade/ui';

import {
  changedIndicators,
  indicatorStatus,
  RegimeHeadline,
  RegimeScoreMeter,
  useRegime,
  type Regime,
} from '@/entities/regime';
import { ExplainRegime } from '@/features/regime-explain';
import { termHelp } from '@/features/guide-help';

/** The macro score's two tiers, so a CAUTION the early tier carries shows while the cards read off. */
function MacroTiers({ regime }: { regime: Regime }) {
  return (
    <Stack gap={2}>
      <RegimeScoreMeter
        label="Early tier"
        caption={termHelp('macro_early')}
        score={regime.scores.macroEarly}
        banded
        size="sm"
      />
      <RegimeScoreMeter
        label="Confirming tier"
        caption={termHelp('macro_confirming')}
        score={regime.scores.macroConfirming}
        banded
        size="sm"
      />
    </Stack>
  );
}

function WhatChanged({ regime }: { regime: Regime }) {
  const changed = changedIndicators(regime);
  return (
    <Stack gap={2}>
      <Heading level={3} size="lg">
        What changed this week
      </Heading>
      {changed.length === 0 ? (
        <Text size="sm" tone="muted">
          {regime.label === 'UNKNOWN'
            ? 'Nothing to compare: the regime is not computed.'
            : 'No warning sign turned on or off in the last five sessions.'}
        </Text>
      ) : (
        <Stack as="ul" gap={2}>
          {changed.map((indicator) => {
            const status = indicatorStatus(indicator.status);
            return (
              <Stack as="li" key={indicator.key} direction="row" gap={2} align="baseline" wrap>
                <StatusBadge tone={status.tone}>{`Now ${status.label.toLowerCase()}`}</StatusBadge>
                <Text weight="medium">{indicator.plainName}</Text>
                <Text size="sm" tone="secondary">
                  {indicator.oneLiner}
                </Text>
              </Stack>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}

export function RegimeHeader() {
  const regime = useRegime();
  const state = regime.isError ? 'error' : regime.data === null ? 'empty' : 'ready';
  return (
    <Panel
      title="Market weather"
      description={regime.data ? `Session ${regime.data.session}` : undefined}
      state={state}
      emptyMessage="No regime is stored yet, so there is no weather to show."
      errorMessage="The market regime failed to load."
      onRetry={() => void regime.refetch()}
    >
      {regime.isPending && <Skeleton lines={6} label="Loading the market regime" />}
      {regime.data && (
        <Stack gap={4}>
          <RegimeHeadline regime={regime.data} macroTiers={<MacroTiers regime={regime.data} />} />
          <WhatChanged regime={regime.data} />
          {regime.data.label !== 'UNKNOWN' && <ExplainRegime />}
        </Stack>
      )}
    </Panel>
  );
}
