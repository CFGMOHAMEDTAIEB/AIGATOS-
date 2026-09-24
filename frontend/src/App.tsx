import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './Layout'
import { CampaignDetailPage, CampaignsPage, DashboardPage, IncidentPage, NotFoundPage, ReportsPage, VehicleDetailPage, VehiclesPage } from './pages'
import { LiveSimulationPage } from './LiveSimulationPage'
import { AnalysisPage } from './AnalysisPage'
import { AuditPage } from './AuditPage'

export function App(){return <Routes><Route element={<Layout/>}>
  <Route index element={<DashboardPage/>}/>
  <Route path="campaigns" element={<CampaignsPage/>}/><Route path="campaigns/:id" element={<CampaignDetailPage/>}/>
  <Route path="vehicles" element={<VehiclesPage/>}/><Route path="vehicles/:id" element={<VehicleDetailPage/>}/>
  <Route path="simulation" element={<LiveSimulationPage/>}/>
  <Route path="incidents" element={<IncidentPage/>}/>
  <Route path="analysis" element={<AnalysisPage/>}/>
  <Route path="reports" element={<ReportsPage/>}/>
  <Route path="audit" element={<AuditPage/>}/>
  <Route path="live-simulation" element={<Navigate to="/simulation" replace/>}/>
  <Route path="workflows/*" element={<Navigate to="/analysis" replace/>}/>
  <Route path="agent-maturity" element={<Navigate to="/analysis" replace/>}/>
  <Route path="recommendations" element={<Navigate to="/analysis" replace/>}/>
  <Route path="approval" element={<Navigate to="/analysis" replace/>}/>
  <Route path="ai-explanation" element={<Navigate to="/reports" replace/>}/>
  <Route path="incidents/:id" element={<Navigate to="/incidents" replace/>}/>
  <Route path="*" element={<NotFoundPage/>}/>
</Route></Routes>}
