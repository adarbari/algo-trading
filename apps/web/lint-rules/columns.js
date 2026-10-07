/**
 * Read model WEB 4 (ADR 0038, docs/api/read-model.md "Column factories"): table columns come
 * only from the factories in src/entities/feature/model/columns.tsx, so a ticker, a decision
 * or a catalogue feature reads the same in every table. A `DataTableColumn` (the design
 * system's column type) may be named only there and in the design system; a widget's table is
 * a ColumnPlan of factory calls rendered by widgets/feature-table.
 *
 * Two explicit exception lists, each entry with its reason:
 *   PENDING   tables of instruments not migrated yet. SHRINK-ONLY: an entry leaves in the PR
 *             named beside it (never add one; a new table uses the factories).
 *   STRUCTURE tables whose rows are not instruments x catalogue features (an option chain's
 *             quotes, events, holdings, run records, checks, screeners, one instrument's
 *             feature list): typed structure, not feature columns.
 */
import { readModelMessage } from './guide.js';

const FACTORIES = 'src/entities/feature/model/columns.tsx';

// SHRINK-ONLY: each entry is removed by the read-model PR named beside it.
const PENDING = [
  'src/widgets/top-ideas/model/columns.tsx', // RM5: Ideas on GraphQL (top ideas rebuilt)
];

// Not feature tables: their rows are not instruments x catalogue features.
const STRUCTURE = [
  'src/widgets/events-panel/ui/EventsPanel.tsx', // an instrument's stored events
  'src/widgets/event-study-panel/model/columns.tsx', // an instrument's events ahead and its 8-Ks
  'src/widgets/features-panel/model/rows.tsx', // one instrument's features, one row each
  'src/widgets/holdings-panel/model/columns.tsx', // an ETF's holdings (issuer-dated weights)
  'src/widgets/options-panel/model/columns.tsx', // an option chain's quotes by strike
  'src/widgets/regime-episodes/model/columns.tsx', // the regime's reference market falls
  'src/widgets/screener-list/model/columns.tsx', // the user's screeners
  'src/widgets/quality-checks-panel/ui/QualityChecksPanel.tsx', // admin: data-quality checks
  'src/widgets/recent-runs-panel/ui/RecentRunsPanel.tsx', // admin: nightly runs
  'src/widgets/review-items-panel/ui/ReviewItemsPanel.tsx', // admin: review lists
  'src/widgets/verification-panel/ui/VerificationPanel.tsx', // admin: IBKR verification
  'src/entities/run/ui/RunRecordDrawer.tsx', // admin: a run's items
];

const MESSAGE = readModelMessage(
  4,
  'table columns come only from the factories in src/entities/feature/model/columns.tsx (tickerColumn, featureColumn(info), decisionColumn, ...): build a ColumnPlan and render it with widgets/feature-table, never a DataTableColumn literal.',
);

/** Reports naming `DataTableColumn` (imported from @algotrade/ui) outside the factories. */
const noColumnLiterals = {
  meta: {
    type: 'problem',
    docs: { description: 'read model WEB 4: columns only from the factories' },
    schema: [],
    messages: { literal: MESSAGE },
  },
  create(context) {
    return {
      ImportSpecifier(node) {
        const source = node.parent?.source?.value;
        const name = node.imported.type === 'Identifier' ? node.imported.name : node.imported.value;
        if (source === '@algotrade/ui' && name === 'DataTableColumn') {
          context.report({ node, messageId: 'literal' });
        }
      },
    };
  },
};

export const columnFactories = {
  name: 'algotrade/read-model/column-factories',
  files: ['src/**/*.{ts,tsx}'],
  ignores: [FACTORIES, ...PENDING, ...STRUCTURE],
  plugins: { algotrade: { rules: { 'column-factories': noColumnLiterals } } },
  rules: { 'algotrade/column-factories': 'error' },
};
