import { chromium } from './capture-tools/node_modules/playwright/index.mjs'

const url = 'http://127.0.0.1:5173/workflows/cde0930e-b80a-447f-8ccc-92c6d97b11ba/interaction'
const allowedMethods = new Set(['GET', 'OPTIONS'])
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))

let browser
try {
  browser = await chromium.launch({
    headless: false,
    channel: 'msedge',
    slowMo: 700,
    args: [
      '--start-fullscreen',
      '--window-position=0,0',
      '--window-size=1920,1080',
      '--disable-notifications',
      '--no-first-run',
    ],
  })
} catch (error) {
  console.error(`EDGE_LAUNCH_ERROR: ${error instanceof Error ? error.message : String(error)}`)
  process.exit(2)
}

const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  locale: 'fr-FR',
})

let getCount = 0
let blockedWriteCount = 0
await context.route('**/*', async route => {
  const method = route.request().method().toUpperCase()
  if (!allowedMethods.has(method)) {
    blockedWriteCount += 1
    await route.abort('blockedbyclient')
    return
  }
  if (method === 'GET') getCount += 1
  await route.continue()
})

const page = await context.newPage()
page.on('dialog', dialog => dialog.dismiss())

try {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.getByRole('heading', { name: 'Agent Interaction' }).waitFor({ timeout: 60_000 })
  await page.getByText('M4 · simulation').first().waitFor({ timeout: 60_000 })

  // Vue globale.
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
  await wait(8_000)

  // Échelle de maturité et avertissement de simulation. M5 n'est attribué à aucun agent.
  await page.getByText('Maturité des agents').scrollIntoViewIfNeeded()
  await wait(10_000)
  await page.getByText('Chaîne d’interaction').scrollIntoViewIfNeeded()
  await wait(6_000)

  // Replay local uniquement.
  await page.getByRole('button', { name: 'Recommencer' }).click()
  await page.getByRole('button', { name: '1×' }).click()
  await page.getByRole('button', { name: 'Replay' }).click()
  await wait(250)
  await page.getByRole('button', { name: 'Pause' }).click()

  // Monitoring : Input / Processing / Output sont visibles simultanément.
  await page.getByText(/^Monitoring · /).last().scrollIntoViewIfNeeded()
  await wait(12_000)

  const next = page.getByRole('button', { name: 'Étape suivante' })
  await next.click()
  await page.getByText(/^Log Analysis · /).last().scrollIntoViewIfNeeded()
  await wait(12_000)

  await next.click()
  await page.getByText(/^Correlation · /).last().scrollIntoViewIfNeeded()
  await wait(15_000)

  await next.click()
  await page.getByText(/^RCA · /).last().scrollIntoViewIfNeeded()
  await wait(15_000)

  await next.click()
  await page.getByText(/^Decision · /).last().scrollIntoViewIfNeeded()
  await wait(15_000)

  await page.getByText('Shared Incident State').scrollIntoViewIfNeeded()
  await page.mouse.wheel(0, 240)
  await wait(12_000)

  await page.getByText('Evidence Traceability').scrollIntoViewIfNeeded()
  await page.mouse.wheel(0, 220)
  await wait(12_000)

  await next.click()
  await page.getByText('Transmission vers Human Approval').scrollIntoViewIfNeeded()
  await page.getByText('WAITING FOR HUMAN APPROVAL').first().waitFor()
  await wait(10_000)

  // Recommandations proposées, aucune exécution.
  await page.getByRole('link', { name: 'Recommandations' }).click()
  await page.getByText('executed=false').first().waitFor()
  await wait(8_000)

  // Approbation PENDING et boutons désactivés sans interaction.
  await page.getByRole('link', { name: 'Validation humaine' }).click()
  await page.getByText('PENDING').first().waitFor()
  await wait(10_000)

  // Canary 3 pending depuis les données FastAPI en lecture seule.
  await page.getByRole('link', { name: 'Campagnes' }).click()
  await page.getByText(/Canary 3 · pending/i).first().waitFor()
  await page.getByText(/Canary 3 · pending/i).first().click()
  await page.getByText('Canary 3').first().waitFor()
  await wait(10_000)

  // Retour final à la vue globale des cinq agents.
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.getByRole('heading', { name: 'Agent Interaction' }).waitFor({ timeout: 60_000 })
  await page.getByText('Chaîne d’interaction').scrollIntoViewIfNeeded()
  await wait(20_000)

  console.log(`DEMO_COMPLETE GET=${getCount} BLOCKED_WRITES=${blockedWriteCount}`)
  // Edge reste volontairement ouvert jusqu'à fermeture manuelle par l'utilisateur.
  await new Promise(() => {})
} catch (error) {
  console.error(`DEMO_ERROR: ${error instanceof Error ? error.message : String(error)}`)
  await new Promise(() => {})
}
