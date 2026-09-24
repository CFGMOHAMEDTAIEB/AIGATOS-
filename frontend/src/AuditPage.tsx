import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Chip, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material'
import RefreshRounded from '@mui/icons-material/RefreshRounded'
import { apiGet, endpoints } from './api'
import { PageHeader, QueryState, shortId, StatusChip, utc } from './components'
import { useOperationalSession } from './SessionContext'
import type { AuditResponse } from './types'

export function AuditPage(){
  const {activeSimulationId}=useOperationalSession();const q=useQuery({queryKey:['audit',activeSimulationId],queryFn:()=>apiGet<AuditResponse>(endpoints.audit(activeSimulationId)),enabled:Boolean(activeSimulationId),refetchInterval:15_000})
  if(!activeSimulationId)return <><PageHeader eyebrow="Traçabilité" title="Historique d’audit" description="Aucun contexte opérationnel sélectionné."/><Alert severity="info">Sélectionnez une campagne ou une simulation.</Alert></>
  return <><PageHeader eyebrow="Traçabilité" title="Historique d’audit" description="Entrées immuables de la simulation et du workflow actif." action={<Button startIcon={<RefreshRounded/>} variant="outlined" onClick={()=>q.refetch()}>Actualiser</Button>}/><QueryState loading={q.isLoading} error={q.error} empty={!q.data?.entries.length}><TableContainer component={Paper}><Table><TableHead><TableRow><TableCell>Horodatage</TableCell><TableCell>Catégorie</TableCell><TableCell>Acteur</TableCell><TableCell>Action</TableCell><TableCell>Statut</TableCell><TableCell>Résumé</TableCell><TableCell>ID</TableCell></TableRow></TableHead><TableBody>{q.data?.entries.map(entry=><TableRow key={entry.id} hover><TableCell>{utc(entry.timestamp)}</TableCell><TableCell><Chip size="small" label={entry.category} variant="outlined"/></TableCell><TableCell>{entry.actor}</TableCell><TableCell>{entry.action.replaceAll('_',' ')}</TableCell><TableCell><StatusChip value={entry.status}/></TableCell><TableCell>{entry.summary}</TableCell><TableCell title={entry.id}>{shortId(entry.id)}</TableCell></TableRow>)}</TableBody></Table></TableContainer></QueryState></>
}
