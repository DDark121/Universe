export type BootStatus = 'loading' | 'link_required' | 'pending' | 'rejected' | 'linked' | 'error'

export type LinkedUser = {
  id: string
  username: string
  full_name: string
  email: string | null
  phone_number: string | null
  roles: string[]
  is_active: boolean
  must_change_password: boolean
}

export type LinkedSession = {
  accessToken: string
  refreshToken: string
  user: LinkedUser
}

export type BootstrapResponse = {
  status: BootStatus
  user?: LinkedUser
  tokens?: {
    access_token: string
    refresh_token: string
    token_type: string
    access_expires_at: string
    refresh_expires_at: string
    password_change_required: boolean
  }
  requested_user_id?: string | null
  requested_full_name?: string | null
  telegram_username?: string | null
  group_code?: string | null
  note?: string | null
  resolved_at?: string | null
  message?: string
}

export type StudentProfile = {
  id: string
  username: string
  full_name: string
  email: string | null
  phone_number: string | null
}

export type AttendanceSummary = {
  present: number
  late: number
  absent: number
  excused_absent: number
  unexcused_absent: number
}

export type RatingSnapshot = {
  score: number
  attendance_pct: number
  late_count: number
  unexcused_absence_count: number
  period_start: string
  period_end: string
}

export type WarningItem = {
  id: string
  status: string
  reason: Record<string, unknown> | string | null
  created_at: string
}

export type ScheduleItem = {
  id: string
  group_id: string
  group_code: string
  group_name: string
  discipline_id: string
  discipline_code: string
  discipline_name: string
  teacher_id: string
  teacher_name: string
  starts_at: string
  ends_at: string
  status: string
  room: string | null
  attendance_window_opens_at: string
  attendance_window_closes_at: string
  late_after: string
}

export type HistoryItem = {
  lesson_id: string
  starts_at: string
  discipline_id: string
  discipline_code: string
  discipline_name: string
  group_id: string
  group_code: string
  group_name: string
  teacher_id: string
  teacher_name: string
  room: string | null
  status: string
  source: string
  is_excused: boolean
  correction_reason: string | null
}

export type AbsenceAttachmentItem = {
  id: string
  file_name: string
  content_type: string
  size_bytes: number
  uploaded_at: string
}

export type AbsenceReasonItem = {
  id: string
  lesson_id: string
  lesson_starts_at: string
  group_name: string
  discipline_name: string
  reason_type: string
  comment: string | null
  is_predeclared: boolean
  status: string
  moderation_comment: string | null
  created_at: string
  attachments: AbsenceAttachmentItem[]
}

export type FaqItem = {
  id: string
  category_id: string
  category_name: string
  question: string
  answer: string
  keywords: string
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
