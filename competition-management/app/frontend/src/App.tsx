import { Navigate, Route, Routes } from 'react-router-dom'

import AppLayout from './components/AppLayout'
import { useAuth } from './components/AuthContext'
import AIPreAssessmentPage from './pages/AIPreAssessmentPage'
import AppealsPage from './pages/AppealsPage'
import AuditPage from './pages/AuditPage'
import CollaborationPage from './pages/CollaborationPage'
import CompetitionDetailPage from './pages/CompetitionDetailPage'
import CompetitionListPage from './pages/CompetitionListPage'
import ExportsPage from './pages/ExportsPage'
import JudgeTasksPage from './pages/JudgeTasksPage'
import LoginPage from './pages/LoginPage'
import MyTeamPage from './pages/MyTeamPage'
import NotificationsPage from './pages/NotificationsPage'
import ResultsPage from './pages/ResultsPage'
import ReviewOpsPage from './pages/ReviewOpsPage'
import StatisticsPage from './pages/StatisticsPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/competitions" replace />} />
        <Route path="competitions" element={<CompetitionListPage />} />
        <Route path="competitions/:id" element={<CompetitionDetailPage />} />
        <Route path="my-team" element={<MyTeamPage />} />
        <Route path="judge" element={<JudgeTasksPage />} />
        <Route path="results" element={<ResultsPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="appeals" element={<AppealsPage />} />
        <Route path="review-ops" element={<ReviewOpsPage />} />
        <Route path="ai-assessments" element={<AIPreAssessmentPage />} />
        <Route path="statistics" element={<StatisticsPage />} />
        <Route path="exports" element={<ExportsPage />} />
        <Route path="collaboration" element={<CollaborationPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="*" element={<Navigate to="/competitions" replace />} />
      </Route>
    </Routes>
  )
}
