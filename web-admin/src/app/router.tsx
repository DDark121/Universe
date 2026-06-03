import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { AdminLayout } from '@/app/layout/AdminLayout'
import { RequireAuth, RequirePasswordChange, RequireRoles } from '@/app/guards'
import { useAuth } from '@/shared/auth/AuthContext'
import { getDefaultRoute } from '@/shared/auth/defaultRoute'
import { Loader } from '@/shared/ui/Loader'

const LoginPage = lazy(async () => ({ default: (await import('@/pages/auth/LoginPage')).LoginPage }))
const PasswordChangePage = lazy(async () => ({ default: (await import('@/pages/auth/PasswordChangePage')).PasswordChangePage }))
const DashboardPage = lazy(async () => ({ default: (await import('@/pages/dashboard/DashboardPage')).DashboardPage }))
const UsersPage = lazy(async () => ({ default: (await import('@/pages/users/UsersPage')).UsersPage }))
const FacultiesPage = lazy(async () => ({ default: (await import('@/pages/structure/FacultiesPage')).FacultiesPage }))
const StreamsPage = lazy(async () => ({ default: (await import('@/pages/structure/StreamsPage')).StreamsPage }))
const GroupsPage = lazy(async () => ({ default: (await import('@/pages/structure/GroupsPage')).GroupsPage }))
const DisciplinesPage = lazy(async () => ({ default: (await import('@/pages/structure/DisciplinesPage')).DisciplinesPage }))
const AssignmentsPage = lazy(async () => ({ default: (await import('@/pages/assignments/AssignmentsPage')).AssignmentsPage }))
const SchedulePage = lazy(async () => ({ default: (await import('@/pages/schedule/SchedulePage')).SchedulePage }))
const InvitesPage = lazy(async () => ({ default: (await import('@/pages/telegram/InvitesPage')).InvitesPage }))
const BindingRequestsPage = lazy(async () => ({
  default: (await import('@/pages/telegram/BindingRequestsPage')).BindingRequestsPage,
}))
const SettingsPage = lazy(async () => ({ default: (await import('@/pages/settings/SettingsPage')).SettingsPage }))
const FaqCategoriesPage = lazy(async () => ({ default: (await import('@/pages/faq/FaqCategoriesPage')).FaqCategoriesPage }))
const FaqItemsPage = lazy(async () => ({ default: (await import('@/pages/faq/FaqItemsPage')).FaqItemsPage }))
const RatingConfigPage = lazy(async () => ({ default: (await import('@/pages/rating/RatingConfigPage')).RatingConfigPage }))
const EscalationRulesPage = lazy(async () => ({
  default: (await import('@/pages/escalations/EscalationRulesPage')).EscalationRulesPage,
}))
const RiskPage = lazy(async () => ({ default: (await import('@/pages/risk/RiskPage')).RiskPage }))
const RiskStudentPage = lazy(async () => ({ default: (await import('@/pages/risk/RiskStudentPage')).RiskStudentPage }))
const AttendanceReportPage = lazy(async () => ({
  default: (await import('@/pages/reports/AttendanceReportPage')).AttendanceReportPage,
}))
const LatesReportPage = lazy(async () => ({ default: (await import('@/pages/reports/LatesReportPage')).LatesReportPage }))
const AbsencesReportPage = lazy(async () => ({
  default: (await import('@/pages/reports/AbsencesReportPage')).AbsencesReportPage,
}))
const TeachersAnalyticsPage = lazy(async () => ({
  default: (await import('@/pages/analytics/TeachersAnalyticsPage')).TeachersAnalyticsPage,
}))
const ImportsPage = lazy(async () => ({ default: (await import('@/pages/imports/ImportsPage')).ImportsPage }))
const AiImportDraftPage = lazy(async () => ({
  default: (await import('@/pages/imports/AiImportDraftPage')).AiImportDraftPage,
}))
const ExportsPage = lazy(async () => ({ default: (await import('@/pages/exports/ExportsPage')).ExportsPage }))
const TutorPushesPage = lazy(async () => ({ default: (await import('@/pages/tutor/TutorPushesPage')).TutorPushesPage }))
const TutorAssignmentsPage = lazy(async () => ({
  default: (await import('@/pages/tutor/TutorAssignmentsPage')).TutorAssignmentsPage,
}))
const AuditPage = lazy(async () => ({ default: (await import('@/pages/audit/AuditPage')).AuditPage }))
const SecurityPage = lazy(async () => ({ default: (await import('@/pages/profile/SecurityPage')).SecurityPage }))
const TeacherLessonsPage = lazy(async () => ({ default: (await import('@/pages/teacher/TeacherLessonsPage')).TeacherLessonsPage }))
const TeacherQrSessionPage = lazy(async () => ({ default: (await import('@/pages/teacher/TeacherQrSessionPage')).TeacherQrSessionPage }))
const TeacherAttendancePage = lazy(async () => ({ default: (await import('@/pages/teacher/TeacherAttendancePage')).TeacherAttendancePage }))
const TeacherAbsenceReasonsPage = lazy(async () => ({ default: (await import('@/pages/teacher/TeacherAbsenceReasonsPage')).TeacherAbsenceReasonsPage }))
const TeacherReportsPage = lazy(async () => ({ default: (await import('@/pages/teacher/TeacherReportsPage')).TeacherReportsPage }))
const TeacherBroadcastsPage = lazy(async () => ({ default: (await import('@/pages/teacher/TeacherBroadcastsPage')).TeacherBroadcastsPage }))
const NotFoundPage = lazy(async () => ({ default: (await import('@/pages/NotFoundPage')).NotFoundPage }))

