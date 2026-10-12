import { describe, expect, it } from 'vitest';

import type { MyFeatureRequest } from '../api/feature-requests';
import { earlierAsk, missingRef, ownRequest, requestStatus, type MissingFeature } from './history';

const item = (over: Partial<MissingFeature> = {}): MissingFeature => ({
  key: 'moat_score',
  new_key_slug: null,
  span: 'rising moat score',
  description: 'A moat score',
  why_needed: 'the sentence asks for it',
  closest: [],
  feasibility: 'NEEDS_SOURCE',
  ...over,
});

const request = (over: Partial<MyFeatureRequest> = {}): MyFeatureRequest => ({
  ref: 'moat_score',
  description: 'A moat score',
  status: 'OPEN',
  unmapped: false,
  firstAsked: '2026-10-03',
  lastAsked: '2026-10-11',
  timesAsked: 2,
  promotedTo: '',
  feasibility: 'NEEDS_SOURCE',
  span: null,
  ...over,
});

describe('earlierAsk', () => {
  it('finds the trader own request asked on an earlier day', () => {
    expect(earlierAsk(item(), [request()])?.firstAsked).toBe('2026-10-03');
  });

  it('is null when the only ask is the one that just ran', () => {
    expect(earlierAsk(item(), [request({ timesAsked: 1 })])).toBeNull();
  });

  it('matches an unmapped request by its slug and ignores other refs', () => {
    const unmapped = item({ key: null, new_key_slug: 'rising_moat' });
    expect(missingRef(unmapped)).toBe('rising_moat');
    expect(earlierAsk(unmapped, [request({ ref: 'rising_moat', unmapped: true })])).not.toBeNull();
    expect(earlierAsk(unmapped, [request()])).toBeNull();
    expect(earlierAsk(item({ key: null, new_key_slug: null }), [request()])).toBeNull();
  });
});

describe('ownRequest', () => {
  it('is the trader request even when it was asked once', () => {
    expect(ownRequest(item(), [request({ timesAsked: 1 })])?.ref).toBe('moat_score');
    expect(ownRequest(item(), [])).toBeNull();
  });
});

describe('requestStatus', () => {
  it('reads the backlog statuses and nothing else', () => {
    expect(requestStatus(request({ status: 'PROMOTED' }))).toBe('PROMOTED');
    expect(requestStatus(request({ status: 'WONT_DO' }))).toBe('WONT_DO');
    expect(requestStatus(request({ status: 'odd' }))).toBeNull();
    expect(requestStatus(undefined)).toBeNull();
  });
});
