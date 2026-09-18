import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'

import './api/client'
import './design-system/global.css'
import { ErrorBoundary } from './app/ErrorBoundary'
import { QueryProvider } from './app/QueryProvider'
import { router } from './app/router'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryProvider>
        <RouterProvider router={router} />
      </QueryProvider>
    </ErrorBoundary>
  </StrictMode>,
)
