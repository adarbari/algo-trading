/**
 * Feature: what a user does about an edge (ADR 0053 amendment 2026-10-09): clone it into their
 * own, follow, reject, retire or reopen it, show a copy's out-of-sample result, and (an admin)
 * download it as the TOML to publish site-wide. One dialog per kind of move; the API refuses
 * what is not allowed and decides the permanent warning labels.
 */
export { EdgeActions, type EdgeActionsProps } from './ui/EdgeActions';
