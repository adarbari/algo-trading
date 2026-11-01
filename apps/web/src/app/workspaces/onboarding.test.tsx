import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { OnboardingRedirect } from './onboarding';

const hooks = vi.hoisted(() => ({ prefs: vi.fn(), navigate: vi.fn(), path: { value: '/ideas' } }));
vi.mock('@/entities/trader-preferences', () => ({ useTraderPreferences: hooks.prefs }));
vi.mock('@/pages/onboarding', () => ({ OnboardingPage: () => null }));
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => hooks.navigate,
  useRouterState: ({ select }: { select: (s: unknown) => unknown }) =>
    select({ location: { pathname: hooks.path.value } }),
}));

beforeEach(() => {
  hooks.navigate.mockReset();
  hooks.path.value = '/ideas';
});

const answered = (defaultTab: string | null) => ({ data: { defaultTab, watchlist: [] } });

describe('OnboardingRedirect', () => {
  it('sends a viewer with no stored start tab to the question', () => {
    hooks.prefs.mockReturnValue(answered(null));
    render(<OnboardingRedirect />);
    expect(hooks.navigate).toHaveBeenCalledWith({ to: '/onboarding', replace: true });
  });

  it('lets a viewer who answered through, and never loops on the question itself', () => {
    hooks.prefs.mockReturnValue(answered('premium'));
    render(<OnboardingRedirect />);
    hooks.prefs.mockReturnValue(answered(null));
    hooks.path.value = '/onboarding';
    render(<OnboardingRedirect />);
    expect(hooks.navigate).not.toHaveBeenCalled();
  });

  it('does nothing while the choice is unknown or when the read failed', () => {
    hooks.prefs.mockReturnValue({ data: undefined });
    render(<OnboardingRedirect />);
    expect(hooks.navigate).not.toHaveBeenCalled();
  });
});
