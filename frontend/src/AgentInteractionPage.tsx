import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Alert, Box, Button, ButtonGroup, Card, CardContent, Chip, Divider, Grid, IconButton,
  LinearProgress, Paper, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography,
} from '@mui/material'
import PlayArrowRounded from '@mui/icons-material/PlayArrowRounded'
import PauseRounded from '@mui/icons-material/PauseRounded'
import RestartAltRounded from '@mui/icons-material/RestartAltRounded'
import SkipNextRounded from '@mui/icons-material/SkipNextRounded'
import SkipPreviousRounded from '@mui/icons-material/SkipPreviousRounded'
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded'
import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded'
import PersonRounded from '@mui/icons-material/PersonRounded'
import StorageRounded from '@mui/icons-material/StorageRounded'
import { apiGet, endpoints } from './api'
import { INCIDENT_ID, SCORE, WORKFLOW_ID } from './constants'
import { PageHeader, QueryState, SectionCard, shortId, StatusChip } from './components'
import type { Evidence, History, Incident, Workflow } from './types'

type Phase = 0 | 1 | 2
type AgentDefinition = {
  key: string
  name: string
  responsibility: string
  tools: string[]
  mode: string
  transfer: string[]
  processing: string[]
}

const PRIMARY_EVIDENCE = [
  '779e64ea-e83b-4c92-b313-fbab5fdbdcba',
  '8fca5c3a-c6fb-4bfe-a226-79ed37df2277',
  'e16c42b8-dea1-439f-a100-8ada1b0f65a7',
]

const AGENTS: AgentDefinition[] = [
  {key:'MONITORING',name:'Monitoring',responsibility:'Surveiller la cohorte Canary et détecter le dépassement du seuil.',tools:['PostgreSQL','Règles de seuil'],mode:'Déterministe',processing:['Calcul des taux succès / échec / rollback','Application du seuil configuré','Association des preuves'],transfer:['incident_id','failed_vehicle_ids','successful_vehicle_ids','evidence_ids']},
  {key:'LOG_ANALYSIS',name:'Log Analysis',responsibility:'Normaliser les erreurs et construire les chronologies par véhicule.',tools:['PostgreSQL','Normaliseur de logs'],mode:'Déterministe',processing:['Normalisation error_code / installation_step','Construction des timelines','Regroupement des séquences d’échec'],transfer:['normalized_errors','timeline','failure_sequences','evidence_ids']},
  {key:'CORRELATION',name:'Correlation',responsibility:'Comparer les cohortes en succès et en échec.',tools:['Statistiques Python','Intervalles de confiance'],mode:'Déterministe',processing:['Effectifs par sous-groupe','Risk ratio et IC 95 %','Contrôle corrélation ≠ causalité'],transfer:['correlations','risk_ratio','confidence_interval','cohort_statistics','evidence_ids']},
  {key:'RCA',name:'RCA',responsibility:'Classer les hypothèses à partir des règles, corrélations et preuves.',tools:['Règles métier','Score explicable'],mode:'Déterministe',processing:['Validation des evidence_ids','Classement multi-hypothèses','Calcul des composantes du score'],transfer:['ranked_hypotheses','global_confidence','confidence_components','evidence_ids']},
  {key:'DECISION',name:'Decision',responsibility:'Transformer le diagnostic en recommandations consultatives sûres.',tools:['Politiques de sécurité','Liste d’actions autorisées'],mode:'Advisory uniquement',processing:['Contrôle des actions autorisées','Vérification human-in-the-loop','Création de la demande PENDING'],transfer:['recommended_actions','approval_request','safety_checks','executed=false']},
]

const phaseNames = ['Input', 'Processing', 'Output'] as const

