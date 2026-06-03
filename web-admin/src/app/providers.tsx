import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'

import { AppRouter } from '@/app/router'
import { AuthProvider } from '@/shared/auth/AuthContext'
import { reportApiError } from '@/shared/telemetry/clientLogger'
import { ErrorBoundary } from '@/shared/ui/ErrorBoundary'
import { ToastProvider } from '@/shared/ui/ToastProvider'

export function createAppQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        reportApiError(error, {
          source: 'react-query-query',
          queryKey: Array.isArray(query.queryKey) ? query.queryKey.join(':') : String(query.queryKey),
        })
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        reportApiError(error, {
          source: 'react-query-mutation',
          mutationKey: Array.isArray(mutation.options.mutationKey)
            ? mutation.options.mutationKey.join(':')
            : String(mutation.options.mutationKey || 'unknown'),
        })
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        retry: 1,
      },
      mutations: {
        retry: 0,
      },
    },
  })
}

const queryClient = createAppQueryClient()

export function AppProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ToastProvider>
          <ErrorBoundary>
            <BrowserRouter>
              <AppRouter />
            </BrowserRouter>
          </ErrorBoundary>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
