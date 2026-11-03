/**
 * Widget: one Ideas tab (ADR 0083): its heading with the Stocks | Premium tabs, the picks of
 * setups with a good stored verdict, or its Unproven section (tonight's matches of the tab's
 * screeners under the shared filter bar, and the picks the regime paused).
 */
export { IdeasHeading, type IdeasHeadingProps } from './ui/IdeasHeading';
export { PausedPicks, type PausedPicksProps } from './ui/PausedPicks';
export { SetupIdeas, type SetupIdeasProps } from './ui/SetupIdeas';
export {
  UnprovenMatches,
  type UnprovenMatchesProps,
  type UnprovenSearch,
  type UnprovenSearchPatch,
} from './ui/UnprovenMatches';
