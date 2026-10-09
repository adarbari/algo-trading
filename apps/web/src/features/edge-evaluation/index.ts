/**
 * Feature: run an edge evaluation on request (`POST /edges/{id}/evaluate`, ADR 0059): a
 * "Run backtest" button for the signed-in user (an admin also gets "Run as site"), the job's
 * state while it runs, and the edge's runs read again when it completes. One evaluation at a
 * time per user: the API's refusal is shown as the message.
 */
export { useRunEvaluation } from './api/hooks';
export { RunEvaluation, type RunEvaluationProps } from './ui/RunEvaluation';
