/**
 * The Guide's compact rail: the search button (it opens the one search dialog, whose results the
 * server ranks), and under it the sections with their entry counts from the server, in the
 * spec's order (Start here first, Glossary last); Fields expands to its themes, and the theme of
 * the current field to its fields; Start here, Market regime (indicators, then market falls),
 * Screeners (the categories in order, the open category's screeners under it) and Situations list their pages while one of theirs is open;
 * Edges lists the mechanisms and, after them, the ideas not built on its pages.
 */
import { NavList, Stack, type NavListItem } from '@algotrade/ui';

import {
  byName,
  themeFields,
  useFeatureCatalogue,
  type CatalogueFeature,
} from '@/entities/feature';
import {
  BUILT_SECTIONS,
  edgesGroupPath,
  episodePath,
  fieldPath,
  fieldsPath,
  GUIDE_EDGES_PATH,
  GUIDE_FIELDS_PATH,
  GUIDE_GLOSSARY_PATH,
  GUIDE_PATH,
  GUIDE_SCREENERS_PATH,
  GUIDE_REGIME_PATH,
  GUIDE_SITUATIONS_PATH,
  GUIDE_START_PATH,
  indicatorPath,
  mechanismPath,
  screenerCategoryPath,
  screenerPath,
  situationPath,
  startPath,
  themeTitle,
  useGuideEdgeIndex,
  useGuideIndex,
  useGuideMechanisms,
} from '@/entities/guide';
import { GuideSearchButton } from '@/features/guide-search';

/** Fields listed under the current theme before "N more". */
const THEME_FIELDS_SHOWN = 8;

export interface GuideRailProps {
  /** Which Guide page is open. */
  page:
    | 'home'
    | 'fields'
    | 'field'
    | 'screeners'
    | 'screener_category'
    | 'screener'
    | 'situations'
    | 'situation'
    | 'regime'
    | 'edges'
    | 'mechanism'
    | 'edge'
    | 'indicator'
    | 'episode'
    | 'start'
    | 'start_page'
    | 'glossary'
    | 'term';
  /** The theme the field index is narrowed to. */
  theme?: string | undefined;
  /** The field whose page is open (catalogue name). */
  field?: string | undefined;
  /** The screener family whose page is open (its id). */
  category?: string | undefined;
  /** The screener whose page is open (the preset id). */
  screener?: string | undefined;
  /** The situation whose page is open (its slug). */
  situation?: string | undefined;
  /** The regime indicator whose page is open (its key). */
  indicator?: string | undefined;
  /** The market fall whose page is open (its slug). */
  episode?: string | undefined;
  /** The mechanism whose page is open, or the mechanism of the edge page that is (its id). */
  mechanism?: string | undefined;
  /** The Start here page that is open (its id). */
  startPage?: string | undefined;
}

export function GuideRail({
  page,
  theme,
  field,
  category,
  screener,
  situation,
  indicator,
  episode,
  mechanism,
  startPage,
}: GuideRailProps) {
  const index = useGuideIndex();
  const onEdges = page === 'edges' || page === 'mechanism' || page === 'edge';
  // The titles of the two groups after the mechanisms are the Edges index's own.
  const edgeIndex = useGuideEdgeIndex({ enabled: onEdges });
  const mechanismList = useGuideMechanisms();
  const catalogue = useFeatureCatalogue();
  const all = catalogue.data;
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

  const onScreeners = page === 'screeners' || page === 'screener_category' || page === 'screener';
  // The open category: the page's own, or the family of the open screener.
  const openCategory =
    page === 'screener'
      ? index.data?.families.find((f) => f.screeners.some((p) => p.id === screener))?.id
      : category;

  const screenersSection = (s: { title: string; entries: number }): NavListItem => ({
    href: GUIDE_SCREENERS_PATH,
    label: s.title,
    count: s.entries,
    current: page === 'screeners',
    children: onScreeners
      ? (index.data?.families ?? [])
          .filter((f) => f.screeners.length > 0)
          .map((f) => ({
            href: screenerCategoryPath(f.id),
            label: f.title,
            count: f.screeners.length,
            current: page === 'screener_category' && f.id === category,
            children:
              f.id === openCategory
                ? f.screeners.map((p) => ({
                    href: screenerPath(p.id),
                    label: p.name,
                    current: page === 'screener' && p.id === screener,
                  }))
                : [],
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

  const edgesSection = (s: { title: string; entries: number }): NavListItem => ({
    href: GUIDE_EDGES_PATH,
    label: s.title,
    count: s.entries,
    current: page === 'edges',
    children: onEdges
      ? [
          ...(mechanismList.data ?? []).map((m) => ({
            href: mechanismPath(m.id),
            label: m.title,
            count: m.count,
            current: page === 'mechanism' && m.id === mechanism,
          })),
          ...(edgeIndex.data
            ? [{ href: edgesGroupPath('not-built'), label: edgeIndex.data.notBuiltTitle }]
            : []),
        ]
      : [],
  });

  const startSection = (s: { title: string; entries: number }): NavListItem => ({
    href: GUIDE_START_PATH,
    label: s.title,
    count: s.entries,
    current: page === 'start',
    children:
      page === 'start' || page === 'start_page'
        ? (index.data?.startPages ?? []).map((p) => ({
            href: startPath(p.id),
            label: `${String(p.order)}. ${p.title}`,
            current: page === 'start_page' && p.id === startPage,
          }))
        : [],
  });

  const glossarySection = (s: { title: string; entries: number }): NavListItem => ({
    href: GUIDE_GLOSSARY_PATH,
    label: s.title,
    count: s.entries,
    current: page === 'glossary' || page === 'term',
  });

  const sectionItem: Record<string, (s: { title: string; entries: number }) => NavListItem> = {
    start: startSection,
    glossary: glossarySection,
    regime: regimeSection,
    edges: edgesSection,
    screeners: screenersSection,
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
      <GuideSearchButton />
      <NavList aria-label="Guide" items={sections} />
    </Stack>
  );
}
