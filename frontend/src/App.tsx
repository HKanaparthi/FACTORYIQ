import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { OperationsOverview } from './pages/OperationsOverview'
import { EquipmentDetails } from './pages/EquipmentDetails'
import { InvestigationWorkspace } from './pages/InvestigationWorkspace'
import { EvidenceExplorer } from './pages/EvidenceExplorer'
import { HumanReview } from './pages/HumanReview'
import { EvaluationWorkspace } from './pages/EvaluationWorkspace'
import { DEMO_MODE } from './demo'
import { DemoPlaybackProvider } from './demo/DemoPlaybackContext'
import { DemoBanner } from './demo/DemoBanner'

function AppRoutes() {
  return (
    <Layout>
      {DEMO_MODE && <DemoBanner />}
      <Routes>
        <Route path="/"              element={<OperationsOverview />} />
        <Route path="/equipment"     element={<Navigate to="/equipment/PUMP-01" replace />} />
        <Route path="/equipment/:assetId" element={<EquipmentDetails />} />
        <Route path="/investigate"   element={<InvestigationWorkspace />} />
        <Route path="/evidence"      element={<EvidenceExplorer />} />
        <Route path="/review"        element={<HumanReview />} />
        <Route path="/evaluation"    element={<EvaluationWorkspace />} />
      </Routes>
    </Layout>
  )
}

export default function App() {
  if (DEMO_MODE) {
    return (
      <BrowserRouter>
        <DemoPlaybackProvider>
          <AppRoutes />
        </DemoPlaybackProvider>
      </BrowserRouter>
    )
  }
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
