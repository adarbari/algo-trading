/**
 * Trader > Regime: the market as weather, and how to read it. The header (the weather word,
 * its sentence, the three scores, what changed this week), one legend for the colors of every
 * chart, the scores through the cycles, the slow and fast warning signs (each with its meter,
 * explanation, sources and history) beside the caller's sizing rules (read-only), the reference
 * market falls (a row sets every chart's window) and the reading list the cards cite.
 */
import { Grid, Heading, Stack, Text } from '@algotrade/ui';

import { RegimeRangeProvider } from '@/features/regime-range';
import { ReadingList } from '@/widgets/reading-list';
import { RegimeCycles } from '@/widgets/regime-cycles';
import { RegimeEpisodes } from '@/widgets/regime-episodes';
import { RegimeHeader } from '@/widgets/regime-header';
import { RegimeIndicators } from '@/widgets/regime-indicators';
import { RegimeLegend } from '@/widgets/regime-legend';
import { RegimeSizing } from '@/widgets/regime-sizing';

export function RegimePage() {
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Heading level={1}>Regime</Heading>
        <Text size="sm" tone="secondary">
          The market as weather, with the warning signs behind it in plain words. It sizes new
          positions and pauses some ideas; it never trades for you.
        </Text>
      </Stack>
      <RegimeRangeProvider>
        <RegimeHeader />
        <RegimeLegend />
        <RegimeCycles />
        <Grid columns="main-aside" gap={4} collapse="lg" align="start">
          <RegimeIndicators />
          <RegimeSizing />
        </Grid>
        <RegimeEpisodes />
        <ReadingList />
      </RegimeRangeProvider>
    </Stack>
  );
}
