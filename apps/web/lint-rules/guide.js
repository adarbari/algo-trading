/** Where every lint message points: the rule's ADR section and the skill that explains the fix. */
export const ARCH = 'docs/ui/architecture.md (ADR 0025)';
export const UI_SKILL = '.claude/skills/add-ui-component';
export const PAGE_SKILL = '.claude/skills/add-web-page';

/** `[ADR 0025 rule n] text. See ...` */
export function message(rule, text, skill = UI_SKILL) {
  return `[ADR 0025 rule ${rule}] ${text} See ${ARCH} and ${skill}.`;
}
