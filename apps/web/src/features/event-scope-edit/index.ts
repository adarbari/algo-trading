/** Feature: change the event-study scope list (add a ticker, remove a name; Admin only; ADR 0050). */
export { AddScopeNameForm } from './ui/AddScopeNameForm';
export { RemoveScopeNameDialog, type RemoveScopeNameDialogProps } from './ui/RemoveScopeNameDialog';
export { useAddScopeName, useRemoveScopeName, type ScopeWrite } from './api/hooks';
