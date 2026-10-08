/**
 * Entity: the Guide (ADR 0051): the index of what it holds (sections with counts, field theme
 * groups, intents, regime indicators and falls), what the server derives for one field's page (related fields, playbooks,
 * situations), the linked prose the server sends, and the paths of its pages and of the places it links to.
 */
export {
  useGuideEpisode,
  useGuideField,
  useGuideIndex,
  useGuideIndicator,
  useGuidePlaybook,
  useGuideSituation,
} from './api/hooks';
export { episodeFacts, type EpisodeFacts } from './model/episode-facts';
export { GuideProse, proseParts, type GuideProseValue } from './ui/GuideProse';
export {
  BUILT_SECTIONS,
  episodePath,
  exploreFieldPath,
  fieldPath,
  fieldsPath,
  indicatorPath,
  GUIDE_FIELDS_PATH,
  GUIDE_PATH,
  GUIDE_PLAYBOOKS_PATH,
  GUIDE_REGIME_PATH,
  GUIDE_SITUATIONS_PATH,
  parseFieldsSearch,
  playbookPath,
  REGIME_PAGE_PATH,
  screenerBuilderPath,
  screenerResultsPath,
  situationPath,
  themeTitle,
  type FieldsSearch,
  type FieldsView,
} from './model/paths';
