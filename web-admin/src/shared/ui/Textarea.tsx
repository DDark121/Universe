import type { TextareaHTMLAttributes } from 'react'
import clsx from 'clsx'

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={clsx('textarea', className)} {...props} />
}
