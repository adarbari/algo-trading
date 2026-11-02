/**
 * The labels and Guide terms of what the server says about a tab's list: a setup's night (state)
 * and why setups or picks were left out (kind). The words are the Guide's entries' names; the
 * explanations live there (ADR 0051), never here.
 */

export const STATE_TERMS: Record<string, { label: string; term: string }> = {
  picked: { label: 'Picked tonight', term: 'idea_setup_picked' },
  nothing_picked: { label: 'Nothing picked', term: 'idea_setup_nothing_picked' },
  not_a_decision_day: { label: 'Not a decision day', term: 'edge_pick_not_a_decision_day' },
  unknown: { label: 'Picks not known', term: 'idea_setup_unknown' },
};

export const LEFT_OUT_TERMS: Record<string, { label: string; term: string }> = {
  newer_run: { label: 'only a newer run', term: 'idea_left_out_newer_run' },
  no_verdict: { label: 'no readable verdict', term: 'idea_left_out_no_verdict' },
  no_basis: { label: 'no basis recorded', term: 'idea_left_out_no_basis' },
  licence: { label: 'kept off by a licence', term: 'idea_left_out_licence' },
};
