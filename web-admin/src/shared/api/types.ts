export type RoleCode = 'student' | 'teacher' | 'admin' | 'curator'

export type AuthSession = {
  accessToken: string
  refreshToken: string
  accessExpiresAt: string
  mustChangePassword: boolean
  user: {
    id: string
    username: string
    full_name: string
    email: string | null
    phone_number: string | null
    roles: RoleCode[]
    is_active: boolean
    must_change_password: boolean
  } | null
}

export type ApiMessage = { message: string }

export type PaginationMeta = {
  page: number
  page_size: number
  total: number
}

export type Paged<T> = {
  items: T[]
  meta: PaginationMeta
}

export type SelectOption = {
  value: string
  label: string
}

export type UserItem = {
  id: string
  username: string
  full_name: string
  email: string | null
  phone_number: string | null
  is_active: boolean
  is_archived: boolean
  roles: RoleCode[]
}

export type FacultyItem = {
  id: string
  code: string
  name: string
  is_archived?: boolean
}

export type StreamItem = {
  id: string
  faculty_id: string
  name: string
  is_archived?: boolean
}

export type GroupItem = {
  id: string
  code: string
  name: string
  is_archived?: boolean
  faculty_id?: string | null
  stream_id?: string | null
  is_subgroup?: boolean
  parent_group_id?: string | null
  window_start_offset_override_minutes?: number | null
  window_duration_override_minutes?: number | null
  late_threshold_override_minutes?: number | null
  telegram_chat_id?: number | null
  telegram_chat_title?: string | null
  telegram_chat_is_active?: boolean
}

export type DisciplineItem = {
  id: string
  code: string
  name: string
  is_archived?: boolean
  window_start_offset_override_minutes?: number | null
  window_duration_override_minutes?: number | null
  late_threshold_override_minutes?: number | null
}

export type AssignmentItem = {
  id: string
  teacher_id: string
  discipline_id: string
  group_id: string
  is_active: boolean
}

export type LessonItem = {
  id: string
  group_id: string
  discipline_id: string
  teacher_id: string
  starts_at: string
  ends_at: string
  status: string
}

export type InviteCodeItem = {
  id?: string
  code: string
  role_code?: RoleCode
  expires_at: string
  max_activations: number
  activation_count?: number
  is_active?: boolean
  created_at?: string
  group_id?: string | null
  discipline_id?: string | null
}

export type BindingRequestItem = {
  id: string
  telegram_id: number
  telegram_username?: string | null
  full_name?: string | null
  group_code?: string | null
  note?: string | null
  status: string
  requested_user_id: string | null
  created_at: string
  resolved_at?: string | null
}

export type RiskListItem = {
  student_id: string
  student_name: string
  score: number
  late_count: number
  unexcused_absence_count: number
  reasons: Record<string, unknown>
}

export type ImportJobItem = {
  id: string
  job_type: string
  status: string
  file_name: string
  file_path?: string
  created_at: string
  updated_at?: string
  completed_at: string | null
  processed_rows: number
  total_rows: number
  error_report: Record<string, unknown> | null
}

export type AIImportMode = 'mixed' | 'users' | 'schedule'
export type AIImportStatus = 'queued' | 'processing' | 'draft' | 'applied' | 'failed' | 'rejected'
export type AIImportMappingAction = 'match_existing' | 'create_new' | 'unresolved'

export type AIImportWizard = {
  term_start?: string | null
  term_end?: string | null
  first_week_parity?: 'odd' | 'even' | null
}

export type AIImportIssue = {
  severity: 'error' | 'warning' | 'info'
  code: string
  message: string
  source_ref?: string | null
  field_path?: string | null
  requires_action?: boolean
}

export type AIImportMappedRow = {
  draft_id: string
  action: AIImportMappingAction
  existing_id?: string | null
  confidence?: number | null
  source_ref?: string | null
}

export type AIImportFacultyRow = AIImportMappedRow & {
  code?: string | null
  name?: string | null
}

export type AIImportStreamRow = AIImportMappedRow & {
  name?: string | null
  faculty_code?: string | null
}

export type AIImportGroupRow = AIImportMappedRow & {
  code?: string | null
  name?: string | null
  faculty_code?: string | null
  stream_name?: string | null
  parent_group_code?: string | null
  is_subgroup?: boolean
}

export type AIImportDisciplineRow = AIImportMappedRow & {
  code?: string | null
  name?: string | null
}

export type AIImportUserRow = AIImportMappedRow & {
  username?: string | null
  full_name?: string | null
  email?: string | null
  roles: RoleCode[]
  group_code?: string | null
}

export type AIImportMembershipRow = {
  draft_id: string
  student_username?: string | null
  student_full_name?: string | null
  group_code?: string | null
  start_date?: string | null
  source_ref?: string | null
}

export type AIImportAssignmentRow = {
  draft_id: string
  teacher_username?: string | null
  teacher_full_name?: string | null
  discipline_code?: string | null
  discipline_name?: string | null
  group_code?: string | null
  source_ref?: string | null
}

export type AIImportSchedulePatternRow = {
  draft_id: string
  group_code?: string | null
  discipline_code?: string | null
  discipline_name?: string | null
  teacher_username?: string | null
  teacher_name?: string | null
  date?: string | null
  day_of_week?: string | null
  start_time?: string | null
  end_time?: string | null
  week_parity: 'all' | 'odd' | 'even'
  room?: string | null
  note?: string | null
  source_ref?: string | null
}

