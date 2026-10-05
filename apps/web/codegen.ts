/**
 * GraphQL codegen (ADR 0037; docs/api/read-model.md "GraphQL conventions"): the client preset
 * over the committed schema snapshot apps/api/schema.graphql (never a running server), for
 * every operation and fragment written with the generated `graphql()` tag in src/. Output:
 * src/shared/api/generated/graphql/ (`npm run api:generate`; CI fails on a stale copy).
 */
import type { CodegenConfig } from '@graphql-codegen/cli';

const config: CodegenConfig = {
  schema: '../api/schema.graphql',
  documents: ['src/**/*.{ts,tsx}', '!src/shared/api/generated/**'],
  ignoreNoDocuments: true,
  generates: {
    'src/shared/api/generated/graphql/': {
      preset: 'client',
      presetConfig: { fragmentMasking: true },
      config: {
        // Documents as strings (no graphql runtime in the bundle); gql() posts them as-is.
        documentMode: 'string',
        enumsAsTypes: true,
        useTypeImports: true,
        strictScalars: true,
        scalars: { Date: 'string', JSON: 'unknown', FeatureName: 'string' },
      },
    },
  },
};

export default config;
