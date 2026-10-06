import { describe, expect, it } from 'vitest';

import { episodeName, EPISODES } from './episodes';

describe('episodeName', () => {
  it('names each reference episode in plain words, newest first', () => {
    expect(EPISODES.map((episode) => episodeName(episode.key))).toEqual([
      'Tariff shock, spring 2025',
      'Rate-hike bear market, 2022',
      'Covid crash, early 2020',
    ]);
  });

  it('spaces the key of an episode with no name yet', () => {
    expect(episodeName('crash_1987')).toBe('crash 1987');
  });
});
