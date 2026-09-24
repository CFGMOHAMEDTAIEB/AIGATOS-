const API_BASE = '/_backend'

export function backendUrl(path: string): string {
  return `${API_BASE}${path}`
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

function apiDetail(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object' || !('detail' in body)) return fallback
  const detail = (body as {detail?:unknown}).detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const safe=detail as {code?:unknown;message?:unknown}
    if (typeof safe.message === 'string') return `${safe.message}${typeof safe.code === 'string' ? ` (${safe.code})` : ''}`
  }
  if (Array.isArray(detail)) return detail.map(item => {
    if (!item || typeof item !== 'object') return String(item)
    const issue=item as {loc?:unknown[];msg?:string}
    const field=issue.loc?.filter(value=>value!=='body').join('.')
    return `${field ? `${field}: ` : ''}${issue.msg??'valeur invalide'}`
  }).join(' · ')
  return fallback
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(backendUrl(path), { headers: { Accept: 'application/json' } })
  if (!response.ok) {
    let detail = `Erreur API (${response.status})`
    try {
      detail = apiDetail(await response.json(), detail)
    } catch {
      // The generic status-only message is deliberately retained.
    }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

export async function apiPost<T>(path: string, body: unknown, idempotencyKey: string): Promise<T> {
  const response = await fetch(backendUrl(path), {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = `Erreur API (${response.status})`
    try { detail = apiDetail(await response.json(), detail) } catch { /* status only */ }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

export const endpoints = {
  capabilities: '/frontend/capabilities',
  configurationDraft: '/frontend/configuration-drafts',
  simulationContext: (id:string) => `/api/v1/frontend/contexts/simulations/${encodeURIComponent(id)}`,
  liveSimulation: (id?:string) => id ? `/live-simulations/${encodeURIComponent(id)}` : '/live-simulations',
  liveStart: (id:string) => `/live-simulations/${encodeURIComponent(id)}/start`,
  liveEvents: (id:string) => `/live-simulations/${encodeURIComponent(id)}/events`,
  liveInvestigation: (id:string) => `/live-simulations/${encodeURIComponent(id)}/investigation`,
  investigation: (id:string) => `/incidents/${encodeURIComponent(id)}/investigations`,
  liveWorkflow: (id:string) => `/live-simulations/${encodeURIComponent(id)}/workflow`,
  liveDecision: (id:string) => `/live-simulations/${encodeURIComponent(id)}/decision`,
  agentMaturity: '/agent-maturity',
  contexts: (scope='all') => `/api/v1/ui/contexts?scope=${encodeURIComponent(scope)}`,
  dashboard: (query='') => `/api/v1/ui/dashboard${query}`,
  audit: (simulationId:string) => `/api/v1/ui/audit?simulation_id=${encodeURIComponent(simulationId)}`,
  campaigns: '/api/v1/ui/campaigns',
  campaign: (id: string) => `/api/v1/ui/campaigns/${encodeURIComponent(id)}`,
  vehicles: (query = '') => `/api/v1/ui/vehicles${query}`,
  vehicle: (id: string) => `/api/v1/ui/vehicles/${encodeURIComponent(id)}`,
  incident: (id: string) => `/api/v1/ui/incidents/${encodeURIComponent(id)}`,
  evidence: (id: string) => `/incidents/${encodeURIComponent(id)}/evidence`,
  workflow: (id: string) => `/workflows/${encodeURIComponent(id)}`,
  workflowHistory: (id: string) => `/workflows/${encodeURIComponent(id)}/history`,
  workflowExecutions: (id: string) => `/workflows/${encodeURIComponent(id)}/executions`,
  workflowMessages: (id: string) => `/workflows/${encodeURIComponent(id)}/messages`,
  workflowTools: (id: string) => `/workflows/${encodeURIComponent(id)}/tools`,
  workflowEvents: (id: string, after=0) => `/workflows/${encodeURIComponent(id)}/events?after=${after}`,
  workflowStream: (id: string) => `/workflows/${encodeURIComponent(id)}/stream`,
  llmStatus: '/api/v1/llm/status',
  reports: (id: string) => `/api/v1/ui/incidents/${encodeURIComponent(id)}/reports`,
  createReport: (id:string) => `/incidents/${encodeURIComponent(id)}/reports`,
  explanation: (id: string) => `/api/v1/ui/incidents/${encodeURIComponent(id)}/explanation`,
}
