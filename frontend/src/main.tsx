import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'

import './api/client'
import './design-system/global.css'
import { ErrorBoundary } from './app/ErrorBoundary'
import { QueryProvider } from './app/QueryProvider'
import { router } from './app/router'
import { TooltipProvider } from './design-system'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryProvider>
        {/* One provider at the root gives every tooltip in the app shared timing. */}
        <TooltipProvider>
          <RouterProvider router={router} />
        </TooltipProvider>
      </QueryProvider>
    </ErrorBoundary>
  </StrictMode>,
)
