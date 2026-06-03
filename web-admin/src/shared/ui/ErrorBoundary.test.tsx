import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'

const { reportClientError } = vi.hoisted(() => ({
  reportClientError: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/shared/telemetry/clientLogger', () => ({
  reportClientError,
}))

import { ErrorBoundary } from '@/shared/ui/ErrorBoundary'

function Thrower(): ReactNode {
  throw new Error('admin crash')
}

beforeEach(() => {
  reportClientError.mockClear()
})

it('renders fallback UI and reports the frontend crash', async () => {
  const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

  render(
    <ErrorBoundary>
      <Thrower />
    </ErrorBoundary>,
  )

  expect(await screen.findByText(/критическая ошибка интерфейса/i)).toBeInTheDocument()
  await waitFor(() => {
    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'admin crash',
        context: expect.objectContaining({
          source: 'error-boundary',
        }),
      }),
    )
  })

  consoleErrorSpy.mockRestore()
})
