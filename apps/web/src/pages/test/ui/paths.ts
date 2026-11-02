/** The Test flow's paths: the steps' links and the routes share them (one spelling each). */
export const TEST_PATHS = {
  start: '/test',
  guided: '/test/guided',
  describe: '/test/describe',
  expert: '/test/expert',
  setup: '/test/setup',
  expertOf: (id: string) => `/test/expert/${encodeURIComponent(id)}`,
  describeOf: (id: string) => `/test/describe/${encodeURIComponent(id)}`,
  resultOf: (id: string) => `/test/result/${encodeURIComponent(id)}`,
} as const;
