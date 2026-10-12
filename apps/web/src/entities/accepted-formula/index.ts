/** Entity: the formulas traders accepted in Describe it, grouped by fingerprint, for the Admin Feature requests page (ADR 0066; Admin only). */
export { useAcceptedFormulas } from './api/queries';
export { FORMULAS_FIXTURE, formula as formulaFixture } from './model/fixtures';
export {
  START_PAGE,
  TERM_OF_ACCEPTED,
  TERM_OF_BACKLOG_MATCH,
  TERM_OF_DUPLICATE,
  TERM_OF_FINGERPRINT,
} from './model/terms';
export type { AcceptedFormula, AcceptedFormulaList } from './model/types';
