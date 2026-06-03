import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'

const { reportClientError } = vi.hoisted(() => ({
  reportClientError: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('./clientLogger', () => ({
  reportClientError,
}))

import { ErrorBoundary } from './ErrorBoundary'

function Thrower(): ReactNode {
  throw new Error('render crash')
}

beforeEach(() => {
  reportClientError.mockClear()
})

it('renders a fallback and reports the UI crash', async () => {
  const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

  render(
    <ErrorBoundary>
      <Thrower />
    </ErrorBoundary>,
  )

  expect(await screen.findByText(/критическая ошибка mini app/i)).toBeInTheDocument()
  await waitFor(() => {
      expect(reportClientError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'render crash',
          context: expect.objectContaining({
            source: 'react.error_boundary',
          }),
        }),
      )
  })

  consoleErrorSpy.mockRestore()
})
