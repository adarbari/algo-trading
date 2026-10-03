# widgets/

Page sections composed of features and entities (e.g. `NightlyRunPanel`), one folder per
widget with a public `index.ts`. May import features, entities, shared and `@algotrade/ui`;
never another widget, a page or the app. No HTML elements, no styling. Rules and examples:
[docs/ui/architecture.md](../../../../docs/ui/architecture.md) (ADR 0025).
