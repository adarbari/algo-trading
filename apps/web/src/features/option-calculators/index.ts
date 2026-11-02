/** Feature: the option calculators' typed figures and their preview POSTs (roll a put, calls on shares). */
export { useCallsPreview, useRollPreview } from './api/hooks';
export {
  callsBody,
  rollBody,
  type CallsBody,
  type CallsForm,
  type RollBody,
  type RollForm,
} from './model/bodies';
export {
  closedSentence,
  contractsText,
  dividendLine,
  type CallRow,
  type CallsPreview,
  type Dividend,
  type DividendLine,
} from './model/calls';
export {
  rollSentence,
  shownRolls,
  VISIBLE_ROLLS,
  type OptionGap,
  type RollPreview,
  type RollRow,
} from './model/roll';
