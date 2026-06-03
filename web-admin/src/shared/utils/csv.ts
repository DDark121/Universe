export function downloadCsv(filename: string, rows: Array<Record<string, unknown>>) {
  if (!rows.length) return
  const headers = Object.keys(rows[0])
  const escaped = rows.map((row) =>
    headers
      .map((header) => {
        const value = row[header]
        const text = value === null || value === undefined ? '' : String(value)
        return `"${text.replaceAll('"', '""')}"`
      })
      .join(','),
  )
  const csv = [headers.join(','), ...escaped].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
