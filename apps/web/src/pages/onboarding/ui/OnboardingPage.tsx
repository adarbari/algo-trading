/**
 * The one sign-up question, shown on the first signed-in visit (no stored start tab): mostly
 * shares or mostly options. The answer picks the Ideas tab that opens first (ADR 0083,
 * amendment 2026-11-01); Skip answers shares. Choice cards are the design system's OptionList
 * until its card variant (C15) lands.
 */
import { Button, Heading, OptionList, Stack, useToast } from '@algotrade/ui';

import { useSaveIdeasTab, type IdeasTab } from '@/entities/trader-preferences';
import { Labelled } from '@/features/guide-help';

const CHOICES = [
  { id: 'stocks', title: 'Mostly shares' },
  { id: 'premium', title: 'Mostly options (selling premium)' },
] as const satisfies readonly { id: IdeasTab; title: string }[];

export function OnboardingPage({ onDone }: { onDone: () => void }) {
  const save = useSaveIdeasTab();
  const toast = useToast();
  const answer = (tab: IdeasTab) => {
    save.mutate(tab, {
      onSuccess: onDone,
      onError: () => {
        toast.show({ tone: 'warning', title: 'Not saved: try again.' });
      },
    });
  };
  return (
    <Stack gap={3}>
      <Heading level={1}>What do you trade?</Heading>
      <Labelled text="Mostly shares or mostly options?" help="trade_mix" />
      <OptionList
        label="Mostly shares or mostly options?"
        items={CHOICES}
        value={null}
        onSelect={(id) => {
          answer(id === 'premium' ? 'premium' : 'stocks');
        }}
      />
      <Stack direction="row">
        <Button
          variant="ghost"
          onClick={() => {
            answer('stocks');
          }}
        >
          Start with shares
        </Button>
      </Stack>
    </Stack>
  );
}
