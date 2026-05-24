/**
 * ReviewDrawer.jsx
 * 키워드 클릭 시 슬라이드 패널
 * 최근순 정렬 + 형광펜 하이라이트
 */

const ASPECT_LABELS = {
  comfort: '착용감', size: '사이즈',
  durability: '내구성', design: '디자인', price: '가격',
}
const ASPECT_ICONS = {
  comfort: '🦶', size: '📏',
  durability: '🔩', design: '🎨', price: '💰',
}

function highlightText(text, keyword, sentiment) {
  if (!keyword || !text) return text
  const color = sentiment === 'issue' ? 'var(--accent-red)' : 'var(--accent-green)'
  const bg = sentiment === 'issue'
    ? 'rgba(255,85,85,0.18)' : 'rgba(78,203,113,0.18)'
  const regex = new RegExp(
    `(${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'
  )
  const parts = text.split(regex)
  return parts.map((part, i) =>
    regex.test(part)
      ? <mark key={i} style={{ background: bg, color, borderRadius: 3,
          padding: '0 2px', fontWeight: 600 }}>{part}</mark>
      : part
  )
}

function ReviewCard({ review, activeKeyword, keywordSentiment }) {
  return (
    <div style={{
      background: 'var(--bg-base)',
      border: '1px solid var(--border-subtle)',
      borderLeft: `3px solid ${review.sentiment === 'issue'
        ? 'var(--accent-red)' : 'var(--accent-green)'}`,
      borderRadius: 8,
      padding: '12px 14px',
      marginBottom: 10,
    }}>
      {/* 메타 */}
      <div style={{ display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} style={{
              color: i < review.rating ? 'var(--accent-yellow)' : 'var(--bg-elevated)',
              fontSize: 12,
            }}>★</span>
          ))}
          {review.verified_purchase && (
            <span style={{ fontSize: 10, color: 'var(--accent-blue)',
              background: 'rgba(74,158,255,0.1)', borderRadius: 4,
              padding: '1px 6px' }}>✓ verified</span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
            {review.date?.slice(0, 10)}
          </span>
          {review.helpful_vote > 0 && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
              👍 {review.helpful_vote}
            </span>
          )}
        </div>
      </div>

      {/* 본문 */}
      <p style={{ fontSize: 12, lineHeight: 1.65,
        color: 'var(--text-secondary)', margin: 0 }}>
        {activeKeyword
          ? highlightText(review.text, activeKeyword, keywordSentiment)
          : review.text}
      </p>
    </div>
  )
}

export default function ReviewDrawer({ aspect, aspectData, activeKeyword,
  keywordSentiment, onClose }) {

  const reviews = (aspectData?.representative_reviews || [])
    .filter(r => activeKeyword
      ? r.text?.toLowerCase().includes(activeKeyword.toLowerCase())
      : true)
    .sort((a, b) => new Date(b.date) - new Date(a.date))

  return (
    <div style={{
      position: 'fixed', top: 0, right: 0,
      width: 420, height: '100vh',
      background: 'var(--bg-surface)',
      borderLeft: '1px solid var(--border-default)',
      zIndex: 1000, overflowY: 'auto', padding: 24,
      animation: 'slideIn 0.25s ease',
    }}>
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%) }
          to   { transform: translateX(0) }
        }
      `}</style>

      {/* 헤더 */}
      <div style={{ display: 'flex', justifyContent: 'space-between',
        alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <div style={{ color: 'var(--text-muted)', fontSize: 11,
            marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>
            {ASPECT_ICONS[aspect]} {ASPECT_LABELS[aspect]}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--text-primary)', fontSize: 15,
              fontWeight: 600 }}>리뷰 조회</span>
            {activeKeyword && (
              <span style={{
                fontSize: 12, padding: '2px 10px', borderRadius: 20,
                background: keywordSentiment === 'issue'
                  ? 'rgba(255,85,85,0.15)' : 'rgba(78,203,113,0.15)',
                color: keywordSentiment === 'issue'
                  ? 'var(--accent-red)' : 'var(--accent-green)',
                border: `1px solid ${keywordSentiment === 'issue'
                  ? 'rgba(255,85,85,0.3)' : 'rgba(78,203,113,0.3)'}`,
              }}>
                "{activeKeyword}"
              </span>
            )}
          </div>
        </div>
        <button onClick={onClose} style={{
          background: 'none', border: 'none',
          color: 'var(--text-muted)', fontSize: 20, padding: 4, lineHeight: 1,
        }}>✕</button>
      </div>

      <div style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 14 }}>
        {reviews.length}개 리뷰 · 최근순
      </div>

      {reviews.length === 0
        ? <div style={{ color: 'var(--text-muted)', fontSize: 13,
            textAlign: 'center', marginTop: 40 }}>
            해당 키워드가 포함된 리뷰가 없습니다.
          </div>
        : reviews.map((r, i) => (
          <ReviewCard key={i} review={r}
            activeKeyword={activeKeyword}
            keywordSentiment={keywordSentiment} />
        ))
      }
    </div>
  )
}
