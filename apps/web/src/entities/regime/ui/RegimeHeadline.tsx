/**
 * The regime's headline: the weather word in its tone, the one sentence under it (the server's
 * words, never composed here) and the three scores as meters (macro risk, market stress, and
 * fragility, which is context only and never changes the label). A score the server could not
 * give shows its reason. The meters' bands are display marks on the 0-100 scales.
 */
import type { ReactNode } from 'react';

import { Heading, ScoreMeter, Stack, StatusBadge, Text, type ScoreThreshold } from '@algotrade/ui';

import { UnknownNote, unknownText } from '@/entities/availability';

import { plainLabel, regimeTone, type Regime, type RegimeScore } from '../model/regime';

/** Where a score reads as caution and as stress on its 0-100 scale. */
const BANDS: readonly ScoreThreshold[] = [
  { at: 50, label: 'caution', tone: 'warning' },
  { at: 75, label: 'stress', tone: 'negative' },
];

export interface RegimeHeadlineProps {
  regime: Regime;
  /** Rendered under the macro-risk meter: the app's view of its two tiers (a widget supplies it). */
  macroTiers?: ReactNode;
}

/** One score as a meter on the 0-100 scale; `banded` marks caution and stress on it. */
export function RegimeScoreMeter({
  label,
  caption,
  score,
  banded,
  size = 'md',
}: {
  label: string;
  caption: ReactNode;
  score: RegimeScore;
  banded: boolean;
  size?: 'sm' | 'md';
}) {
  return (
    <ScoreMeter
      label={label}
      value={score.value}
      caption={caption}
      size={size}
      unknownReason={unknownText(score.unknown)}
      {...(banded ? { thresholds: BANDS, baseTone: 'positive', baseLabel: 'calm' } : {})}
    />
  );
}

export function RegimeHeadline({ regime, macroTiers }: RegimeHeadlineProps) {
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
        {regime.unknownReason && <UnknownNote unknown={regime.unknownReason} />}
      </Stack>
      <Stack gap={3}>
        <RegimeScoreMeter
          label="Slow-warning score"
          caption="Macro risk: credit, labour, the yield curve. Moves over weeks."
          score={scores.macroRisk}
          banded
        />
        {macroTiers}
        <RegimeScoreMeter
          label="Market stress score"
          caption="Trend, volatility, breadth. Moves daily."
          score={scores.marketStress}
          banded
        />
        <RegimeScoreMeter
          label="Fragility"
          caption="Context only: how deep a fall from here could be. Never changes the label."
          score={scores.fragility}
          banded={false}
        />
      </Stack>
    </Stack>
  );
}
