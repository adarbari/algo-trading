# entities/

Domain models with their read hooks (TanStack Query over `@/shared/api`) and view components
(e.g. `instrument`, `feature`, `screen`, `run`), one folder per entity with a public
`index.ts`. May import shared, `@algotrade/ui` and another entity's `index.ts`. No HTML
elements, no styling. Rules: [docs/ui/architecture.md](../../../../docs/ui/architecture.md)
(ADR 0025).
