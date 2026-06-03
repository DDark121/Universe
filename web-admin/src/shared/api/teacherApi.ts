import { api, apiBaseUrl } from '@/shared/api/http'
import type {
  ApiMessage,
  TeacherAbsenceReasonItem,
  TeacherAttendanceSummary,
  TeacherDynamicQrSessionResponse,
  TeacherGroupItem,
  TeacherLessonAttendanceResponse,
  TeacherLessonItem,
  TeacherQrGenerateResponse,
} from '@/shared/api/types'

export const teacherApi = {
  async listLessons(params?: { date_from?: string; date_to?: string }) {
    const { data } = await api.get<TeacherLessonItem[]>('/teacher/lessons', { params })
    return data
  },

  async listGroups() {
    const { data } = await api.get<TeacherGroupItem[]>('/teacher/groups')
    return data
  },

  async generateQr(lessonId: string) {
    const { data } = await api.post<TeacherQrGenerateResponse>('/teacher/qr/generate', {
      lesson_id: lessonId,
    })
    return data
  },

  async startDynamicQrSession(lessonId: string) {
    const { data } = await api.post<TeacherDynamicQrSessionResponse>('/teacher/qr/sessions/start', {
      lesson_id: lessonId,
    })
    return data
  },

  async stopDynamicQrSession(sessionId: string) {
    const { data } = await api.post(`/teacher/qr/sessions/${sessionId}/stop`)
    return data as { session_id: string; is_active: boolean; stopped_at: string | null }
  },

  async getLessonAttendance(lessonId: string) {
    const { data } = await api.get<TeacherLessonAttendanceResponse>(`/teacher/lessons/${lessonId}/attendance`)
    return data
  },

  async correctAttendance(payload: {
    lesson_id: string
    student_id: string
    status: 'present' | 'late' | 'absent'
    reason: string
  }) {
    const { data } = await api.post('/teacher/attendance/correct', payload)
    return data
  },

  async listAbsenceReasons() {
    const { data } = await api.get<TeacherAbsenceReasonItem[]>('/teacher/absence-reasons')
    return data
  },

  async moderateAbsenceReason(payload: {
    reason_id: string
    status: 'accepted' | 'rejected'
    comment?: string
  }) {
    const { data } = await api.post('/teacher/absence-reasons/moderate', payload)
    return data
  },

  async downloadAbsenceAttachment(attachmentId: string) {
    const { data } = await api.get<Blob>(`/teacher/absence-reasons/attachments/${attachmentId}`, {
      responseType: 'blob',
    })
    return data
  },

  async getAttendanceReport(params: { date_from: string; date_to: string; group_id?: string }) {
    const { data } = await api.get<TeacherAttendanceSummary>('/teacher/reports/attendance', { params })
    return data
  },

  async createBroadcast(payload: { group_id: string; message: string }) {
    const { data } = await api.post<ApiMessage & { broadcast_id?: string; recipients?: number }>(
      '/teacher/broadcasts',
      null,
      {
        params: payload,
      },
    )
    return data
  },
}

export function buildTeacherWsUrl(pathname: string, token: string) {
  const apiUrl = new URL(apiBaseUrl, window.location.origin)
  const protocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${apiUrl.host}${pathname}?token=${encodeURIComponent(token)}`
}
