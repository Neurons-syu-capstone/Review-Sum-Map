/**
 * KeywordPanel.jsx
 * 부정/긍정 키워드 버튼
 * 클릭 시 ReviewDrawer 트리거
 */

function KeywordChip({ keyword, sentiment, isActive, onClick }) {
  const color = sentiment === 'issue' ? 'var(--accent-red)' : 'var(--accent-green)'
  const activeBg = sentiment === 'issue'
    ? 'rgba(255,85,85,0.2)' : 'rgba(78,203,113,0.2)'

  return (
    <button
      onClick={onClick}
      style={{
        background: isActive ? activeBg : 'rgba(255,255,255,0.04)',
        border: `1px solid ${isActive ? color : 'var(--border-default)'}`,
        borderRadius: 20,
        padding: '5px 12px',
        display: 'inline-flex', alignItems: 'center', gap: 6,
      }}
    >
      <span style={{ fontSize: 12, color: isActive ? color : 'var(--text-secondary)' }}>
        {keyword}
      </span>
    </button>
  )
}

export default function KeywordPanel({ issueKeywords, strengthKeywords,
  activeKeyword, onKeywordClick, aspect }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 14 }}>
      {/* 부정 키워드 */}
      <div>
        <div style={{ fontSize: 10, color: 'var(--accent-red)',
          marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          부정 키워드
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {(issueKeywords || []).map(kw => (
            <KeywordChip
              key={kw}
              keyword={kw}
              sentiment="issue"
              isActive={activeKeyword === kw}
              onClick={() => onKeywordClick(kw, 'issue', aspect)}
            />
          ))}
        </div>
      </div>

      {/* 긍정 키워드 */}
      <div>
        <div style={{ fontSize: 10, color: 'var(--accent-green)',
          marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          긍정 키워드
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {(strengthKeywords || []).map(kw => (
            <KeywordChip
              key={kw}
              keyword={kw}
              frequency={kw.frequency}
              sentiment="strength"
              isActive={activeKeyword === kw}
              onClick={() => onKeywordClick(kw, 'strength', aspect)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
