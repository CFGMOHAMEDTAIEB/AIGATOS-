import { expect, test, type Route } from '@playwright/test'

// Contract test double: every backend request is intercepted. It persists
// state only in this test process and cannot touch PostgreSQL, Celery, an LLM,
// or any OTA executor.
test('guided simulation -> explicit investigation -> persisted report download', async ({ page }) => {
  const simulationId = 'e2e-simulation-001'
  const campaignId = 'e2e-campaign-001'
  const incidentId = 'e2e-incident-001'
  const workflowId = 'e2e-workflow-001'
  const sessionId = 'e2e-session-001'
  let sessionStatus = 'PREPARING'
  let lastMethod = ''
  const context = {
    context_id: simulationId, source: 'LIVE_SIMULATION', environment: 'SIMULATED',
    session_id: sessionId, campaign_id: campaignId, campaign_name: 'E2E contract session',
    campaign_status: 'draft', simulation_id: simulationId, simulation_status: 'COMPLETED',
    incident_id: incidentId, workflow_id: workflowId, report_id: 'e2e-report-001',
    workflow_status: 'WAITING_FOR_HUMAN_APPROVAL', approval_status: 'PENDING',
    software_name: 'BatteryManager', software_version: '2.4.0', stage_number: 1,
    vehicle_count: 30, progress_count: 30, success_count: 24, failure_count: 6,
    rollback_count: 3, failure_rate: 0.2, evidence_count: 6, global_confidence: 0.72,
    actions_executed: 0, created_by: 'playwright-contract',
    created_at: '2026-09-24T10:00:00Z', updated_at: '2026-09-24T10:01:00Z',
  }
  const workflow = {
    workflow_id: workflowId, incident_id: incidentId, campaign_id: campaignId,
    canary_stage_id: 'e2e-stage-001', current_agent: null,
    workflow_status: 'WAITING_FOR_HUMAN_APPROVAL', approval_status: 'PENDING',
    failed_vehicle_ids: ['v-1'], successful_vehicle_ids: ['v-2'], normalized_errors: [],
    timeline: [], correlations: [], hypotheses: [], evidence_ids: ['ev-1'],
    confidence_components: {}, global_confidence: 0.72,
    recommended_actions: [{ action: 'PAUSE_CAMPAIGN', status: 'PROPOSED',
      requires_human_approval: true, reason: 'Review only', executed: false, evidence_ids: ['ev-1'] }],
    retry_count: 0, last_error: null, created_at: context.created_at, updated_at: context.updated_at,
  }
  const executions = ['MONITORING', 'LOG_ANALYSIS', 'CORRELATION', 'RCA', 'DECISION'].map((agent, index) => ({
    id: `execution-${index}`, agent_type: agent, objective: `${agent} bounded objective`,
    status: 'COMPLETED', current_state: 'STOP', observation: { evidence_count: 1 },
    plan: { selected_tool: ['read_simulation_metrics', 'get_vehicle_timeline', 'build_cohorts', 'rank_root_causes', 'create_pending_approval'][index], operational_summary: 'Contract-tested operation' },
    selected_tool: ['read_simulation_metrics', 'get_vehicle_timeline', 'build_cohorts', 'rank_root_causes', 'create_pending_approval'][index],
    tool_call_ids: [`tool-${index}`], validation_result: { valid: true }, runtime_retry_count: 0,
    stop_reason: 'Stage completed', tools_allowed: [], tools_used: [], input_payload: {}, output_payload: {},
    evidence_ids: ['ev-1'], incoming_message_ids: [], outgoing_message_ids: [], validations: ['EVIDENCE_REFERENCES'],
    attempt: 1, duration_ms: 3, proposed_next_state: 'STOP', output_source: 'DETERMINISTIC_FALLBACK',
    llm_provider: null, llm_model: null, error_code: null,
    created_at: context.created_at, completed_at: context.updated_at,
  }))
  const messages = ['INCIDENT_DETECTED', 'NORMALIZED_FAILURES_READY', 'CORRELATIONS_READY',
    'ROOT_CAUSES_READY', 'RECOMMENDATION_PROPOSED', 'HUMAN_APPROVAL_REQUIRED'].map((type, index) => ({
    id: `message-${index}`, sender_agent: ['MONITORING', 'LOG_ANALYSIS', 'CORRELATION', 'RCA', 'DECISION', 'DECISION'][index],
    receiver_agent: ['LOG_ANALYSIS', 'CORRELATION', 'RCA', 'DECISION', 'HUMAN', 'HUMAN'][index],
    message_type: type, summary: `${type} persisted`, payload: { evidence_count: 1 },
    evidence_ids: ['ev-1'], tool_call_ids: [`tool-${Math.min(index, 4)}`],
    correlation_id: workflowId, sequence_number: index + 1, validation_status: 'VALIDATED',
    created_at: context.updated_at, consumed_at: null,
  }))
  const tools = executions.map((execution, index) => ({
    id: `tool-${index}`, agent_execution_id: execution.id, agent_type: execution.agent_type,
    tool_name: execution.selected_tool, mode: index === 4 ? 'INTERNAL_WRITE' : 'READ_ONLY',
    input_payload: { evidence_count: 1 }, output_payload: { evidence_count: 1 },
    status: 'COMPLETED', duration_ms: 2, sequence_number: 1, created_at: context.updated_at,
  }))
  const report = [{ report_id: 'e2e-report-001', incident_id: incidentId, workflow_id: workflowId,
    explanation_id: 'e2e-explanation-001', version: 1, template_version: 'incident-report-v1.1',
    pdf_sha256: 'a'.repeat(64), generated_at: context.updated_at,
    download_url: '/reports/e2e-report-001/pdf', source: 'DETERMINISTIC_FALLBACK' }]
  const session = () => ({
    id: sessionId, session_id: sessionId, source: 'LIVE_SIMULATION', environment: 'SIMULATED',
    created_by: 'playwright-contract', created_at: context.created_at, updated_at: context.updated_at,
    status: sessionStatus, campaign_id: campaignId, simulation_id: simulationId,
    incident_id: sessionStatus === 'PREPARING' ? null : incidentId,
    workflow_id: sessionStatus === 'WAITING_FOR_HUMAN_APPROVAL' ? workflowId : null,
    configuration: { campaign: { name: 'E2E contract session' } }, result: {}, current_stage: 1,
    stage: { stage_number: 1, vehicle_count: 30, status: 'COMPLETED', success_count: 24,
      failure_count: 6, rollback_count: 3, progress_count: 30 },
    event_count: 30, workflow: sessionStatus === 'WAITING_FOR_HUMAN_APPROVAL' ? workflow : null,
    executed: false, can_execute_real_ota: false,
  })
  const json = (route: Route, value: unknown, status = 200) => route.fulfill({
    status, contentType: 'application/json', body: JSON.stringify(value),
  })

  await page.route('**/*', async route => {
    const request = route.request()
    const requestPath = new URL(request.url()).pathname
    if (!requestPath.startsWith('/_backend/')) return route.continue()
    const path = requestPath.replace('/_backend', '')
    lastMethod = `${request.method()} ${path}`
    if (request.method() === 'POST' && path === '/api/v1/llm/test') {
      return json(route, { provider: 'nvidia', model: 'contract-fake', configured: true,
        reachable: true, authorized: true, latency_ms: 1, structured_output_supported: true, error_code: null })
    }
    if (request.method() === 'POST' && path === '/live-simulations') {
      sessionStatus = 'PREPARING'
      return json(route, session(), 201)
    }
    if (request.method() === 'POST' && path.endsWith('/start')) {
      sessionStatus = 'INCIDENT_DETECTED'
      return json(route, session())
    }
    if (request.method() === 'POST' && path.endsWith('/investigation')) {
      sessionStatus = 'WAITING_FOR_HUMAN_APPROVAL'
      return json(route, session())
    }
    if (request.method() === 'GET' && path === '/frontend/capabilities') {
      return json(route, { operation_mode: 'live_simulation', can_create_simulation: true,
        can_launch_simulation: true, can_start_investigation: true, can_review_recommendations: true,
        can_execute_real_ota: false })
    }
    if (request.method() === 'GET' && path === '/api/v1/llm/status') {
      return json(route, { provider: 'nvidia', model: 'contract-fake', hostname: 'test-double',
        configured: true, reachable: false, authorized: false, latency_ms: null,
        structured_output_supported: false, error_code: null })
    }
    if (request.method() === 'GET' && path.includes('/contexts/simulations/')) return json(route, context)
    if (request.method() === 'GET' && path === '/api/v1/ui/contexts') return json(route, [context])
    if (request.method() === 'GET' && path.endsWith('/events')) return json(route, [])
    if (request.method() === 'GET' && path.endsWith('/stream')) {
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' })
    }
    if (request.method() === 'GET' && path === `/api/v1/ui/incidents/${incidentId}`) {
      return json(route, { id: incidentId, campaign_id: campaignId, simulation_id: simulationId,
        stage_number: 1, status: 'open', severity: 'high', title: 'Test incident', failure_rate: 0.2,
        threshold: 0.1, anomaly_score: null, created_at: context.created_at,
        vehicle_count: 30, success_count: 24, failure_count: 6, rollback_count: 3,
        linked_event_count: 30, failure_event_count: 6, normalized_errors: [], affected_vehicles: [] })
    }
    if (request.method() === 'GET' && path === `/workflows/${workflowId}`) return json(route, workflow)
    if (request.method() === 'GET' && path.endsWith('/executions')) return json(route, executions)
    if (request.method() === 'GET' && path.endsWith('/messages')) return json(route, messages)
    if (request.method() === 'GET' && path.endsWith('/tools')) return json(route, tools)
    if (request.method() === 'GET' && path.includes('/api/v1/ui/incidents/') && path.endsWith('/reports')) return json(route, report)
    if (request.method() === 'GET' && path.includes('/api/v1/ui/incidents/') && path.endsWith('/explanation')) return json(route, null)
    if (request.method() === 'GET' && path.includes('e2e-report-001') && path.endsWith('/pdf')) {
      return route.fulfill({ status: 200, contentType: 'application/pdf',
        body: Buffer.from('%PDF-1.4\ncontract-test-double\n%%EOF') })
    }
    if (request.method() === 'GET') return json(route, [])
    if (request.method() === 'POST') return json(route, { detail: 'Unmapped contract request' }, 500)
    return json(route, [])
  })

  await page.goto('/simulation')
  await expect(page.getByRole('heading', { name: 'Nouvelle simulation OTA' })).toBeVisible()
  await expect(page.getByText(/Assistant disponible/)).toBeVisible()
  await page.getByRole('button', { name: 'Charger une configuration de référence' }).click()
  await page.getByRole('button', { name: 'Continuer' }).click()
  await page.getByRole('button', { name: 'Continuer' }).click()
  await page.getByRole('button', { name: 'Continuer' }).click()
  await expect(page.getByText('Aucune action OTA réelle', { exact: true })).toBeVisible()
  await page.getByLabel('Je confirme une simulation sur véhicules virtuels uniquement').check()
  await page.getByRole('button', { name: 'Créer la simulation' }).click()
  await expect(page.getByRole('button', { name: 'Lancer la simulation' })).toBeVisible()
  await page.getByRole('button', { name: 'Lancer la simulation' }).click()
  await expect(page.getByRole('button', { name: 'Lancer l’investigation' })).toBeVisible()
  await page.getByRole('button', { name: 'Lancer l’investigation' }).click()
  await expect(page.getByRole('link', { name: 'Ouvrir l’analyse agentique' })).toBeVisible()
  await page.getByRole('link', { name: 'Ouvrir l’analyse agentique' }).click()
  await expect(page.getByRole('heading', { name: 'Centre agentique' })).toBeVisible()
  for (const [agent, tool] of [
    ['Monitoring', 'read_simulation_metrics'], ['Log Analysis', 'get_vehicle_timeline'],
    ['Correlation', 'build_cohorts'], ['RCA', 'rank_root_causes'], ['Decision', 'create_pending_approval'],
  ]) {
    await page.getByText(agent, { exact: true }).first().click()
    await expect(page.getByText(tool, { exact: true })).toBeVisible()
  }
  await expect(page.getByText('REQUIS', { exact: true })).toBeVisible()
  await expect(page.getByText(/executed=false/)).toBeVisible()
  await page.goto('/reports')
  await expect(page.getByText('a'.repeat(64))).toBeVisible()
  const downloadLink = page.getByRole('link', { name: 'Télécharger le PDF' })
  await expect(downloadLink).toHaveAttribute('href', '/_backend/reports/e2e-report-001/pdf')
  // The intercepted report is a test double; use a local Blob to exercise the
  // browser download behavior without issuing a real report/backend request.
  await downloadLink.evaluate(async element => {
    const blobUrl = URL.createObjectURL(new Blob(['%PDF-1.4\ncontract-test-double\n%%EOF'], { type: 'application/pdf' }))
    element.setAttribute('href', blobUrl)
    element.setAttribute('download', 'e2e-report.pdf')
  })
  const downloadPromise = page.waitForEvent('download')
  await downloadLink.click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('e2e-report.pdf')
  expect(lastMethod).not.toMatch(/approve|reject|decision/i)
})
