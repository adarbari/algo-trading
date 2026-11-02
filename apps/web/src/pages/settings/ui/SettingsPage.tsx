/**
 * Settings (from the account menu): theme, the Ideas tab that opens first, the watchlist, the
 * country (read-only: the service is for US residents) and sign out. Display preferences only:
 * nothing stored here is a position, a size or an account (ADR 0083, amendment 2026-11-01).
 */
import { Button, Divider, Heading, SegmentedControl, Stack, Surface, Text } from '@algotrade/ui';

import {
  useSaveIdeasTab,
  useTraderPreferences,
  type IdeasTab,
} from '@/entities/trader-preferences';
import { useSession, useSignOut } from '@/entities/viewer';
import { Labelled } from '@/features/guide-help';
import { ThemeChoice } from '@/widgets/theme-choice';
import { WatchlistEditor } from '@/widgets/watchlist-editor';

const TABS = [
  { value: 'stocks', label: 'Stocks' },
  { value: 'premium', label: 'Premium' },
] as const satisfies readonly { value: IdeasTab; label: string }[];

export function SettingsPage() {
  const prefs = useTraderPreferences();
  const saveTab = useSaveIdeasTab();
  const { session } = useSession();
  const signOut = useSignOut();
  return (
    <Stack gap={3}>
      <Heading level={1}>Settings</Heading>
      <Surface>
        <Stack gap={3}>
          <ThemeChoice />
          <Divider />
          <Stack gap={1}>
            <Labelled text="Start tab" help="start_tab" />
            <SegmentedControl
              aria-label="Start tab"
              size="sm"
              options={TABS}
              value={prefs.data?.defaultTab ?? 'stocks'}
              disabled={prefs.data === undefined}
              onValueChange={(tab) => {
                saveTab.mutate(tab);
              }}
            />
          </Stack>
          <Divider />
          <Stack gap={1}>
            <Labelled text="Watchlist" help="watchlist" />
            <WatchlistEditor />
          </Stack>
        </Stack>
      </Surface>
      <Surface>
        <Stack gap={3}>
          <Stack gap={1}>
            <Labelled text="Country" help="country" />
            <Text>United States</Text>
          </Stack>
          {session ? (
            <>
              <Divider />
              <Stack direction="row">
                <Button
                  variant="secondary"
                  onClick={() => {
                    void signOut();
                  }}
                >
                  Sign out
                </Button>
              </Stack>
            </>
          ) : null}
        </Stack>
      </Surface>
    </Stack>
  );
}
