/* Read-only Playwright recording driver for AIGATOS.
 * Requires Playwright to be installed under demo/temp/capture-tools.
 * It records WebM under demo/temp; FFmpeg conversion is documented separately.
 */
import { createRequire } from 'node:module'
import { mkdir, rename } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const scriptDir = dirname(fileURLToPath(import.meta.url))
const { chromium } = require(resolve(scriptDir, 'temp/capture-tools/node_modules/playwright'))

const mode = process.argv.includes('workflow') ? 'workflow' : 'jury'
const fast = process.argv.includes('--fast')
const baseUrl = 'http://127.0.0.1:5173'
const tempDir = resolve(scriptDir, 'temp')
const target = resolve(tempDir, mode === 'jury' ? 'AIGATOS_Demo_Jury.webm' : 'AIGATOS_Agentic_Workflow_Demo.webm')
await mkdir(tempDir, { recursive: true })

const browser = await chromium.launch({ headless: false, args: ['--start-fullscreen','--disable-notifications'] })
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, recordVideo: { dir: tempDir, size: { width: 1920, height: 1080 } }, acceptDownloads: true })
const page = await context.newPage()
const blockedWrites = []
await page.route('**/*', async route => {
  const method = route.request().method()
  if (!['GET','HEAD','OPTIONS'].includes(method)) {
    blockedWrites.push(`${method} ${route.request().url()}`)
    await route.abort('blockedbyclient')
    return
  }
  await route.continue()
})

const scale = fast ? .03 : 1
const wait = seconds => page.waitForTimeout(seconds * 1000 * scale)
async function go(path, seconds) {
  await page.goto(baseUrl + path, { waitUntil: 'networkidle' })
  await wait(seconds)
}
async function titleCard(title, subtitle, kicker, seconds=20) {
  await page.goto(baseUrl, { waitUntil: 'networkidle' })
  await page.evaluate(({title,subtitle,kicker}) => {
    const cover=document.createElement('div')
    cover.id='aigatos-recording-title'
    Object.assign(cover.style,{position:'fixed',inset:'0',zIndex:'99999',display:'grid',placeContent:'center',textAlign:'center',background:'linear-gradient(135deg,#071523,#123a5d)',color:'white',fontFamily:'Segoe UI,Arial',padding:'80px'})
    const safe=document.createElement('div')
    const h=document.createElement('h1');h.textContent=title;Object.assign(h.style,{fontSize:'86px',letterSpacing:'12px',margin:'0 0 24px'})
    const s=document.createElement('p');s.textContent=subtitle;Object.assign(s.style,{fontSize:'34px',margin:'0 0 18px'})
    const k=document.createElement('p');k.textContent=kicker;Object.assign(k.style,{fontSize:'23px',color:'#8fcaff'})
    safe.append(h,s,k);cover.append(safe);document.body.append(cover)
  },{title,subtitle,kicker})
  await wait(seconds)
}

if (mode === 'jury') {
  await titleCard('AIGATOS','Plateforme Agentic AI de supervision OTA automobile','Démonstration du prototype')
  await go('/',40)
  await go('/campaigns',12)
  const campaignLink=page.locator('a[href^="/campaigns/"]').first();if(await campaignLink.count())await campaignLink.click();await wait(33)
  await go('/vehicles',8)
  await page.getByLabel('Révision matérielle').click();await page.getByRole('option',{name:'HW_REV_B'}).click();await wait(12)
  const vehicleLink=page.locator('a[href^="/vehicles/"]').first();if(await vehicleLink.count())await vehicleLink.click();await wait(25)
  await go('/incidents/dedbd95d-8029-4116-ae6e-6bc220fdb347',50)
  await go('/workflows/cde0930e-b80a-447f-8ccc-92c6d97b11ba/interaction',8)
  await page.getByRole('button',{name:'Replay'}).click();await wait(62)
  await go('/workflows/cde0930e-b80a-447f-8ccc-92c6d97b11ba',42)
  await go('/recommendations',25)
  await go('/approval',10)
  await go('/ai-explanation',35)
  await go('/reports',40)
  await go('/',30)
} else {
  await titleCard('AIGATOS','Interaction et maturité des agents','Workflow OTA démontré en environnement simulé')
  await go('/workflows/cde0930e-b80a-447f-8ccc-92c6d97b11ba/interaction',30)
  await page.getByRole('button',{name:'Replay'}).click()
  await wait(200)
  await wait(20)
}

if (blockedWrites.length) throw new Error(`Requêtes d'écriture bloquées : ${blockedWrites.join(', ')}`)
const video = page.video()
await context.close()
if (!video) throw new Error('Capture vidéo Playwright indisponible')
const generated = await video.path()
await rename(generated, target)
await browser.close()
console.log(`Capture WebM créée : ${target}`)
console.log('Convertir ensuite en MP4 H.264 avec la commande documentée dans README.md.')

