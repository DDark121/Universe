import { useId } from 'react'
import clsx from 'clsx'

type Props = {
  accept?: string
  badge?: string
  description: string
  disabled?: boolean
  file: File | null
  label: string
  onFileChange: (file: File | null) => void
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${Math.round(size / 102.4) / 10} KB`
  return `${Math.round(size / 104857.6) / 10} MB`
}

export function FilePickerPanel({
  accept,
  badge = 'Файл',
  description,
  disabled = false,
  file,
  label,
  onFileChange,
}: Props) {
  const inputId = useId()

  return (
    <div>
      <input
        id={inputId}
        aria-label={label}
        className="file-panel-input"
        disabled={disabled}
        type="file"
        accept={accept}
        onChange={(event) => {
          onFileChange(event.target.files?.[0] ?? null)
        }}
      />
      <label
        htmlFor={inputId}
        className={clsx('file-panel', {
          'file-panel-selected': Boolean(file),
          'file-panel-disabled': disabled,
        })}
      >
        <span className="file-panel-eyebrow">{badge}</span>
        <span className="file-panel-title">{file ? file.name : label}</span>
        <span className="file-panel-meta">
          {file ? `${formatFileSize(file.size)} • ${description}` : description}
        </span>
      </label>
    </div>
  )
}
