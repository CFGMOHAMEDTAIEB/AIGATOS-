import { Navigate } from 'react-router-dom'

/** Compatibility shim for legacy imports; the operational view is /analysis. */
export function AgentInteractionPage(){
  return <Navigate to="/analysis" replace/>
}
