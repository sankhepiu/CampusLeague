export const env = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000/api',
  useMockApi: (import.meta.env.VITE_USE_MOCK_API as string | undefined) !== 'false',
} as const;
