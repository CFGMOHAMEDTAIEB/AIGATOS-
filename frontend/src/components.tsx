import type { ReactNode } from 'react'
import { Alert, Box, Card, CardContent, Chip, CircularProgress, Stack, Typography } from '@mui/material'

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?:string; title:string; description:string; action?:ReactNode }) {
  return <Stack className="page-header" direction={{xs:'column',sm:'row'}} justifyContent="space-between" alignItems={{sm:'flex-end'}} gap={2.5} mb={3.5}>
    <Box>{eyebrow && <Stack direction="row" alignItems="center" gap={1} mb={.5}><Box className="eyebrow-marker"/><Typography variant="overline" color="primary">{eyebrow}</Typography></Stack>}<Typography component="h1" variant="h1">{title}</Typography><Typography color="text.secondary" mt={1} maxWidth={760} fontSize={{xs:'.94rem',sm:'1rem'}}>{description}</Typography></Box>{action&&<Box className="page-header__action">{action}</Box>}
  </Stack>
}
export function QueryState({ loading, error, empty, children }: {loading:boolean;error:Error|null;empty?:boolean;children:ReactNode}) {
  if (loading) return <Stack className="state-panel" alignItems="center" py={10} gap={2}><CircularProgress aria-label="Chargement" size={34}/><Typography fontWeight={700}>Chargement des données…</Typography><Typography variant="body2" color="text.secondary">Connexion sécurisée aux services AIGATOS</Typography></Stack>
  if (error) return <Alert severity="error"><strong>API indisponible.</strong> {error.message}</Alert>
  if (empty) return <Alert severity="info">Aucune donnée disponible pour cette vue.</Alert>
  return <>{children}</>
}
export function MetricCard({ label, value, helper, tone='primary' }: {label:string;value:string|number;helper?:string;tone?:'primary'|'success'|'error'|'warning'}) {
  return <Card className={`metric-card metric-card--${tone}`}><CardContent><Stack direction="row" alignItems="center" justifyContent="space-between"><Typography variant="overline" color="text.secondary">{label}</Typography><Box className="metric-card__dot"/></Stack><Typography variant="h4" color={`${tone}.main`} fontWeight={820} mt={.7}>{value}</Typography>{helper && <Typography variant="body2" color="text.secondary" mt={.65}>{helper}</Typography>}</CardContent></Card>
}
export function StatusChip({ value }: {value:string}) {
  const v=value.toUpperCase(); const color = v.includes('SUCCESS')||v.includes('APPROVED')||v.includes('OPÉRATIONNEL')?'success':v.includes('FAIL')||v.includes('REJECT')||v.includes('INDISPONIBLE')?'error':v.includes('WAIT')||v.includes('PENDING')||v.includes('PROPOSED')?'warning':'default'
  return <Chip size="small" label={value.replaceAll('_',' ')} color={color} variant={color==='default'?'outlined':'filled'} />
}
export function SectionCard({ title, subtitle, children }: {title:string;subtitle?:string;children:ReactNode}) {
  return <Card className="section-card"><CardContent><Stack direction="row" alignItems="center" gap={1.2}><Box className="section-card__accent"/><Typography variant="h2" component="h2">{title}</Typography></Stack>{subtitle&&<Typography color="text.secondary" variant="body2" mt={.65} mb={2.2}>{subtitle}</Typography>}<Box mt={subtitle?0:2.2}>{children}</Box></CardContent></Card>
}
export const pct = (value:number) => new Intl.NumberFormat('fr-FR',{style:'percent',maximumFractionDigits:1}).format(value)
export const utc = (value:string|null|undefined) => value ? new Intl.DateTimeFormat('fr-FR',{dateStyle:'medium',timeStyle:'short',timeZone:'UTC'}).format(new Date(value))+' UTC' : '—'
export const shortId = (value:string) => `${value.slice(0,8)}…${value.slice(-4)}`
