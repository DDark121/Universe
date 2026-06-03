type StatBarSegment = {
  label: string
  value: number
  tone: 'success' | 'warning' | 'danger' | 'neutral'
}

type StatBarProps = {
  title: string
  totalLabel: string
  totalValue: number
  segments: StatBarSegment[]
}

export function StatBar({ title, totalLabel, totalValue, segments }: StatBarProps) {
  const safeTotal = Math.max(totalValue, 1)

  return (
    <section className="stat-bar">
      <div className="stat-bar-head">
        <div>
          <span className="panel-kicker">Snapshot</span>
          <h3>{title}</h3>
        </div>
        <div className="stat-bar-total">
          <span>{totalLabel}</span>
          <strong>{totalValue}</strong>
        </div>
      </div>
      <div className="stat-bar-track" aria-hidden="true">
        {segments.map((segment) => (
          <span
            key={segment.label}
            className={`stat-bar-segment stat-bar-segment-${segment.tone}`}
            style={{ flexGrow: segment.value === 0 ? 0 : segment.value / safeTotal }}
          />
        ))}
      </div>
      <div className="stat-bar-legend">
        {segments.map((segment) => (
          <div key={segment.label} className="stat-bar-legend-item">
            <span className={`stat-bar-dot stat-bar-dot-${segment.tone}`} />
            <span>{segment.label}</span>
            <strong>{segment.value}</strong>
          </div>
        ))}
      </div>
    </section>
  )
}
