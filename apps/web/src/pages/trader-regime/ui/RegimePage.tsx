/**
 * Trader > Regime: the market as weather. The header (the weather word, its sentence, the
 * three scores, what changed this week), the slow and fast warning signs behind it, beside
 * the caller's sizing rules (read-only) and the reading list the cards cite.
 */
import { Grid, Heading, Stack, Text } from '@algotrade/ui';

import { ReadingList } from '@/widgets/reading-list';
import { RegimeHeader } from '@/widgets/regime-header';
import { RegimeIndicators } from '@/widgets/regime-indicators';
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
      <RegimeHeader />
      <Grid columns="main-aside" gap={4} collapse="lg" align="start">
        <RegimeIndicators />
        <Stack gap={3}>
          <RegimeSizing />
          <ReadingList />
        </Stack>
      </Grid>
    </Stack>
  );
}
