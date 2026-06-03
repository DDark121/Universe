import { waitFor } from '@testing-library/react'

const { reportApiError } = vi.hoisted(() => ({
  reportApiError: vi.fn(),
}))

vi.mock('@/shared/telemetry/clientLogger', () => ({
  reportApiError,
}))

import { createAppQueryClient } from '@/app/providers'

beforeEach(() => {
  reportApiError.mockClear()
})

it('reports unexpected react-query failures through the shared client logger', async () => {
  const queryClient = createAppQueryClient()

  await expect(
    queryClient.fetchQuery({
      queryKey: ['students', 'list'],
      queryFn: async () => {
        throw new Error('query failed')
      },
    }),
  ).rejects.toThrow('query failed')

  await waitFor(() => {
    expect(reportApiError).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({
        source: 'react-query-query',
        queryKey: 'students:list',
      }),
    )
  })
})
