import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CssBaseline, ThemeProvider } from '@mui/material'
import { App } from './App'
import { theme } from './theme'
import { OperationalSessionProvider } from './SessionContext'
import './styles.css'

const queryClient=new QueryClient({defaultOptions:{queries:{retry:1,staleTime:15000,refetchOnWindowFocus:false}}})
createRoot(document.getElementById('root')!).render(<StrictMode><ThemeProvider theme={theme}><CssBaseline/><QueryClientProvider client={queryClient}><OperationalSessionProvider><BrowserRouter><App/></BrowserRouter></OperationalSessionProvider></QueryClientProvider></ThemeProvider></StrictMode>)
