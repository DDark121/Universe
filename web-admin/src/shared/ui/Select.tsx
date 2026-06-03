import type { SelectHTMLAttributes } from 'react'
import clsx from 'clsx'

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={clsx('select', className)} {...props} />
}