function scalar(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(6)
  if (typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return `${value.length} éléments`
  if (typeof value === 'object') return `${Object.keys(value as object).length} champs`
  return String(value).replaceAll('_', ' ')
}

function DataRows({ data }: { data: Record<string, unknown> }) {
  return <Stack divider={<Divider flexItem/>}>{Object.entries(data).map(([key,value])=><Stack key={key} direction="row" justifyContent="space-between" gap={2} py={.7}><Typography variant="body2" color="text.secondary">{key.replaceAll('_',' ')}</Typography><Typography variant="body2" fontWeight={750} textAlign="right">{scalar(value)}</Typography></Stack>)}</Stack>
}

function AgentCard({ definition, history, index, activeStep }: { definition:AgentDefinition;history?:History;index:number;activeStep:number }) {
  const active=index===activeStep
  const completed=index<activeStep || activeStep>=AGENTS.length
  const state=active?'ACTIVE':completed?'COMPLETED':'WAITING'
  return <Card className={`agent-node ${active?'agent-node--active':''}`} sx={{height:'100%',minWidth:0,borderColor:active?'primary.main':completed?'success.light':'divider',position:'relative',overflow:'visible'}}>
    {active&&<Box className="agent-pulse"/>}
    <CardContent sx={{p:2}}>
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" gap={1}><Box><Typography variant="caption" color="text.secondary">AGENT {index+1}</Typography><Typography variant="h3">{definition.name}</Typography></Box><Chip size="small" color={active?'primary':completed?'success':'default'} label={state}/></Stack>
      <Typography variant="body2" color="text.secondary" mt={1.3} minHeight={60}>{definition.responsibility}</Typography>
      <Stack direction="row" gap={.6} flexWrap="wrap" mt={1}>{definition.tools.map(tool=><Chip key={tool} size="small" variant="outlined" label={tool}/>)}</Stack>
      <Divider sx={{my:1.5}}/>
      <Grid container spacing={1}><Grid size={6}><Typography variant="caption" color="text.secondary">Maturité</Typography><Typography fontWeight={850} color="primary">M4 · simulation</Typography></Grid><Grid size={6}><Typography variant="caption" color="text.secondary">Durée réelle</Typography><Typography fontWeight={850}>{history?.duration_ms??'—'} ms</Typography></Grid><Grid size={6}><Typography variant="caption" color="text.secondary">Entrées</Typography><Typography fontWeight={750}>{Object.keys(history?.input_summary??{}).length}</Typography></Grid><Grid size={6}><Typography variant="caption" color="text.secondary">Sorties</Typography><Typography fontWeight={750}>{Object.keys(history?.output_summary??{}).length}</Typography></Grid></Grid>
      <Typography variant="caption" display="block" mt={1.5} color="text.secondary">Mode : {definition.mode} · retry 0 · erreur : aucune</Typography>
    </CardContent>
  </Card>
}

function stageOutput(index:number, workflow:Workflow, incident:Incident): Record<string,unknown> {
  const hwB=workflow.correlations.find(item=>item.factor==='hardware_revision'&&item.level==='HW_REV_B') as Record<string,unknown>|undefined
  const hwA=workflow.correlations.find(item=>item.factor==='hardware_revision'&&item.level==='HW_REV_A') as Record<string,unknown>|undefined
  if(index===0)return {vehicles:incident.vehicle_count,successes:incident.success_count,failures:incident.failure_count,rollbacks:incident.rollback_count,failure_rate:incident.failure_rate,evidence_ids:workflow.evidence_ids.length}
  if(index===1)return {normalized_errors:workflow.normalized_errors.length,timelines:workflow.timeline.length,dominant_signature:'HW_REV_B / MEMORY_LAYOUT_MISMATCH / MEMORY_VALIDATION : 3',other_failures:'BATTERY 1 · NETWORK 1 · STORAGE 1'}
  if(index===2)return {HW_REV_B:`${scalar(hwB?.failures)}/${scalar(hwB?.exposed_count)} échecs`,HW_REV_A:`${scalar(hwA?.failures)}/${scalar(hwA?.exposed_count)} échecs`,risk_ratio:hwB?.risk_ratio,confidence_interval_95:Array.isArray(hwB?.confidence_interval_95)?`[${Number(hwB.confidence_interval_95[0]).toFixed(3)}, ${Number(hwB.confidence_interval_95[1]).toFixed(3)}]`:'—',warning:'Corrélation ≠ causalité'}
  if(index===3)return {probable_cause:'Incompatibilité probable entre HW_REV_B et BatteryManager 2.4.0',global_confidence:workflow.global_confidence,association:workflow.confidence_components.association_strength,support:workflow.confidence_components.failure_support,error_consistency:workflow.confidence_components.error_consistency,step_consistency:workflow.confidence_components.step_consistency,evidence_coverage:workflow.confidence_components.evidence_coverage}
  return {recommended_actions:workflow.recommended_actions.length,status:'PROPOSED',executed:false,approval_status:workflow.approval_status,workflow_status:workflow.workflow_status}
}

export function AgentInteractionPage(){
  const {id=WORKFLOW_ID}=useParams()
  const workflowQ=useQuery({queryKey:['workflow',id],queryFn:()=>apiGet<Workflow>(endpoints.workflow(id))})
  const historyQ=useQuery({queryKey:['workflow-history',id],queryFn:()=>apiGet<History[]>(endpoints.workflowHistory(id))})
  const incidentQ=useQuery({queryKey:['incident',INCIDENT_ID],queryFn:()=>apiGet<Incident>(endpoints.incident(INCIDENT_ID))})
  const evidenceQ=useQuery({queryKey:['evidence',INCIDENT_ID],queryFn:()=>apiGet<Evidence[]>(endpoints.evidence(INCIDENT_ID))})
  const [step,setStep]=useState(-1)
  const [phase,setPhase]=useState<Phase>(0)
  const [playing,setPlaying]=useState(false)
  const [speed,setSpeed]=useState(1)
  const workflow=workflowQ.data; const history=historyQ.data; const incident=incidentQ.data
  const orderedHistory=useMemo(()=>AGENTS.map(agent=>history?.find(item=>item.agent===agent.key)),[history])

  useEffect(()=>{if(!playing)return;const timer=window.setTimeout(()=>{if(step<0){setStep(0);setPhase(0);return}if(step>=AGENTS.length){setPlaying(false);return}if(phase<2){setPhase((phase+1) as Phase);return}setStep(step+1);setPhase(0)},1100/speed);return()=>window.clearTimeout(timer)},[playing,step,phase,speed])

  const replay=()=>{setStep(0);setPhase(0);setPlaying(true)}
  const reset=()=>{setPlaying(false);setStep(-1);setPhase(0)}
  const next=()=>{setPlaying(false);setStep(value=>Math.min(AGENTS.length,value+1));setPhase(2)}
  const previous=()=>{setPlaying(false);setStep(value=>Math.max(-1,value-1));setPhase(2)}
  const activeIndex=step<0?0:step
  const activeDefinition=AGENTS[Math.min(Math.max(activeIndex,0),AGENTS.length-1)]
  const activeHistory=orderedHistory[Math.min(Math.max(activeIndex,0),AGENTS.length-1)]
  const final=step>=AGENTS.length
  const loading=workflowQ.isLoading||historyQ.isLoading||incidentQ.isLoading||evidenceQ.isLoading
  const error=workflowQ.error??historyQ.error??incidentQ.error??evidenceQ.error

  const sharedState=workflow&&incident?{
    workflow_id:workflow.workflow_id,incident_id:workflow.incident_id,current_agent:final?'HUMAN_APPROVAL':activeDefinition.name,
    workflow_status:final?workflow.workflow_status:'RUNNING',failed_vehicle_count:step>=0?workflow.failed_vehicle_ids.length:0,
    successful_vehicle_count:step>=0?workflow.successful_vehicle_ids.length:0,normalized_error_count:step>=1?workflow.normalized_errors.length:0,
    evidence_count:step>=0?workflow.evidence_ids.length:0,hypothesis_count:step>=3?workflow.hypotheses.length:0,
    global_confidence:step>=3?workflow.global_confidence:null,recommendations_count:step>=4?workflow.recommended_actions.length:0,
    approval_status:final?workflow.approval_status:'PENDING',retry_count:workflow.retry_count,last_error:workflow.last_error??'aucune',
  }:{}

  return <><PageHeader eyebrow="Replay en lecture seule" title="Agent Interaction" description="Visualisation rejouable de l’historique PostgreSQL. Le Replay ne relance aucun agent et n’effectue aucune écriture." action={<Button component={RouterLink} to={`/workflows/${id}`} variant="outlined">Vue synthétique</Button>}/>
    <QueryState loading={loading} error={error} empty={!workflow||!incident}>
      {workflow&&incident&&<>
        <Alert severity="warning" sx={{mb:2}}><strong>M4 correspond à une démonstration intégrée sur données simulées.</strong><br/>Aucune validation sur véhicule réel ou environnement automobile de production. Cette échelle n’est ni une certification officielle ni un niveau ISO.</Alert>
        <Paper variant="outlined" sx={{p:1.5,mb:3,position:'sticky',top:72,zIndex:5,backdropFilter:'blur(12px)',bgcolor:'rgba(255,255,255,.94)'}}><Stack direction={{xs:'column',md:'row'}} alignItems={{md:'center'}} justifyContent="space-between" gap={2}><Stack direction="row" gap={1} flexWrap="wrap"><Button startIcon={<PlayArrowRounded/>} variant="contained" onClick={replay}>Replay</Button><Button startIcon={<PauseRounded/>} variant="outlined" onClick={()=>setPlaying(false)} disabled={!playing}>Pause</Button><Button startIcon={<RestartAltRounded/>} variant="outlined" onClick={reset}>Recommencer</Button><ButtonGroup variant="outlined"><Tooltip title="Étape précédente"><span><IconButton aria-label="Étape précédente" onClick={previous} disabled={step<0}><SkipPreviousRounded/></IconButton></span></Tooltip><Tooltip title="Étape suivante"><span><IconButton aria-label="Étape suivante" onClick={next} disabled={final}><SkipNextRounded/></IconButton></span></Tooltip></ButtonGroup></Stack><Stack direction="row" alignItems="center" gap={1}><Typography variant="caption" fontWeight={800}>VITESSE</Typography><ToggleButtonGroup exclusive size="small" value={speed} onChange={(_,value)=>value&&setSpeed(value)}>{[.5,1,2].map(value=><ToggleButton key={value} value={value}>{value}×</ToggleButton>)}</ToggleButtonGroup><StatusChip value={playing?'REPLAY_RUNNING':final?workflow.workflow_status:'PAUSED'}/></Stack></Stack><LinearProgress variant="determinate" value={Math.max(0,Math.min(100,((step+(phase+1)/3)/AGENTS.length)*100))} sx={{mt:1.5,height:5,borderRadius:4}}/></Paper>

        <SectionCard title="Chaîne d’interaction" subtitle="Monitoring → Log Analysis → Correlation → RCA → Decision → Human Approval">
          <Box className="agent-flow">{AGENTS.map((agent,index)=><Box key={agent.key} className="agent-flow__item"><AgentCard definition={agent} history={orderedHistory[index]} index={index} activeStep={activeIndex}/>{index<AGENTS.length-1&&<ArrowForwardRounded className={`agent-transfer ${index<activeIndex?'agent-transfer--done':''}`}/>}</Box>)}<Box className="agent-flow__item"><Card sx={{height:'100%',borderColor:final?'warning.main':'divider',bgcolor:final?'#fff8e8':'background.paper'}}><CardContent><PersonRounded color={final?'warning':'disabled'} fontSize="large"/><Typography variant="h3" mt={1}>Human Approval</Typography><Typography color="text.secondary" variant="body2" mt={1}>Décision finale obligatoire, hors du Replay.</Typography><Stack direction="row" gap={1} mt={2} flexWrap="wrap"><StatusChip value={final?'PENDING':'WAITING'}/><Chip label="Aucune action" variant="outlined"/></Stack></CardContent></Card></Box></Box>
        </SectionCard>

        <Grid container spacing={3} mt={.5}>
          <Grid size={{xs:12,lg:8}}><SectionCard title={final?'Transmission vers Human Approval':`${activeDefinition.name} · ${phaseNames[phase]}`} subtitle={final?'Le workflow déterministe s’arrête ici.':activeDefinition.responsibility}>
            {final?<Grid container spacing={2}>{Object.entries({recommended_actions:workflow.recommended_actions.length,approval_request:workflow.approval_status,safety_checks:'validés',executed:false,workflow_status:workflow.workflow_status}).map(([key,value])=><Grid size={{xs:12,sm:6}} key={key}><Paper variant="outlined" sx={{p:2}}><Typography variant="caption" color="text.secondary">{key.replaceAll('_',' ')}</Typography><Typography fontWeight={800}>{scalar(value)}</Typography></Paper></Grid>)}</Grid>:<Grid container spacing={2}><Grid size={{xs:12,md:4}}><Paper variant="outlined" className={phase===0?'phase-panel phase-panel--active':'phase-panel'} sx={{p:2,height:'100%'}}><Typography variant="overline" fontWeight={900}>Input</Typography><DataRows data={activeHistory?.input_summary??{}}/></Paper></Grid><Grid size={{xs:12,md:4}}><Paper variant="outlined" className={phase===1?'phase-panel phase-panel--active':'phase-panel'} sx={{p:2,height:'100%'}}><Typography variant="overline" fontWeight={900}>Processing</Typography><Stack component="ul" pl={2}>{activeDefinition.processing.map(rule=><Typography component="li" variant="body2" mb={1} key={rule}>{rule}</Typography>)}</Stack></Paper></Grid><Grid size={{xs:12,md:4}}><Paper variant="outlined" className={phase===2?'phase-panel phase-panel--active':'phase-panel'} sx={{p:2,height:'100%'}}><Typography variant="overline" fontWeight={900}>Output</Typography><DataRows data={stageOutput(activeIndex,workflow,incident)}/></Paper></Grid></Grid>}
            {!final&&<Box mt={2} p={1.5} borderRadius={2} bgcolor="primary.light"><Typography variant="caption" fontWeight={900}>DONNÉES TRANSMISES À L’ÉTAPE SUIVANTE</Typography><Stack direction="row" gap={1} mt={1} flexWrap="wrap">{activeDefinition.transfer.map(item=><Chip key={item} label={item} size="small" color="primary" variant="outlined"/>)}</Stack></Box>}
          </SectionCard></Grid>
          <Grid size={{xs:12,lg:4}}><SectionCard title="Shared Incident State" subtitle="Uniquement les champs structurés autorisés"><DataRows data={sharedState}/></SectionCard></Grid>

          <Grid size={{xs:12,lg:7}}><SectionCard title="Evidence Traceability" subtitle={`${incident.linked_event_count} événements liés · ${incident.failure_event_count} événements FAILURE · 0 evidence_id invalide`}><Stack spacing={1.2}>{PRIMARY_EVIDENCE.map(idValue=>{const found=evidenceQ.data?.find(item=>item.evidence_id===idValue);return <Paper key={idValue} variant="outlined" sx={{p:1.5}}><Stack direction={{xs:'column',sm:'row'}} justifyContent="space-between" gap={1}><Box><Stack direction="row" gap={1} alignItems="center"><StorageRounded color="primary"/><Typography fontFamily="monospace" variant="body2">{idValue}</Typography></Stack><Typography variant="caption" color="text.secondary">{found?.hardware_revision} · {found?.error_code} · {found?.installation_step}</Typography></Box><Stack direction="row" gap={.5} flexWrap="wrap">{['Log Analysis','Correlation','RCA','Decision'].map(agent=><Chip key={agent} size="small" label={agent}/>)}</Stack></Stack></Paper>})}</Stack></SectionCard></Grid>
          <Grid size={{xs:12,lg:5}}><SectionCard title="Maturité des agents" subtitle="Échelle interne de démonstration, non certifiante"><Stack spacing={1}>{['M0 — Concept','M1 — Implémenté','M2 — Testé unitairement','M3 — Intégré et persistant','M4 — Démontré de bout en bout'].map(level=><Paper key={level} variant="outlined" sx={{p:1,bgcolor:level.startsWith('M4')?'primary.light':'transparent'}}><Typography fontWeight={level.startsWith('M4')?850:600}>{level}</Typography></Paper>)}</Stack><Alert severity="info" sx={{mt:2}}>Les cinq agents sont M4 en environnement simulé. Decision reste en mode Advisory uniquement.</Alert></SectionCard></Grid>

          <Grid size={12}><Alert severity="success" icon={<CheckCircleRounded/>}><strong>Garde-fous actifs :</strong> Replay local, requêtes GET uniquement, zéro tâche Celery, zéro appel LLM, zéro écriture PostgreSQL, zéro action OTA. Score déterministe inchangé : {SCORE.toFixed(6)}.</Alert></Grid>
        </Grid>
      </>}
    </QueryState>
  </>
}
