import { describe, expect, it } from 'vitest';

import type { RegimeEpisode } from './regime';
import { episodeWindow, HISTORY_START, presetWindow, RANGE_PRESETS } from './window';

describe('presetWindow', () => {
  it('counts the years back from the session, All from the first stored year', () => {
    expect(presetWindow('all', '2026-10-02')).toEqual({ start: HISTORY_START, end: '2026-10-02' });
    expect(presetWindow('20y', '2026-10-02').start).toBe('2006-10-02');
    expect(presetWindow('10y', '2026-10-02').start).toBe('2016-10-02');
    expect(presetWindow('5y', '2026-10-02').start).toBe('2021-10-02');
    expect(presetWindow('2y', '2026-10-02')).toEqual({ start: '2024-10-02', end: '2026-10-02' });
  });

  it('offers All, 20y, 10y, 5y and 2y in that order', () => {
    expect(RANGE_PRESETS.map((p) => p.label)).toEqual(['All', '20y', '10y', '5y', '2y']);
  });
});

describe('episodeWindow', () => {
  const episode = { peak: '2020-02-19', recovered: '2020-08-18' } as RegimeEpisode;

  it('runs from a year before the peak to six months after the recovery', () => {
    expect(episodeWindow(episode, '2026-10-02')).toEqual({
      start: '2019-02-19',
      end: '2021-02-18',
    });
  });

  it('ends at the session while the episode has not recovered or six months would pass it', () => {
    expect(episodeWindow({ ...episode, recovered: null }, '2026-10-02').end).toBe('2026-10-02');
    expect(episodeWindow(episode, '2020-10-01').end).toBe('2020-10-01');
  });
});
