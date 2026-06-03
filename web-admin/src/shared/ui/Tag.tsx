import type { PropsWithChildren } from 'react'

type Variant = 'default' | 'success' | 'warning' | 'danger'

export function Tag({ children, variant = 'default' }: PropsWithChildren<{ variant?: Variant }>) {
  const style =
    variant === 'success'
      ? { borderColor: 'rgba(79, 103, 52, 0.45)', background: 'rgba(79, 103, 52, 0.16)' }
      : variant === 'warning'
        ? { borderColor: 'rgba(163, 127, 43, 0.55)', background: 'rgba(163, 127, 43, 0.16)' }
        : variant === 'danger'
          ? { borderColor: 'rgba(140, 63, 57, 0.55)', background: 'rgba(140, 63, 57, 0.16)' }
          : undefined
  return (
    <span className="tag" style={style}>
      {children}
    </span>
  )
}
