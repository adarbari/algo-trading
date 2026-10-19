/**
 * Entity: the Guide (ADR 0051): the index of what it holds (sections with counts, field theme
 * groups, intents, regime indicators and falls), what the server derives for one field's page (related fields, playbooks,
 * situations), the linked prose the server sends, the glossary terms and Start here pages, and the paths of its pages and of the places it links to.
 */
export {
  prefetchGuideIndex,
  useGuideEpisode,
  useGuideField,
  useGuideIndex,
  useGuideIndicator,
  useGuidePlaybook,
  useGuideSituation,
  useGuideStartPage,
  useGuideTerm,
} from './api/hooks';
export { useGuideEdge, useGuideEdgeIndex, useGuideMechanism } from './api/edges';
export { episodeFacts, type EpisodeFacts } from './model/episode-facts';
export { edgeSideText, edgeStatusText, edgeStatusTone, ideaVerdictTone } from './model/edge-status';
export {
  EdgeRows,
  IdeaRows,
  type EdgeRowsProps,
  type EdgeRowValue,
  type IdeaRowsProps,
  type IdeaRowValue,
} from './ui/EdgeRows';
export { RelatedTerms, type RelatedTermsProps } from './ui/RelatedTerms';
export { GuideProse, proseParts, type GuideProseValue } from './ui/GuideProse';
export {
  BUILT_SECTIONS,
  edgeGuidePath,
  edgesGroupPath,
  EDGES_PAGE_PATH,
  episodePath,
  exploreFieldPath,
  fieldPath,
  fieldsPath,
  guideEntryPath,
  indicatorPath,
  mechanismPath,
  GUIDE_EDGES_PATH,
  GUIDE_FIELDS_PATH,
  GUIDE_GLOSSARY_PATH,
  GUIDE_KIND_TITLES,
  GUIDE_PATH,
  GUIDE_PLAYBOOKS_PATH,
  GUIDE_REGIME_PATH,
  GUIDE_SITUATIONS_PATH,
  GUIDE_START_PATH,
  parseFieldsSearch,
  playbookPath,
  REGIME_PAGE_PATH,
  screenerBuilderPath,
  screenerResultsPath,
  situationPath,
  startPath,
  termPath,
  themeTitle,
  type FieldsSearch,
  type FieldsView,
} from './model/paths';
