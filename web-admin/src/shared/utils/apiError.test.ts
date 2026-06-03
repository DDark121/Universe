import axios from 'axios'

import { getApiErrorMessage } from './apiError'

it('returns wrapped backend error message', () => {
  const error = new axios.AxiosError('Request failed with status code 409')
  error.response = {
    data: {
      error: {
        code: 'http_error',
        message: 'User already has Telegram binding',
      },
    },
    status: 409,
    statusText: 'Conflict',
    headers: {},
    config: {} as never,
  }

  expect(getApiErrorMessage(error)).toBe('User already has Telegram binding')
})

it('returns wrapped backend error details when message is absent', () => {
  const error = new axios.AxiosError('Request failed with status code 500')
  error.response = {
    data: {
      error: {
        code: 'internal_error',
        details: 'Detailed backend failure',
      },
    },
    status: 500,
    statusText: 'Internal Server Error',
    headers: {},
    config: {} as never,
  }

  expect(getApiErrorMessage(error)).toBe('Detailed backend failure')
})