export type AIImportLessonRow = {
  draft_id: string
  pattern_draft_id?: string | null
  group_code?: string | null
  discipline_code?: string | null
  discipline_name?: string | null
  teacher_username?: string | null
  teacher_name?: string | null
  starts_at: string
  ends_at: string
  room?: string | null
  status: string
  source_ref?: string | null
}

export type AIImportPayload = {
  detected_doc_kind: AIImportMode
  notes: string[]
  entities: {
    faculties: AIImportFacultyRow[]
    streams: AIImportStreamRow[]
    groups: AIImportGroupRow[]
    disciplines: AIImportDisciplineRow[]
    users: AIImportUserRow[]
    memberships: AIImportMembershipRow[]
    assignments: AIImportAssignmentRow[]
  }
  schedule_patterns: AIImportSchedulePatternRow[]
  lessons: AIImportLessonRow[]
}

export type AIImportDraftItem = {
  id: string
  status: AIImportStatus
  mode: AIImportMode
  file_name: string
  created_at: string
  updated_at?: string
  completed_at: string | null
  summary?: {
    detected_doc_kind?: AIImportMode
    confidence?: number
    counts?: Record<string, number>
    source_metadata?: Record<string, unknown> | null
    excerpt?: string | null
  } | null
  error_report?: Record<string, unknown> | null
}

export type AIImportDraftDetail = AIImportDraftItem & {
  wizard: AIImportWizard
  payload: AIImportPayload | null
  issues: AIImportIssue[]
  apply_result?: Record<string, unknown> | null
}

export type ExportJobItem = {
  id: string
  job_type: string
  format: string
  status: string
  filters: Record<string, unknown> | null
  file_path: string | null
  created_at: string
  updated_at?: string
  completed_at: string | null
}

export type TeacherAnalyticsItem = {
  teacher_id: string
  attendance_pct: number
  total_marks: number
  lates?: number
  absences?: number
}

export type TeacherGroupItem = {
  id: string
  code: string
  name: string
}

export type TeacherLessonItem = {
  id: string
  group_id: string
  group_code: string
  group_name: string
  discipline_id: string
  discipline_code: string
  discipline_name: string
  starts_at: string
  ends_at: string
  status: string
  room: string | null
}

export type TeacherQrGenerateResponse = {
  token: string
  deeplink: string
  expires_at: string
}

export type TeacherDynamicQrSessionResponse = {
  session_id: string
  ws_url: string
  session_expires_at: string
}

export type TeacherQrSlotEvent = {
  event: 'qr_slot'
  session_id: string
  lesson_id: string
  slot_index: number
  qr_token: string
  deeplink: string
  expires_at: string
}

export type TeacherQrSessionClosedEvent = {
  event: 'session_closed'
  session_id: string
}

export type TeacherLessonAttendanceResponse = {
  lesson: TeacherLessonItem
  students: Array<{
    student_id: string
    username: string
    full_name: string
    attendance_id: string | null
    status: 'present' | 'late' | 'absent' | null
    source: string | null
    marked_at: string | null
    is_excused: boolean
    correction_reason: string | null
  }>
}

export type TeacherAbsenceReasonItem = {
  id: string
  lesson_id: string
  lesson_starts_at: string
  group_name: string
  student_id: string
  student_name: string
  reason_type: string
  comment: string | null
  is_predeclared: boolean
  status: 'pending' | 'accepted' | 'rejected'
  moderation_comment: string | null
  created_at: string
  attachments: Array<{
    id: string
    file_name: string
    content_type: string
    size_bytes: number
    uploaded_at: string
  }>
}

export type TeacherAttendanceSummary = {
  present: number
  late: number
  absent: number
  excused_absent: number
  unexcused_absent: number
}

export type AttendanceReportSummary = TeacherAttendanceSummary

export type LateReportItem = {
  attendance_id: string
  lesson_id: string
  student_id: string
  student_name: string
  marked_at: string
  starts_at: string
  group_id: string
  discipline_id: string
  teacher_id: string
}

export type RiskStudentDetail = {
  student: {
    id: string
    full_name: string
    username: string
    email: string | null
  }
  risk_card: {
    score: number
    late_count: number
    unexcused_absence_count: number
    reasons: Record<string, unknown>
  } | null
  ratings: Array<{
    period_start: string
    period_end: string
    score: number
    attendance_pct: number
    late_count: number
    unexcused_absence_count: number
    calculated_at: string
  }>
  forecasts?: Array<{
    horizon_days: number
    period_days: number
    predicted_score: number
    predicted_late_count: number
    predicted_unexcused_absence_count: number
    confidence: number
    calculated_for_date: string
    explain: Record<string, unknown>
  }>
  absence_reasons: Array<{
    reason_id: string
    lesson_id: string
    lesson_starts_at: string
    reason_type: string
    comment: string | null
    is_predeclared: boolean
    moderation_status: string
    moderation_comment: string | null
    moderated_at: string | null
  }>
  escalations: Array<{
    id: string
    status: string
    reason_payload: Record<string, unknown>
    created_at: string
    resolved_at: string | null
  }>
}
