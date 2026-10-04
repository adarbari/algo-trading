import { afterEach, describe, expect, it, vi } from 'vitest';

import { saveTextFile } from './save-text-file';

describe('saveTextFile', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('downloads the text under the name, then releases the object URL', async () => {
    vi.useFakeTimers();
    const blobs: Blob[] = [];
    URL.createObjectURL = vi.fn((blob: Blob) => {
      blobs.push(blob);
      return 'blob:test';
    });
    const revoke = vi.fn();
    URL.revokeObjectURL = revoke;
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      expect(this.download).toBe('items.csv');
      expect(this.href).toBe('blob:test');
    });

    saveTextFile('items.csv', 'key,code\nAAPL,OK\n');

    expect(click).toHaveBeenCalledOnce();
    expect(blobs[0]?.type).toBe('text/csv;charset=utf-8');
    expect(await blobs[0]?.text()).toBe('key,code\nAAPL,OK\n');
    expect(revoke).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(revoke).toHaveBeenCalledWith('blob:test');
  });
});
