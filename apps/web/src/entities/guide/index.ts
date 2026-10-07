/**
 * Entity: the Guide (ADR 0051): the index of what it holds (sections with counts, field theme
 * groups, intents), what the server derives for one field's page (related fields, playbooks,
 * situations), and the paths of its pages and of the places it links to.
 */
export { useGuideField, useGuideIndex } from './api/hooks';
export {
  BUILT_SECTIONS,
  exploreFieldPath,
  fieldPath,
  fieldsPath,
  GUIDE_FIELDS_PATH,
  GUIDE_PATH,
  parseFieldsSearch,
  themeTitle,
  type FieldsSearch,
  type FieldsView,
} from './model/paths';
