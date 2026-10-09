/**
 * Feature: set the user's out-of-sample split (`PUT /evaluation/split`): the site's out-of-sample
 * periods, their own split, a date input with Save and Clear. Runs under it are exploratory
 * and come from `evaluate-edges`; the form never starts a run.
 */
export { useSaveSplit } from './api/hooks';
export { EvaluationSplitForm, type EvaluationSplitFormProps } from './ui/EvaluationSplitForm';
