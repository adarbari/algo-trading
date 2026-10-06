/**
 * The regime's headline: the weather word in its tone, the one sentence under it (the server's
 * words, never composed here) and the three scores as meters (macro risk, market stress, and
 * fragility, which is context only and never changes the label). A score the server could not
 * give shows its reason. The meters' bands are display marks on the 0-100 scales.
 */
import { Heading, ScoreMeter, Stack, StatusBadge, Text, type ScoreThreshold } from '@algotrade/ui';

import { plainLabel, regimeTone, type Regime, type RegimeScore } from '../model/regime';

/** Where a score reads as caution and as stress on its 0-100 scale. */
const BANDS: readonly ScoreThreshold[] = [
  { at: 50, label: 'caution', tone: 'warning' },
  { at: 75, label: 'stress', tone: 'negative' },
];

export interface RegimeHeadlineProps {
  regime: Regime;
}

function Meter({
  label,
  caption,
  score,
  banded,
}: {
  label: string;
  caption: string;
  score: RegimeScore;
  banded: boolean;
}) {
  return (
    <ScoreMeter
      label={label}
      value={score.value}
      caption={caption}
      size="md"
      unknownReason={score.unknown?.detail ?? 'Not available'}
      {...(banded ? { thresholds: BANDS, baseTone: 'positive', baseLabel: 'calm' } : {})}
    />
  );
}

export function RegimeHeadline({ regime }: RegimeHeadlineProps) {
  const { scores } = regime;
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Stack direction="row" gap={2} align="center">
          <Heading level={3} size="3xl">
            {plainLabel(regime.label)}
          </Heading>
          <StatusBadge tone={regimeTone(regime.label)}>{regime.label}</StatusBadge>
        </Stack>
        <Text tone="secondary">{regime.headline}</Text>
        {regime.unknownReason && (
          <Text size="sm" tone="muted">
            {regime.unknownReason.detail}
          </Text>
        )}
      </Stack>
      <Stack gap={3}>
        <Meter
          label="Slow-warning score"
          caption="Macro risk: credit, labour, the yield curve. Moves over weeks."
          score={scores.macroRisk}
          banded
        />
        <Meter
          label="Market stress score"
          caption="Trend, volatility, breadth. Moves daily."
          score={scores.marketStress}
          banded
        />
        <Meter
          label="Fragility"
          caption="Context only: how deep a fall from here could be. Never changes the label."
          score={scores.fragility}
          banded={false}
        />
      </Stack>
    </Stack>
  );
}
