/**
 * Trader > Regime: one scroll in three parts under a sticky section nav. NOW: the market as
 * weather (the weather word, its sentence, the three scores, what changed this week). WHY: the slow and fast warning signs, each a compact row that
 * opens to its meter, sources and history (a help button opens each one's Guide entry). HISTORY:
 * one legend for the colors of every chart, the scores through the cycles, the reference market
 * falls (a row sets every chart's window) and how early each sign flagged around each fall.
 */
import { Box, Heading, SectionNav, Stack, Text } from '@algotrade/ui';

import { RegimeRangeProvider } from '@/features/regime-range';
import { RegimeCycles } from '@/widgets/regime-cycles';
import { RegimeEpisodes } from '@/widgets/regime-episodes';
import { RegimeHeader } from '@/widgets/regime-header';
import { RegimeIndicators } from '@/widgets/regime-indicators';
import { RegimeLegend } from '@/widgets/regime-legend';
import { RegimeTiming } from '@/widgets/regime-timing';

const SECTIONS = [
  { id: 'regime-now', label: 'Now' },
  { id: 'regime-why', label: 'Why' },
  { id: 'regime-history', label: 'History' },
];

export function RegimePage() {
  return (
    <Stack gap={3}>
      <Stack gap={1}>
        <Heading level={1}>Regime</Heading>
        <Text size="sm" tone="secondary">
          The market as weather, with the warning signs behind it in plain words. It can pause some
          ideas; it never trades for you.
        </Text>
      </Stack>
      <SectionNav items={SECTIONS} aria-label="Regime sections" />
      <RegimeRangeProvider>
        <Box as="section" id="regime-now" aria-label="Now">
          <RegimeHeader />
        </Box>
        <Box as="section" id="regime-why" aria-label="Why">
          <Stack gap={3}>
            <Heading level={2}>Why</Heading>
            <RegimeIndicators />
          </Stack>
        </Box>
        <Box as="section" id="regime-history" aria-label="History">
          <Stack gap={3}>
            <Heading level={2}>History</Heading>
            <RegimeLegend />
            <RegimeCycles />
            <RegimeEpisodes />
            <RegimeTiming />
          </Stack>
        </Box>
      </RegimeRangeProvider>
    </Stack>
  );
}
