/**
 * Trader > Setups (the Edges page; the UI says setup, the code edge): the library (Start here, the
 * setups grouped by verdict) and the chosen setup's page in place of it (a back link returns). The chosen edge comes from the route
 * (shareable).
 */
import { Button, Heading, Stack, Text } from '@algotrade/ui';

import {
  SetupLibrary,
  type SetupLibrarySearch,
  type SetupLibrarySearchPatch,
} from '@/widgets/setup-library';

import { EdgePage } from './EdgePage';

export interface EdgesPageProps {
  /** The chosen edge (from the URL), or null for the list. */
  selected?: string | null;
  onSelect: (id: string) => void;
  /** Open the builder on one of the user's edges (null: a new edge). */
  onBuild: (id: string | null) => void;
  /** Back to the list: the route clears the choice. */
  onClear: () => void;
  /** The list's filters and search (from the URL) and their change. */
  search: SetupLibrarySearch;
  onSearchChange: (patch: SetupLibrarySearchPatch) => void;
}

export function EdgesPage({
  selected = null,
  onSelect,
  onBuild,
  onClear,
  search,
  onSearchChange,
}: EdgesPageProps) {
  if (selected !== null) return <EdgePage id={selected} onBack={onClear} onEdit={onBuild} />;
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} align="center" justify="between" wrap>
        <Stack gap={1}>
          <Heading level={1}>Setups</Heading>
          <Text size="sm" tone="secondary">
            Published setups: a written idea, the rules that find it, and its evidence
          </Text>
        </Stack>
        <Button
          variant="primary"
          onClick={() => {
            onBuild(null);
          }}
        >
          Test your own idea
        </Button>
      </Stack>
      <SetupLibrary onSelect={onSelect} search={search} onSearchChange={onSearchChange} />
    </Stack>
  );
}
