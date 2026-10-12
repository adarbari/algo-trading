/** The accepted-formula entity's types: the server's grouped list and its rows, as the operation selects. */
import type { gqlTypes } from '@/shared/api';

export type AcceptedFormulaList = NonNullable<gqlTypes.AcceptedFormulasQuery['acceptedFormulas']>;
export type AcceptedFormula = AcceptedFormulaList['rows'][number];
