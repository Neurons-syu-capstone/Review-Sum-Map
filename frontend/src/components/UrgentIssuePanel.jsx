/**
 * UrgentIssuePanel.jsx
 * 긴급 이슈 카드
 * urgency_score 기반 색상 등급 표시
 */

const ASPECT_LABELS = {
  comfort: '착용감', size: '사이즈',
  durability: '내구성', design: '디자인', price: '가격',
}
const ASPECT_ICONS = {
  comfort: '🦶', size: '📏',
  durability: '🔩', design: '🎨', price: '💰',
}

function getUrgencyStyle(score) {
  if (score >= 7.5) return { bg: '#ff2d2d', text: '#fff', label: 'CRITICAL' }
  if (score >= 5.0) return { bg: '#ff8c00', text: '#fff', label: 'HIGH' }
  return { bg: '#f0c040', text: '#1a1a1a', label: 'MEDIUM' }
}

export default function UrgentIssuePanel({ urgentIssues }) {
  if (!urgentIssues?.length) return null

  return (
    <section style={{ marginBottom: 28 }}>
      <div style={{ fontSize: 10, color: 'var(--accent-red)',
        letterSpacing: 2, textTransform: 'uppercase', marginBottom: 12 }}>
        ⚡ 긴급 이슈
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {urgentIssues.map((issue, i) => {
          const s = getUrgencyStyle(issue.urgency_score)
          return (
            <div key={i} style={{
              background: 'rgba(255,45,45,0.04)',
              border: '1px solid rgba(255,45,45,0.2)',
              borderLeft: `4px solid ${s.bg}`,
              borderRadius: 10,
              padding: '14px 18px',
              display: 'flex', gap: 16, alignItems: 'flex-start',
            }}>
              {/* 점수 뱃지 */}
              <div style={{
                background: s.bg, color: s.text,
                borderRadius: 8, padding: '6px 12px',
                textAlign: 'center', minWidth: 64, flexShrink: 0,
              }}>
                <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1 }}>
                  {issue.urgency_score?.toFixed(1)}
                </div>
                <div style={{ fontSize: 9, letterSpacing: 0.5, marginTop: 2 }}>
                  {s.label}
                </div>
              </div>

              {/* 내용 */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center',
                  gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 14 }}>{ASPECT_ICONS[issue.aspect]}</span>
                  <span style={{ fontSize: 13, fontWeight: 600,
                    color: 'var(--text-primary)' }}>
                    {ASPECT_LABELS[issue.aspect] || issue.aspect}
                  </span>
                </div>
                <p style={{ fontSize: 12, color: 'var(--text-secondary)',
                  lineHeight: 1.65, margin: 0 }}>
                  {issue.summary}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
