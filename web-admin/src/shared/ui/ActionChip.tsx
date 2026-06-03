import type { ButtonHTMLAttributes, PropsWithChildren } from 'react'
import clsx from 'clsx'

type Variant = 'primary' | 'secondary' | 'quiet' | 'danger'

type Props = PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>> & {
  variant?: Variant
}

export function ActionChip({ variant = 'secondary', className, type = 'button', children, ...rest }: Props) {
  return (
    <button
      type={type}
      className={clsx(
        'action-chip',
        {
          'action-chip-primary': variant === 'primary',
          'action-chip-secondary': variant === 'secondary',
          'action-chip-quiet': variant === 'quiet',
          'action-chip-danger': variant === 'danger',
        },
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}
