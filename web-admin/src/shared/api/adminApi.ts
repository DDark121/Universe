import { api } from '@/shared/api/http'
import type { paths } from '@/shared/api/openapi.generated'
import type {
  AIImportDraftDetail,
  AIImportDraftItem,
  AIImportMode,
  AIImportPayload,
  AIImportWizard,
  AssignmentItem,
  BindingRequestItem,
  DisciplineItem,
  AttendanceReportSummary,
  AdminAssistantMessage,
  AdminAssistantReply,
  ExportJobItem,
  FacultyItem,
  GroupItem,
  ImportJobItem,
  InviteCodeItem,
  LateReportItem,
  LessonItem,
  Paged,
  RiskListItem,
  RiskStudentDetail,
  StudentAnalyticsSummary,
  StreamItem,
  TeacherAnalyticsItem,
  UserItem,
} from '@/shared/api/types'

type QueryParams<Path extends keyof paths> =
  paths[Path] extends { get: { parameters: { query?: infer Query } } } ? Query : never
type JsonPostBody<Path extends keyof paths> =
  paths[Path] extends { post: { requestBody: { content: { 'application/json': infer Body } } } } ? Body : never
type JsonPatchBody<Path extends keyof paths> =
  paths[Path] extends { patch: { requestBody: { content: { 'application/json': infer Body } } } } ? Body : never

type AdminUsersQuery = NonNullable<QueryParams<'/api/v1/admin/users'>>
type AdminUserCreatePayload = {
  username: string
  email?: string | null
  phone_number: string
  full_name: string
  roles: string[]
}
type AdminUserUpdatePayload = {
  email?: string | null
  phone_number?: string | null
  full_name?: string | null
  is_active?: boolean | null
  is_archived?: boolean | null
}
type AdminUserRolesUpdatePayload = JsonPatchBody<'/api/v1/admin/users/{user_id}/roles'>
type AdminGroupCreatePayload = JsonPostBody<'/api/v1/admin/groups'>
type AdminGroupUpdatePayload = JsonPatchBody<'/api/v1/admin/groups/{group_id}'>

type CreateUserResult = {
  id: string
  username: string
  phone_number: string | null
  temp_password: string
  roles: string[]
}

const DEFAULT_PAGE = 1
const MAX_PAGE_SIZE = 500
const COMPACT_PAGE_SIZE = 200

function unwrapPaged<T>(payload: Paged<T> | T[]): T[] {
  return Array.isArray(payload) ? payload : payload.items
}

function buildPagedParams<T extends Record<string, unknown>>(params?: T, pageSize = MAX_PAGE_SIZE) {
  return {
    page: DEFAULT_PAGE,
    page_size: pageSize,
    ...(params ?? {}),
  }
}

