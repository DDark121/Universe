import type { ButtonHTMLAttributes, PropsWithChildren } from 'react'
import clsx from 'clsx'

type Variant = 'primary' | 'secondary' | 'danger'

type Props = PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement>> & {
  variant?: Variant
}

export function Button({ variant = 'secondary', className, children, ...rest }: Props) {
  return (
    <button
      className={clsx('btn', {
        'btn-primary': variant === 'primary',
        'btn-secondary': variant === 'secondary',
        'btn-danger': variant === 'danger',
      }, className)}
      {...rest}
    >
      {children}
    </button>
  )
}
