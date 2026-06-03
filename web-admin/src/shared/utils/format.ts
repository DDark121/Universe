import dayjs from 'dayjs'

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  return dayjs(value).format('DD.MM.YYYY HH:mm')
}

export function formatDate(value: string | null | undefined) {
  if (!value) return '-'
  return dayjs(value).format('DD.MM.YYYY')
}

export function humanizeStatus(value: string | null | undefined) {
  if (!value) return '-'
  return value
    .replaceAll('_', ' ')
    .replace(/^./, (s) => s.toUpperCase())
}