function LazyRoute({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Loader />}>{children}</Suspense>
}

function DefaultRouteRedirect() {
  const { roles } = useAuth()
  return <Navigate to={getDefaultRoute(roles)} replace />
}

export function AppRouter() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <LazyRoute>
            <LoginPage />
          </LazyRoute>
        }
      />

      <Route element={<RequireAuth />}>
        <Route
          path="/password-change"
          element={
            <LazyRoute>
              <PasswordChangePage />
            </LazyRoute>
          }
        />

        <Route element={<RequirePasswordChange />}>
          <Route element={<AdminLayout />}>
            <Route path="/" element={<DefaultRouteRedirect />} />

            <Route
              path="/profile/security"
              element={
                <LazyRoute>
                  <SecurityPage />
                </LazyRoute>
              }
            />

            <Route element={<RequireRoles roles={['admin', 'curator']} />}>
              <Route
                path="/dashboard"
                element={
                  <LazyRoute>
                    <DashboardPage />
                  </LazyRoute>
                }
              />
            </Route>

            <Route element={<RequireRoles roles={['teacher']} />}>
              <Route
                path="/teacher/lessons"
                element={
                  <LazyRoute>
                    <TeacherLessonsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/teacher/qr-sessions/:sessionId"
                element={
                  <LazyRoute>
                    <TeacherQrSessionPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/teacher/lessons/:lessonId/attendance"
                element={
                  <LazyRoute>
                    <TeacherAttendancePage />
                  </LazyRoute>
                }
              />
              <Route
                path="/teacher/absence-reasons"
                element={
                  <LazyRoute>
                    <TeacherAbsenceReasonsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/teacher/reports"
                element={
                  <LazyRoute>
                    <TeacherReportsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/teacher/broadcasts"
                element={
                  <LazyRoute>
                    <TeacherBroadcastsPage />
                  </LazyRoute>
                }
              />
            </Route>

            <Route element={<RequireRoles roles={['admin']} />}>
              <Route
                path="/users"
                element={
                  <LazyRoute>
                    <UsersPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/structure/faculties"
                element={
                  <LazyRoute>
                    <FacultiesPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/structure/streams"
                element={
                  <LazyRoute>
                    <StreamsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/structure/groups"
                element={
                  <LazyRoute>
                    <GroupsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/structure/disciplines"
                element={
                  <LazyRoute>
                    <DisciplinesPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/assignments"
                element={
                  <LazyRoute>
                    <AssignmentsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/tutor/assignments"
                element={
                  <LazyRoute>
                    <TutorAssignmentsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/schedule"
                element={
                  <LazyRoute>
                    <SchedulePage />
                  </LazyRoute>
                }
              />
              <Route
                path="/telegram/invites"
                element={
                  <LazyRoute>
                    <InvitesPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/telegram/binding-requests"
                element={
                  <LazyRoute>
                    <BindingRequestsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/settings"
                element={
                  <LazyRoute>
                    <SettingsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/faq/categories"
                element={
                  <LazyRoute>
                    <FaqCategoriesPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/faq/items"
                element={
                  <LazyRoute>
                    <FaqItemsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/rating/config"
                element={
                  <LazyRoute>
                    <RatingConfigPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/escalations/rules"
                element={
                  <LazyRoute>
                    <EscalationRulesPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/imports"
                element={
                  <LazyRoute>
                    <ImportsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/imports/ai/:draftId"
                element={
                  <LazyRoute>
                    <AiImportDraftPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/audit"
                element={
                  <LazyRoute>
                    <AuditPage />
                  </LazyRoute>
                }
              />
            </Route>

            <Route element={<RequireRoles roles={['admin', 'curator']} />}>
              <Route
                path="/tutor/pushes"
                element={
                  <LazyRoute>
                    <TutorPushesPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/risk"
                element={
                  <LazyRoute>
                    <RiskPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/risk/:studentId"
                element={
                  <LazyRoute>
                    <RiskStudentPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/reports/attendance"
                element={
                  <LazyRoute>
                    <AttendanceReportPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/reports/lates"
                element={
                  <LazyRoute>
                    <LatesReportPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/reports/absences"
                element={
                  <LazyRoute>
                    <AbsencesReportPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/analytics/teachers"
                element={
                  <LazyRoute>
                    <TeachersAnalyticsPage />
                  </LazyRoute>
                }
              />
              <Route
                path="/exports"
                element={
                  <LazyRoute>
                    <ExportsPage />
                  </LazyRoute>
                }
              />
            </Route>

            <Route
              path="*"
              element={
                <LazyRoute>
                  <NotFoundPage />
                </LazyRoute>
              }
            />
          </Route>
        </Route>
      </Route>

      <Route
        path="*"
        element={
          <LazyRoute>
            <NotFoundPage />
          </LazyRoute>
        }
      />
    </Routes>
  )
}
