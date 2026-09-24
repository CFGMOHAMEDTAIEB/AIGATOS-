import { useState } from 'react'
import { Alert, Button, Paper, Stack, TextField, Typography } from '@mui/material'
import { apiPost } from './api'
import { PageHeader } from './components'
import type { LLMStatus } from './types'

type Reply = { provider:string; model:string; reply:string }
const key=()=>globalThis.crypto?.randomUUID?.()??String(Date.now())

export function AssistantPage(){
  const [status,setStatus]=useState<LLMStatus|null>(null)
  const [prompt,setPrompt]=useState('')
  const [reply,setReply]=useState<Reply|null>(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  const check=async()=>{setBusy(true);setError('');setStatus(null);try{setStatus(await apiPost<LLMStatus>('/api/v1/llm/test',{},key()))}catch(e){setError(e instanceof Error?e.message:'Vérification du fournisseur impossible.')}finally{setBusy(false)}}
  const send=async()=>{setBusy(true);setError('');setReply(null);try{setReply(await apiPost<Reply>('/api/v1/llm/chat',{prompt},key()))}catch(e){setError(e instanceof Error?e.message:'Le message n’a pas pu être envoyé.')}finally{setBusy(false)}}
  const available=Boolean(status?.configured&&status.reachable&&status.authorized&&status.structured_output_supported)
  return <><PageHeader eyebrow="Assistant" title="Parler au modèle LLM" description="Conversation texte via le fournisseur configuré sur le backend. Aucun outil métier n’est accessible depuis cet assistant."/>
    <Paper variant="outlined" sx={{p:{xs:2,md:3},maxWidth:900}}><Stack spacing={2}>
      <Alert severity="info">Pour la sécurité, configurez une clé renouvelée dans l’environnement du backend. Les clés ne doivent pas être saisies dans cette page.</Alert>
      <Stack direction={{xs:'column',sm:'row'}} alignItems={{sm:'center'}} spacing={1.5}>
        <Button variant="outlined" disabled={busy} onClick={check}>{busy?'Vérification…':'Vérifier le fournisseur'}</Button>
        {status&&<Typography role="status" variant="body2">{available?`Disponible · ${status.provider} / ${status.model}`:`Indisponible${status.error_code?` · ${status.error_code}`:''}`}</Typography>}
      </Stack>
      {error&&<Alert severity="error">{error}</Alert>}
      <TextField label="Votre message" value={prompt} onChange={e=>setPrompt(e.target.value)} multiline minRows={3} maxRows={8} inputProps={{maxLength:4000}} disabled={!available||busy} helperText="Maximum 4 000 caractères · aucun accès aux données opérationnelles"/>
      <Button variant="contained" disabled={!available||busy||!prompt.trim()} onClick={send}>{busy?'Envoi…':'Envoyer au modèle'}</Button>
      {reply&&<Paper variant="outlined" sx={{p:2}}><Typography variant="caption" color="text.secondary">{reply.provider} · {reply.model}</Typography><Typography sx={{whiteSpace:'pre-wrap',mt:1}}>{reply.reply}</Typography></Paper>}
    </Stack></Paper>
  </>
}
