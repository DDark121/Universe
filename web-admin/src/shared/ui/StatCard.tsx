type StatTone = 'neutral' | 'success' | 'warning' | 'danger' | 'ink'

type StatCardProps = {
  label: string
  value: number | string
  hint?: string
  tone?: StatTone
  eyebrow?: string
}

export function StatCard({ label, value, hint, tone = 'neutral', eyebrow }: StatCardProps) {
  return (
    <article className={`stat-card stat-card-${tone}`}>
      {eyebrow ? <span className="stat-card-eyebrow">{eyebrow}</span> : null}
      <span className="stat-card-label">{label}</span>
      <strong className="stat-card-value">{value}</strong>
      {hint ? <span className="stat-card-hint">{hint}</span> : null}
    </article>
  )
}
