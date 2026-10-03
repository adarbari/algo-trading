# features/

User actions and flows with their state (e.g. `screener-builder`, `chain-filter`), one folder
per feature with a public `index.ts`. May import entities, shared and `@algotrade/ui`; never
another feature (compose two features in a widget). No HTML elements, no styling. Rules:
[docs/ui/architecture.md](../../../../docs/ui/architecture.md) (ADR 0025).
