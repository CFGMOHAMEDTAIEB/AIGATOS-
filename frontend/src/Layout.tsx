import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  Alert, AppBar, Avatar, Box, Chip, Divider, Drawer, FormControl, IconButton, InputLabel,
  List, ListItemButton, ListItemIcon, ListItemText, MenuItem, Select, Stack,
  Toolbar, Typography, useMediaQuery,
} from '@mui/material'
import { useTheme } from '@mui/material/styles'
import MenuRounded from '@mui/icons-material/MenuRounded'
import SpaceDashboardRounded from '@mui/icons-material/SpaceDashboardRounded'
import CampaignRounded from '@mui/icons-material/CampaignRounded'
import DirectionsCarRounded from '@mui/icons-material/DirectionsCarRounded'
import WarningAmberRounded from '@mui/icons-material/WarningAmberRounded'
import AccountTreeRounded from '@mui/icons-material/AccountTreeRounded'
import DescriptionRounded from '@mui/icons-material/DescriptionRounded'
import SensorsRounded from '@mui/icons-material/SensorsRounded'
import ScienceRounded from '@mui/icons-material/ScienceRounded'
import HistoryRounded from '@mui/icons-material/HistoryRounded'
import { useOperationalSession } from './SessionContext'
import { shortId, utc } from './components'

const width=276
const nav=[
  ['Tableau de bord','/',<SpaceDashboardRounded/>],
  ['Campagnes','/campaigns',<CampaignRounded/>],
  ['Véhicules','/vehicles',<DirectionsCarRounded/>],
  ['Simulation','/simulation',<ScienceRounded/>],
  ['Incidents','/incidents',<WarningAmberRounded/>],
  ['Analyse agentique','/analysis',<AccountTreeRounded/>],
  ['Rapports','/reports',<DescriptionRounded/>],
  ['Audit','/audit',<HistoryRounded/>],
] as const

export function Layout(){
  const theme=useTheme();const desktop=useMediaQuery(theme.breakpoints.up('md'));const [open,setOpen]=useState(false);const location=useLocation()
  const {contexts,active,activeSimulationId,selectSimulation,error}=useOperationalSession()
  const selectedContextId=contexts.some(item=>item.simulation_id===activeSimulationId)?activeSimulationId:''
  const drawer=<Box className="app-drawer">
    <Stack className="brand-block" direction="row" alignItems="center" gap={1.5}><Box className="brand-mark"><Box/><Box/><Box/></Box><Box><Typography className="brand-name">AIGATOS</Typography><Typography className="brand-tagline">OTA OPERATIONS</Typography></Box></Stack>
    <Divider sx={{borderColor:'rgba(255,255,255,.08)',mx:2,mb:1}}/>
    <List className="nav-list">{nav.map(([label,to,icon])=><ListItemButton key={to} component={NavLink} to={to} end={to==='/'} selected={location.pathname===to||(to!=='/'&&location.pathname.startsWith(`${to}/`))} onClick={()=>setOpen(false)}><ListItemIcon>{icon}</ListItemIcon><ListItemText primary={label}/><Box className="nav-active-indicator"/></ListItemButton>)}</List>
    <Box mt="auto" px={2.5} pb={2.5}><Divider sx={{borderColor:'rgba(255,255,255,.08)',mb:2}}/><Stack direction="row" alignItems="flex-start" gap={1.2}><Box className="live-dot" mt={.6}/><Box><Typography variant="caption" fontWeight={800} color="#e7f3ff">Environnement simulé</Typography><Typography variant="caption" display="block" color="#7890a8">Aucune action OTA réelle</Typography></Box></Stack></Box>
  </Box>
  return <Box sx={{display:'flex',minHeight:'100vh'}}>
    <AppBar className="topbar" position="fixed" elevation={0} sx={{ml:{md:`${width}px`},width:{md:`calc(100% - ${width}px)`}}}><Toolbar sx={{minHeight:{xs:74,md:84},gap:2}}><IconButton aria-label="Ouvrir le menu" onClick={()=>setOpen(true)} sx={{display:{md:'none'}}}><MenuRounded/></IconButton><Stack direction="row" alignItems="center" gap={1.3} minWidth={{lg:235}}><Avatar className="control-avatar"><SensorsRounded fontSize="small"/></Avatar><Box sx={{display:{xs:'none',lg:'block'}}}><Typography fontWeight={790}>Centre de contrôle OTA</Typography><Typography variant="caption" color="text.secondary">Supervision et diagnostic</Typography></Box></Stack><FormControl size="small" sx={{ml:'auto',minWidth:{xs:190,sm:310,lg:390}}}><InputLabel>Contexte opérationnel</InputLabel><Select label="Contexte opérationnel" value={selectedContextId} onChange={event=>selectSimulation(event.target.value)}>{contexts.map(item=><MenuItem key={item.simulation_id} value={item.simulation_id}><Stack minWidth={0}><Typography fontWeight={750} noWrap>{item.campaign_name}</Typography><Typography variant="caption" color="text.secondary">{shortId(item.simulation_id)} · {item.software_version??'version non renseignée'}</Typography></Stack></MenuItem>)}</Select></FormControl>{active&&<Stack sx={{display:{xs:'none',xl:'flex'}}} alignItems="flex-end" minWidth={180}><Stack direction="row" gap={1} alignItems="center"><Chip size="small" label={active.source==='LIVE_SIMULATION'?'SIMULATION':'HISTORIQUE'} color={active.source==='LIVE_SIMULATION'?'secondary':'default'} variant="outlined"/><Typography variant="caption" fontWeight={750}>{active.vehicle_count} véhicules</Typography></Stack><Typography variant="caption" color="text.secondary">Actualisé {utc(active.updated_at)}</Typography></Stack>}</Toolbar></AppBar>
    <Box component="nav" aria-label="Navigation principale" sx={{width:{md:width},flexShrink:{md:0}}}><Drawer variant={desktop?'permanent':'temporary'} open={desktop||open} onClose={()=>setOpen(false)} ModalProps={{keepMounted:true}} sx={{'& .MuiDrawer-paper':{width,boxSizing:'border-box',border:0}}}>{drawer}</Drawer></Box>
    <Box component="main" className="app-main" sx={{flexGrow:1,width:{md:`calc(100% - ${width}px)`},pt:{xs:'102px',md:'118px'},pb:7,px:{xs:2,sm:3,lg:5}}}><Box maxWidth={1480} mx="auto">{error?<Alert severity="error"><strong>API indisponible.</strong> Impossible de charger le contexte opÃ©rationnel.</Alert>:<Outlet/>}</Box></Box>
  </Box>
}
