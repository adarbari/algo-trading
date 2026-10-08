/**
 * The Guide's compact rail: a search over field names, display names and what they say (it
 * filters what the catalogue already returned, in the browser), and under it the sections that
 * have pages today with their entry counts from the server; Fields expands to its themes, and
 * the theme of the current field to its fields; Market regime (indicators, then market falls),
 * Playbooks (in family order) and Situations list their pages while one of theirs is open. While a query is typed the rail lists the matching
 * fields instead.
 */
import { NavList, SearchInput, Stack, Text, type NavListItem } from '@algotrade/ui';
import { useMemo, useState } from 'react';

import {
  byName,
  searchFields,
  themeFields,
  useFeatureCatalogue,
  type CatalogueFeature,
} from '@/entities/feature';
import {
  BUILT_SECTIONS,
  episodePath,
  fieldPath,
  fieldsPath,
  GUIDE_FIELDS_PATH,
  GUIDE_PATH,
  GUIDE_PLAYBOOKS_PATH,
  GUIDE_REGIME_PATH,
  GUIDE_SITUATIONS_PATH,
  indicatorPath,
  playbookPath,
  situationPath,
  themeTitle,
  useGuideIndex,
} from '@/entities/guide';

/** Fields listed under the current theme before "N more". */
const THEME_FIELDS_SHOWN = 8;
/** Matches listed while searching. */
const MATCHES_SHOWN = 30;

export interface GuideRailProps {
  /** Which Guide page is open. */
  page:
    | 'home'
    | 'fields'
    | 'field'
    | 'playbooks'
    | 'playbook'
    | 'situations'
    | 'situation'
    | 'regime'
    | 'indicator'
    | 'episode';
  /** The theme the field index is narrowed to. */
  theme?: string | undefined;
  /** The field whose page is open (catalogue name). */
  field?: string | undefined;
  /** The playbook whose page is open (the preset id). */
  playbook?: string | undefined;
  /** The situation whose page is open (its slug). */
  situation?: string | undefined;
  /** The regime indicator whose page is open (its key). */
  indicator?: string | undefined;
  /** The market fall whose page is open (its slug). */
  episode?: string | undefined;
}

export function GuideRail({
  page,
  theme,
  field,
  playbook,
  situation,
  indicator,
  episode,
}: GuideRailProps) {
  const index = useGuideIndex();
  const catalogue = useFeatureCatalogue();
  const [query, setQuery] = useState('');
  const all = catalogue.data;
  const matches = useMemo(
    () => (query.trim() ? searchFields(all ?? [], query) : null),
    [all, query],
  );
  const openField = field && all ? byName(all).get(field) : undefined;
  const openTheme = openField?.guide?.theme ?? theme;

  const fieldItem = (f: CatalogueFeature): NavListItem => ({
    href: fieldPath(f.name),
    label: f.name,
    mono: true,
    current: f.name === field,
  });

  const fieldsSection = (s: { title: string; entries: number }): NavListItem => ({
    href: GUIDE_FIELDS_PATH,
    label: s.title,
    count: s.entries,
    current: page === 'fields' && theme === undefined,
    children: (index.data?.themeGroups ?? [])
      .flatMap((g) => g.themes)
      .map((t): NavListItem => {
        const shown = t.theme === openTheme ? themeFields(all ?? [], t.theme) : [];
        return {
          href: fieldsPath({ theme: t.theme }),
          label: themeTitle(t.theme),
          count: t.fields,
          current: page === 'fields' && t.theme === theme,
          children: [
            ...shown.slice(0, THEME_FIELDS_SHOWN).map(fieldItem),
            ...(shown.length > THEME_FIELDS_SHOWN
              ? [
                  {
                    href: fieldsPath({ theme: t.theme }),
                    label: `${String(shown.length - THEME_FIELDS_SHOWN)} more`,
                  },
                ]
              : []),
          ],
        };
      }),
  });

  const playbooksSection = (s: { title: string; entries: number }): NavListItem => ({
    href: GUIDE_PLAYBOOKS_PATH,
    label: s.title,
    count: s.entries,
    current: page === 'playbooks',
    children:
      page === 'playbooks' || page === 'playbook'
        ? (index.data?.families ?? [])
            .flatMap((f) => f.playbooks)
            .map((p) => ({
              href: playbookPath(p.id),
              label: p.name,
              current: page === 'playbook' && p.id === playbook,
            }))
        : [],
  });

  const situationsSection = (s: { title: string; entries: number }): NavListItem => ({
    href: GUIDE_SITUATIONS_PATH,
    label: s.title,
    count: s.entries,
    current: page === 'situations',
    children:
      page === 'situations' || page === 'situation'
        ? (index.data?.situations ?? []).map((x) => ({
            href: situationPath(x.slug),
            label: x.name,
            current: page === 'situation' && x.slug === situation,
          }))
        : [],
  });

  const regimeSection = (s: { title: string; entries: number }): NavListItem => ({
    href: GUIDE_REGIME_PATH,
    label: s.title,
    count: s.entries,
    current: page === 'regime',
    children:
      page === 'regime' || page === 'indicator' || page === 'episode'
        ? [
            ...(index.data?.indicators ?? []).map((i) => ({
              href: indicatorPath(i.key),
              label: i.plainName,
              current: page === 'indicator' && i.key === indicator,
            })),
            ...(index.data?.episodes ?? []).map((e) => ({
              href: episodePath(e.key),
              label: e.name,
              current: page === 'episode' && e.key === episode,
            })),
          ]
        : [],
  });

  const sectionItem: Record<string, (s: { title: string; entries: number }) => NavListItem> = {
    regime: regimeSection,
    playbooks: playbooksSection,
    fields: fieldsSection,
    situations: situationsSection,
  };

  const sections: NavListItem[] = [
    { href: GUIDE_PATH, label: 'Overview', current: page === 'home' },
    ...(index.data?.sections ?? [])
      .filter((s) => BUILT_SECTIONS.includes(s.id))
      .map((s) => sectionItem[s.id]?.(s))
      .filter((item): item is NavListItem => item !== undefined),
  ];

  return (
    <Stack gap={3}>
      <SearchInput
        aria-label="Search the guide"
        placeholder="Search fields"
        size="sm"
        value={query}
        onValueChange={setQuery}
      />
      {matches ? (
        <Stack gap={2}>
          <Text size="sm" tone="muted">
            {matches.length === 0
              ? `No field matches “${query}”.`
              : `${String(matches.length)} ${matches.length === 1 ? 'field' : 'fields'}`}
          </Text>
          <NavList
            aria-label="Search results"
            size="sm"
            items={matches.slice(0, MATCHES_SHOWN).map((f) => ({
              href: fieldPath(f.name),
              label: f.name,
              mono: true,
              current: f.name === field,
            }))}
          />
          {matches.length > MATCHES_SHOWN && (
            <Text size="sm" tone="muted">
              {`${String(matches.length - MATCHES_SHOWN)} more: narrow the search.`}
            </Text>
          )}
        </Stack>
      ) : (
        <NavList aria-label="Guide" items={sections} />
      )}
    </Stack>
  );
}
