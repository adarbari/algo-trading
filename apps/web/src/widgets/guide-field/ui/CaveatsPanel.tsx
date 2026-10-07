/**
 * When the number lies: the guide's caveats, each naming the field that exposes it, in the
 * warning tint, then the situations that fool it (the server picks them; ADR 0038). A field with
 * neither says so in one line.
 */
import { Banner, Stack, Text } from '@algotrade/ui';

export interface CaveatsPanelProps {
  caveats: readonly string[];
  /** The situations that fool the field: how each shows itself. */
  situations: readonly { name: string; signs: string }[];
}

export function CaveatsPanel({ caveats, situations }: CaveatsPanelProps) {
  if (caveats.length === 0 && situations.length === 0) {
    return (
      <Text size="sm" tone="muted">
        The guide lists no caveat for this field yet.
      </Text>
    );
  }
  return (
    <Banner tone="warning" title="When it lies">
      <Stack gap={2}>
        {caveats.map((caveat) => (
          <Text key={caveat} as="p">
            {caveat}
          </Text>
        ))}
        {situations.length > 0 && (
          <Stack gap={1}>
            <Text weight="medium">Situations that fool it</Text>
            {situations.map((situation) => (
              <Text key={situation.name} as="p" size="sm">
                <Text weight="medium">{situation.name}</Text>
                {`: ${situation.signs}`}
              </Text>
            ))}
          </Stack>
        )}
      </Stack>
    </Banner>
  );
}