export const adminApi = {
  async listRoles() {
    const { data } = await api.get<Array<{ id: string; code: string; name: string }>>('/admin/roles')
    return data
  },

  async listUsers(params?: AdminUsersQuery) {
    const { data } = await api.get<Paged<UserItem> | UserItem[]>('/admin/users', {
      params: buildPagedParams(params),
    })
    return unwrapPaged(data)
  },

  async createUser(payload: AdminUserCreatePayload) {
    const { data } = await api.post<CreateUserResult>('/admin/users', payload)
    return data
  },

  async updateUser(id: string, payload: AdminUserUpdatePayload) {
    const { data } = await api.patch(`/admin/users/${id}`, payload)
    return data
  },

  async updateUserRoles(id: string, roles: AdminUserRolesUpdatePayload['roles']) {
    const { data } = await api.patch(`/admin/users/${id}/roles`, { roles })
    return data
  },

  async listFaculties() {
    const { data } = await api.get<Paged<FacultyItem> | FacultyItem[]>('/admin/faculties', {
      params: buildPagedParams(),
    })
    return unwrapPaged(data)
  },

  async createFaculty(payload: { code: string; name: string }) {
    const { data } = await api.post('/admin/faculties', payload)
    return data
  },

  async updateFaculty(id: string, payload: { code?: string; name?: string }) {
    const { data } = await api.patch(`/admin/faculties/${id}`, payload)
    return data
  },

  async listStreams(facultyId?: string) {
    const { data } = await api.get<Paged<StreamItem> | StreamItem[]>('/admin/streams', {
      params: buildPagedParams(facultyId ? { faculty_id: facultyId } : undefined),
    })
    return unwrapPaged(data)
  },

  async createStream(payload: { faculty_id: string; name: string }) {
    const { data } = await api.post('/admin/streams', payload)
    return data
  },

  async updateStream(id: string, payload: { faculty_id?: string; name?: string }) {
    const { data } = await api.patch(`/admin/streams/${id}`, payload)
    return data
  },

  async listGroups() {
    const { data } = await api.get<Paged<GroupItem> | GroupItem[]>('/admin/groups', {
      params: buildPagedParams(),
    })
    return unwrapPaged(data)
  },

  async createGroup(payload: AdminGroupCreatePayload) {
    const { data } = await api.post('/admin/groups', payload)
    return data
  },

  async updateGroup(id: string, payload: AdminGroupUpdatePayload) {
    const { data } = await api.patch(`/admin/groups/${id}`, payload)
    return data
  },

  async listDisciplines() {
    const { data } = await api.get<Paged<DisciplineItem> | DisciplineItem[]>('/admin/disciplines', {
      params: buildPagedParams(),
    })
    return unwrapPaged(data)
  },

  async createDiscipline(payload: {
    code: string
    name: string
    window_start_offset_override_minutes?: number | null
    window_duration_override_minutes?: number | null
    late_threshold_override_minutes?: number | null
  }) {
    const { data } = await api.post('/admin/disciplines', payload)
    return data
  },

  async updateDiscipline(
    id: string,
    payload: {
      code?: string
      name?: string
      is_archived?: boolean
      window_start_offset_override_minutes?: number | null
      window_duration_override_minutes?: number | null
      late_threshold_override_minutes?: number | null
    },
  ) {
    const { data } = await api.patch(`/admin/disciplines/${id}`, payload)
    return data
  },

  async listAssignments() {
    const { data } = await api.get<Paged<AssignmentItem> | AssignmentItem[]>('/admin/assignments', {
      params: buildPagedParams(),
    })
    return unwrapPaged(data)
  },

  async createAssignment(payload: { teacher_id: string; discipline_id: string; group_id: string }) {
    const { data } = await api.post('/admin/assignments', payload)
    return data
  },

  async updateAssignment(id: string, payload: Record<string, unknown>) {
    const { data } = await api.patch(`/admin/assignments/${id}`, payload)
    return data
  },

  async archiveAssignment(id: string) {
    const { data } = await api.delete(`/admin/assignments/${id}`)
    return data
  },

  async listLessons(params?: { date_from?: string; date_to?: string }) {
    const { data } = await api.get<Paged<LessonItem> | LessonItem[]>('/admin/lessons', {
      params: buildPagedParams(params),
    })
    return unwrapPaged(data)
  },

  async createLesson(payload: Record<string, unknown>) {
    const { data } = await api.post('/admin/lessons', payload)
    return data
  },

  async updateLesson(id: string, payload: Record<string, unknown>) {
    const { data } = await api.patch(`/admin/lessons/${id}`, payload)
    return data
  },

  async updateLessonStatus(id: string, payload: Record<string, unknown>) {
    const { data } = await api.patch(`/admin/lessons/${id}/status`, payload)
    return data
  },

  async importLessons(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await api.post('/admin/lessons/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  async createInvite(payload: Record<string, unknown>) {
    const { data } = await api.post<InviteCodeItem>('/admin/invite-codes', payload)
    return data
  },

  async listInviteCodes() {
    const { data } = await api.get<Paged<InviteCodeItem> | InviteCodeItem[]>('/admin/invite-codes', {
      params: buildPagedParams(),
    })
    return unwrapPaged(data)
  },

  async listBindingRequests() {
    const { data } = await api.get<Paged<BindingRequestItem> | BindingRequestItem[]>('/admin/binding-requests', {
      params: buildPagedParams(undefined, COMPACT_PAGE_SIZE),
    })
    return unwrapPaged(data)
  },

  async decideBinding(payload: { request_id: string; user_id: string; approve: boolean }) {
    const { data } = await api.post('/admin/binding-requests/decision', payload)
    return data
  },

  async getSetting(key: string) {
    const { data } = await api.get<{ key: string; value: Record<string, unknown> }>(`/admin/settings/${key}`)
    return data
  },

  async setSetting(key: string, value: Record<string, unknown>) {
    const { data } = await api.put(`/admin/settings/${key}`, { value })
    return data
  },

  async listFaqCategories(includeInactive = true) {
    const { data } = await api.get<
      Paged<{ id: string; name: string; sort_order: number; is_active: boolean }> | Array<{ id: string; name: string; sort_order: number; is_active: boolean }>
    >(
      '/admin/faq/categories',
      {
        params: {
          ...buildPagedParams(),
          ...(includeInactive ? { include_inactive: 'true' } : {}),
        },
      },
    )
    return unwrapPaged(data)
  },

  async getFaqStatus() {
    const { data } = await api.get<{
      status: string
      assistant_enabled: boolean
      vector_runtime_available: boolean
      source_dir: string
      source_hash: string
      index_hash: string | null
      file_count: number
      item_count: number
      chunk_count: number
      built_at: string | null
      model_name: string
    }>('/admin/faq/status')
    return data
  },

  async createFaqCategory(payload: { name: string; sort_order: number }) {
    const { data } = await api.post('/admin/faq/categories', payload)
    return data
  },

  async updateFaqCategory(
    id: string,
    payload: { name?: string; sort_order?: number; is_active?: boolean },
  ) {
    const { data } = await api.patch(`/admin/faq/categories/${id}`, payload)
    return data
  },

  async listFaqItems(query?: string, includeInactive = true) {
    const params: Record<string, string> = {}
    if (query) params.query = query
    if (includeInactive) params.include_inactive = 'true'
    params.page = String(DEFAULT_PAGE)
    params.page_size = String(MAX_PAGE_SIZE)
    const { data } = await api.get('/admin/faq/items', { params })
    return unwrapPaged(
      data as
        | Paged<{
            id: string
            category_id: string
            question: string
            answer: string
            keywords: string
            is_active: boolean
          }>
        | Array<{
            id: string
            category_id: string
            question: string
            answer: string
            keywords: string
            is_active: boolean
          }>,
    ) as Array<{
      id: string
      category_id: string
      question: string
      answer: string
      keywords: string
      is_active: boolean
    }>
  },

  async createFaqItem(payload: { category_id: string; question: string; answer: string; keywords?: string }) {
    const { data } = await api.post('/admin/faq/items', payload)
    return data
  },

  async updateFaqItem(
    id: string,
    payload: {
      category_id?: string
      question?: string
      answer?: string
      keywords?: string
      is_active?: boolean
    },
  ) {
    const { data } = await api.patch(`/admin/faq/items/${id}`, payload)
    return data
  },

  async getRatingConfig() {
    const { data } = await api.get('/admin/rating/config')
    return data as {
      attendance_weight: number
      late_weight: number
      unexcused_absence_weight: number
      activity_weight: number
      updated_at: string
    } | null
  },

  async updateRatingConfig(payload: Record<string, number>) {
    const { data } = await api.put('/admin/rating/config', payload)
    return data
  },

  async listEscalationRules() {
    const { data } = await api.get('/admin/escalation-rules', {
      params: buildPagedParams(),
    })
    return unwrapPaged(
      data as
        | Paged<{
            id: string
            name: string
            threshold_unexcused_absences: number
            threshold_lates: number
            min_rating: number
            is_active: boolean
          }>
        | Array<{
            id: string
            name: string
            threshold_unexcused_absences: number
            threshold_lates: number
            min_rating: number
            is_active: boolean
          }>,
    ) as Array<{
      id: string
      name: string
      threshold_unexcused_absences: number
      threshold_lates: number
      min_rating: number
      is_active: boolean
    }>
  },

  async createEscalationRule(payload: Record<string, unknown>) {
    const { data } = await api.post('/admin/escalation-rules', payload)
    return data
  },

  async updateEscalationRule(id: string, payload: Record<string, unknown>) {
    const { data } = await api.patch(`/admin/escalation-rules/${id}`, payload)
    return data
  },

  async listRiskStudents(params?: Record<string, string>) {
    const { data } = await api.get<Paged<RiskListItem> | RiskListItem[]>('/admin/risk/students', {
      params: buildPagedParams(params),
    })
    return unwrapPaged(data)
  },

  async getRiskStudent(id: string) {
    const { data } = await api.get<RiskStudentDetail>(`/admin/risk/students/${id}`)
    return data
  },

  async warnRiskStudent(id: string) {
    const { data } = await api.post(`/admin/risk/${id}/warn`)
    return data
  },

  async getAttendanceReport(params: Record<string, string>) {
    const { data } = await api.get<AttendanceReportSummary>('/admin/reports/attendance', { params })
    return data
  },

  async getLatesReport(params: Record<string, string>) {
    const { data } = await api.get<Paged<LateReportItem> | LateReportItem[]>('/admin/reports/lates', {
      params: buildPagedParams(params),
    })
    return unwrapPaged(data)
  },

  async getAbsencesReport(params: Record<string, string>) {
    const { data } = await api.get('/admin/reports/absences', {
      params: buildPagedParams(params),
    })
    return unwrapPaged(data as Paged<Record<string, unknown>> | Record<string, unknown>[])
  },

  async getTeacherAnalytics(params: Record<string, string>) {
    const { data } = await api.get<TeacherAnalyticsItem[]>('/admin/analytics/teachers', { params })
    return data
  },

  async compareTeacherAnalytics(params: Record<string, string | string[]>) {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        for (const item of value) {
          query.append(key, item)
        }
      } else {
        query.set(key, value)
      }
    }
    const { data } = await api.get<TeacherAnalyticsItem[]>('/admin/analytics/teachers/compare', {
      params: query,
    })
    return data
  },

  async getStudentAnalytics(params: Record<string, string>) {
    const { data } = await api.get<StudentAnalyticsSummary>('/admin/analytics/students', { params })
    return data
  },

  async transferStudent(payload: { student_id: string; target_group_id: string; transfer_date: string }) {
    const { data } = await api.post('/admin/student-transfer', payload)
    return data
  },

  async uploadImport(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await api.post('/admin/imports/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data as { file_name: string; file_path: string }
  },

  async createImportJob(payload: { job_type: string; file_name: string; file_path: string }) {
    const { data } = await api.post('/admin/imports', payload)
    return data
  },

  async listImports() {
    const { data } = await api.get<Paged<ImportJobItem> | ImportJobItem[]>('/admin/imports', {
      params: buildPagedParams(),
    })
    return unwrapPaged(data)
  },

  async getImport(id: string) {
    const { data } = await api.get<ImportJobItem>(`/admin/imports/${id}`)
    return data
  },

  async createExport(payload: { job_type: string; format: string; filters?: Record<string, unknown> }) {
    const { data } = await api.post('/admin/exports', payload)
    return data
  },

  async listExports() {
    const { data } = await api.get<Paged<ExportJobItem> | ExportJobItem[]>('/admin/exports', {
      params: buildPagedParams(),
    })
    return unwrapPaged(data)
  },

  async getExport(id: string) {
    const { data } = await api.get<ExportJobItem>(`/admin/exports/${id}`)
    return data
  },

  async downloadExport(id: string) {
    const { data } = await api.get<Blob>(`/admin/exports/${id}/download`, {
      responseType: 'blob',
      headers: {
        Accept: 'application/octet-stream',
      },
    })
    return data
  },

  async downloadImportErrors(id: string) {
    const { data } = await api.get<Blob>(`/admin/imports/${id}/errors/download`, {
      responseType: 'blob',
      headers: {
        Accept: 'text/csv',
      },
    })
    return data
  },

  async createAIImportDraft(payload: {
    file: File
    mode: AIImportMode
    wizard: AIImportWizard
  }) {
    const formData = new FormData()
    formData.append('file', payload.file)
    formData.append('mode', payload.mode)
    if (payload.wizard.term_start) formData.append('term_start', payload.wizard.term_start)
    if (payload.wizard.term_end) formData.append('term_end', payload.wizard.term_end)
    if (payload.wizard.first_week_parity) formData.append('first_week_parity', payload.wizard.first_week_parity)
    const { data } = await api.post<AIImportDraftDetail>('/admin/ai-imports', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  async listAIImports() {
    const { data } = await api.get<Paged<AIImportDraftItem> | AIImportDraftItem[]>('/admin/ai-imports', {
      params: buildPagedParams(),
    })
    return unwrapPaged(data)
  },

  async getAIImport(id: string) {
    const { data } = await api.get<AIImportDraftDetail>(`/admin/ai-imports/${id}`)
    return data
  },

  async updateAIImport(id: string, payload: { wizard: AIImportWizard; payload: AIImportPayload }) {
    const { data } = await api.patch<AIImportDraftDetail>(`/admin/ai-imports/${id}`, payload)
    return data
  },

  async applyAIImport(id: string) {
    const { data } = await api.post(`/admin/ai-imports/${id}/apply`)
    return data
  },

  async rejectAIImport(id: string) {
    const { data } = await api.post(`/admin/ai-imports/${id}/reject`)
    return data
  },

  async listTutorGroups() {
    const { data } = await api.get<Array<{ id: string; code: string; name: string }>>('/admin/tutor/groups')
    return data
  },

  async createTutorBroadcast(payload: { group_id: string; message: string }) {
    const { data } = await api.post('/admin/tutor/broadcasts', payload)
    return data
  },

  async askAssistant(payload: {
    message: string
    current_path?: string | null
    history?: AdminAssistantMessage[]
  }) {
    const { data } = await api.post<AdminAssistantReply>('/admin/assistant/reply', payload)
    return data
  },

  async listTutorAssignments() {
    const { data } = await api.get('/admin/tutor-assignments', {
      params: buildPagedParams(),
    })
    return unwrapPaged(
      data as
        | Paged<{
            id: string
            tutor_user_id: string
            group_id: string
            is_active: boolean
            created_at: string
          }>
        | Array<{
            id: string
            tutor_user_id: string
            group_id: string
            is_active: boolean
            created_at: string
          }>,
    )
  },

  async createTutorAssignment(payload: { tutor_user_id: string; group_id: string }) {
    const { data } = await api.post('/admin/tutor-assignments', payload)
    return data
  },

  async updateTutorAssignment(id: string, payload: { is_active?: boolean }) {
    const { data } = await api.patch(`/admin/tutor-assignments/${id}`, payload)
    return data
  },

  async deleteTutorAssignment(id: string) {
    const { data } = await api.delete(`/admin/tutor-assignments/${id}`)
    return data
  },

  async listAudit(params: Record<string, string>) {
    const { data } = await api.get('/admin/audit/logs', { params })
    return data as {
      items: Array<{
        id: string
        actor_user_id: string | null
        action: string
        entity_type: string
        entity_id: string | null
        details: Record<string, unknown> | null
        created_at: string
      }>
      meta: {
        page: number
        page_size: number
        total: number
      }
    }
  },
}
