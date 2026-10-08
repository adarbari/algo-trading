/**
 * Feature: the help drawer for a Guide entry (ADR 0051). `GuideHelp` takes an entry reference
 * (`{ kind, id }`; a field's id is its catalogue name) and renders the `InfoButton` that opens
 * the entry in a `HelpDrawer`; it is the only importer of `HelpDrawer`, so no page passes text
 * to it. The app gives it navigation (`GuideHelpProvider`) for "Open full page".
 */
export { GuideHelp, type GuideHelpProps } from './ui/GuideHelp';
export { helped } from './ui/helped';
export { GuideHelpProvider, type GuideNavigate } from './model/navigation';
export { guidePath, type GuideEntry } from './model/entry';
export { useGuideHelp } from './api/hooks';
