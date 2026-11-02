/**
 * An option setup's page as the pages show it (ADR 0088): the types of the served
 * `edgeOptionSetup`. Every number, date and state is the read model's; this only names the shapes.
 */
import type { gqlTypes } from '@/shared/api';

export type OptionSetup = NonNullable<gqlTypes.OptionSetupQuery['edgeOptionSetup']>;
export type OptionRules = NonNullable<OptionSetup['rules']>;
export type OptionLeg = OptionRules['legs'][number];
export type OptionEvidence = NonNullable<OptionSetup['evidence']>;
export type OptionYear = OptionEvidence['byYear'][number];
export type OptionStress = OptionEvidence['stress'][number];
export type OptionCostLevel = NonNullable<OptionEvidence['costs']>['levels'][number];

/** Whether the setup's position is options (a share setup's page is the original one). */
export const isOptionSetup = (setup: { positionKind: string } | null | undefined): boolean =>
  setup?.positionKind === 'options';
