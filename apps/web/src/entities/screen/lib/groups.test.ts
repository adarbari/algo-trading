import { describe, expect, it } from 'vitest';

import {
  eitherWithPrevious,
  excludeCriterion,
  excludeGroup,
  groupsOf,
  joinTarget,
  layoutOf,
  newGroupId,
  pruneGroups,
  ungroup,
  type CriterionGroup,
} from './groups';

type Doc = Record<string, unknown>;
const doc = (extra: Doc = {}): Doc => ({ id: 's', ...extra });
const c = (id: string) => ({ id });
const ids = ['a', 'b', 'c', 'd'].map(c);
const any = (id: string, members: string[]): CriterionGroup => ({ id, kind: 'any', members });

describe('groupsOf', () => {
  const live = new Set(['a', 'b', 'c']);

  it('reads the draft groups after the base ones, the draft winning per group', () => {
    const { groups } = groupsOf(
      { g: { any: ['a', 'b'] } },
      { g: { none: ['a', 'b'] }, h: { any: ['b', 'c'] } },
      live,
    );
    expect(groups).toEqual([
      { id: 'g', kind: 'none', members: ['a', 'b'] },
      { id: 'h', kind: 'any', members: ['b', 'c'] },
    ]);
  });

  it('drops members that are gone and takes everything under a disabled group out', () => {
    const { groups, off } = groupsOf(
      { top: { any: ['in', 'a'] }, in: { all: ['b', 'c'] } },
      { in: { enabled: false } },
      new Set(['a', 'c']),
    );
    expect([...off].sort()).toEqual(['b', 'c', 'in']);
    expect(groups).toEqual([{ id: 'top', kind: 'any', members: ['a'] }]);
  });
});

describe('layoutOf', () => {
  it('puts a gate at its first criterion, members in criteria order', () => {
    const layout = layoutOf(ids, [any('g', ['c', 'b'])], new Set(['g']));
    expect(layout.map((n) => (n.type === 'group' ? n.group.id : n.criterion.id))).toEqual([
      'a',
      'g',
      'd',
    ]);
    const gate = layout[1];
    expect(
      gate?.type === 'group' && gate.members.map((m) => m.type === 'criterion' && m.criterion.id),
    ).toEqual(['b', 'c']);
  });

  it('edits one level written by the draft, not a nested or inherited group', () => {
    const nested: CriterionGroup[] = [
      { id: 'in', kind: 'all', members: ['a', 'b'] },
      any('out', ['in', 'c']),
    ];
    const deep = layoutOf(ids, nested, new Set(['in', 'out']))[0];
    expect(deep?.type === 'group' && deep.editable).toBe(false);
    expect(deep?.type === 'group' && deep.owned).toBe(true);
    const inherited = layoutOf(ids, [any('g', ['a', 'b'])], new Set())[0];
    expect(inherited?.type === 'group' && inherited.editable).toBe(false);
    expect(inherited?.type === 'group' && inherited.owned).toBe(false);
    const flat = layoutOf(ids, [any('g', ['a', 'b'])], new Set(['g']))[0];
    expect(flat?.type === 'group' && flat.editable).toBe(true);
  });
});

describe('the actions', () => {
  it('makes an any group of a criterion and the one before', () => {
    const layout = layoutOf(ids, [], new Set());
    const out = eitherWithPrevious(doc(), layout, ['a', 'b', 'c', 'd'], 'b');
    expect(out['groups']).toEqual({ any: { any: ['a', 'b'] } });
  });

  it('adds a criterion to the any group before it, and joins nothing else', () => {
    const groups = [any('g', ['a', 'b'])];
    const layout = layoutOf(ids, groups, new Set(['g']));
    expect(
      eitherWithPrevious(doc({ groups: { g: { any: ['a', 'b'] } } }), layout, ['g'], 'c')['groups'],
    ).toEqual({
      g: { any: ['a', 'b', 'c'] },
    });
    expect(joinTarget(layout, 'a')).toBeNull();
    const none = layoutOf(ids, [{ id: 'n', kind: 'none', members: ['a'] }], new Set(['n']));
    expect(joinTarget(none, 'b')).toBeNull();
    const plain = doc();
    expect(eitherWithPrevious(plain, none, [], 'b')).toBe(plain);
  });

  it('excludes a criterion or an any group', () => {
    expect(excludeCriterion(doc(), ['a'], 'a')['groups']).toEqual({ none: { none: ['a'] } });
    expect(excludeGroup(doc(), any('g', ['a', 'b']))['groups']).toEqual({
      g: { none: ['a', 'b'] },
    });
  });

  it('ungroups a group and dissolves a member all that would become a top-level all', () => {
    const groups: CriterionGroup[] = [
      { id: 'in', kind: 'all', members: ['a', 'b'] },
      any('out', ['in', 'c']),
    ];
    const document = doc({ groups: { in: { all: ['a', 'b'] }, out: { any: ['in', 'c'] } } });
    expect(ungroup(document, groups, 'out')['groups']).toBeUndefined();
    const keep = doc({ groups: { none: { none: ['a'] }, out: { any: ['none', 'c'] } } });
    expect(
      ungroup(
        keep,
        [{ id: 'none', kind: 'none', members: ['a'] }, any('out', ['none', 'c'])],
        'out',
      )['groups'],
    ).toEqual({ none: { none: ['a'] } });
  });
});

describe('pruneGroups', () => {
  it('shrinks a group and dissolves one left too small, which shrinks its parent', () => {
    const out = pruneGroups(
      doc({
        groups: {
          in: { all: ['a', 'b'] },
          out: { any: ['in', 'c'] },
          big: { any: ['a', 'b', 'c'] },
        },
      }),
      ['b'],
    );
    expect(out['groups']).toEqual({ big: { any: ['a', 'c'] } });
  });

  it('dissolves an empty none and drops the key when no group is left', () => {
    expect(pruneGroups({ id: 's', groups: { n: { none: ['a'] } } }, ['a'])).toEqual({ id: 's' });
  });
});

describe('newGroupId', () => {
  it('takes the next free id of the kind, never score', () => {
    expect(newGroupId([], 'any')).toBe('any');
    expect(newGroupId(['any', 'any_2'], 'any')).toBe('any_3');
    expect(newGroupId(['none'], 'none')).toBe('none_2');
  });
});
