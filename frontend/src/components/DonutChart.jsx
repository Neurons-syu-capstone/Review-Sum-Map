/**
 * DonutChart.jsx
 * 긍정/부정 리뷰 수 원 그래프
 */

export default function DonutChart({ positive, negative, total }) {
  const r = 38, cx = 50, cy = 50, strokeW = 10
  const circumference = 2 * Math.PI * r
  const posRatio = total > 0 ? positive / total : 0
  const negRatio = total > 0 ? negative / total : 0
  const posDash = posRatio * circumference
  const negDash = negRatio * circumference

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <svg width={100} height={100} viewBox="0 0 100 100">
        {/* 배경 */}
        <circle cx={cx} cy={cy} r={r} fill="none"
          stroke="var(--bg-elevated)" strokeWidth={strokeW} />
        {/* 긍정 */}
        <circle cx={cx} cy={cy} r={r} fill="none"
          stroke="var(--accent-green)" strokeWidth={strokeW}
          strokeDasharray={`${posDash} ${circumference - posDash}`}
          strokeDashoffset={0}
          transform={`rotate(-90 ${cx} ${cy})`} />
        {/* 부정 */}
        <circle cx={cx} cy={cy} r={r} fill="none"
          stroke="var(--accent-red)" strokeWidth={strokeW}
          strokeDasharray={`${negDash} ${circumference - negDash}`}
          strokeDashoffset={-posDash}
          transform={`rotate(-90 ${cx} ${cy})`} />
        <text x={cx} y={cy - 5} textAnchor="middle"
          fill="var(--text-primary)" fontSize={14} fontWeight={700}>{total}</text>
        <text x={cx} y={cy + 10} textAnchor="middle"
          fill="var(--text-muted)" fontSize={8}>reviews</text>
      </svg>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%',
            background: 'var(--accent-green)' }} />
          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
            긍정 <strong style={{ color: 'var(--accent-green)' }}>{positive}</strong>
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%',
            background: 'var(--accent-red)' }} />
          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
            부정 <strong style={{ color: 'var(--accent-red)' }}>{negative}</strong>
          </span>
        </div>
      </div>
    </div>
  )
}
