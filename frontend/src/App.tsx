import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Spinner } from './components/ui'
import { useAuth } from './lib/auth'
import { Activity } from './pages/Activity'
import { AgentDetail } from './pages/AgentDetail'
import { Agents } from './pages/Agents'
import { ApprovalReview } from './pages/ApprovalReview'
import { Approvals } from './pages/Approvals'
import { DataFiles } from './pages/DataFiles'
import { Home } from './pages/Home'
import { Knowledge } from './pages/Knowledge'
import { Login } from './pages/Login'
import { Outbox } from './pages/Outbox'
import { RunView } from './pages/RunView'
import { Runs } from './pages/Runs'
import { SettingsPage } from './pages/Settings'
import { Studio } from './pages/Studio'

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen grid place-items-center"><Spinner className="h-6 w-6 text-ink-3" /></div>
  if (!user) return <Routes><Route path="*" element={<Login />} /></Routes>
  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="studio" element={<Studio />} />
        <Route path="studio/:agentId" element={<Studio />} />
        <Route path="agents" element={<Agents />} />
        <Route path="agents/:agentId" element={<AgentDetail />} />
        <Route path="agents/:agentId/runs/:runId" element={<RunView />} />
        <Route path="runs" element={<Runs />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="approvals/:approvalId" element={<ApprovalReview />} />
        <Route path="data" element={<DataFiles />} />
        <Route path="knowledge" element={<Knowledge />} />
        <Route path="outbox" element={<Outbox />} />
        <Route path="activity" element={<Activity />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
