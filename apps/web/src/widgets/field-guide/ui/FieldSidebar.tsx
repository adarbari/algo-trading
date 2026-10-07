/**
 * The way into the catalogue: a search over names, titles, descriptions and the guide's text, the
 * themes as toggle chips with their field counts, and the chosen theme's fields (name and one-line
 * meaning) in a list that scrolls inside the sidebar.
 */
import { Chip, OptionList, SearchInput, Stack, Surface, Text } from '@algotrade/ui';

import { shortMeaning, type CatalogueFeature, type GuideTheme } from '@/entities/feature';

export interface FieldSidebarProps {
  query: string;
  onQueryChange: (query: string) => void;
  /** The themes with how many fields of each match the query. */
  themes: readonly GuideTheme[];
  theme: string;
  onThemeChange: (theme: string) => void;
  /** The chosen theme's fields that match the query. */
  fields: readonly CatalogueFeature[];
  field: string | null;
  onFieldChange: (name: string) => void;
}

export function FieldSidebar({
  query,
  onQueryChange,
  themes,
  theme,
  onThemeChange,
  fields,
  field,
  onFieldChange,
}: FieldSidebarProps) {
  return (
    <Surface as="aside" aria-label="Find a field" radius="lg" padding={3}>
      <Stack gap={3}>
        <SearchInput
          aria-label="Search fields and what they mean"
          placeholder="Search fields and what they mean"
          value={query}
          onValueChange={onQueryChange}
        />
        <Stack direction="row" gap={1} wrap>
          {themes.map((t) => (
            <Chip
              key={t.name}
              label={`${t.name} ${String(t.count)}`}
              selected={t.name === theme}
              onSelectedChange={() => {
                onThemeChange(t.name);
              }}
            />
          ))}
        </Stack>
        <Text size="sm" tone="muted">
          {`${theme} · ${String(fields.length)} ${fields.length === 1 ? 'field' : 'fields'}`}
        </Text>
        <OptionList
          label={`Fields in ${theme}`}
          mono
          maxHeight="lg"
          items={fields.map((f) => ({
            id: f.name,
            title: f.name,
            description: shortMeaning(f),
          }))}
          value={field}
          onSelect={onFieldChange}
          emptyMessage={
            query ? `No field in ${theme} matches “${query}”.` : `No fields in ${theme}.`
          }
        />
      </Stack>
    </Surface>
  );
}
