/** When the number lies: the guide's caveats, each naming the field that exposes it, in the warning tint. */
import { Banner, Stack, Text } from '@algotrade/ui';

export interface CaveatsPanelProps {
  caveats: readonly string[];
}

export function CaveatsPanel({ caveats }: CaveatsPanelProps) {
  return (
    <Banner tone="warning" title="When the number lies">
      <Stack gap={2}>
        {caveats.map((caveat) => (
          <Text key={caveat} as="p">
            {caveat}
          </Text>
        ))}
      </Stack>
    </Banner>
  );
}
