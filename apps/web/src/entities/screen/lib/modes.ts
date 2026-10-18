/**
 * The criterion modes (hard, soft, score), apart from the spec model so a list that only reads
 * criteria does not load the Builder's document code with them.
 */
export type CriterionMode = 'hard' | 'soft' | 'score';

export const MODES: readonly CriterionMode[] = ['hard', 'soft', 'score'];
