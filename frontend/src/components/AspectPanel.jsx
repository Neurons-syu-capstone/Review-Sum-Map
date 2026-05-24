/**
 * AspectPanel.jsx
 * aspect별 분석 카드
 * 요약 + 키워드 + 대표 리뷰 + 개선 포인트
 */

import { useState } from 'react'
import KeywordPanel from './KeywordPanel.jsx'

const ASPECT_LABELS = {
  comfort: '착용감', size: '사이즈',
  durability: '내구성', design: '디자인', price: '가격',
}
const ASPECT_ICONS = {
  comfort: '🦶', size: '📏',
  durability: '🔩', design: '🎨', price: '💰',
}

function getUrgencyStyle(score) {
  if (score >= 7.5) return { color: 'var(--accent-red)', label: 'CRITICAL' }
  if (score >= 5.0) return { color: 'var(--accent-orange)', label: 'HIGH' }
  return { color: 'var(--accent-yellow)', label: 'MEDIUM' }
}

function ReviewPreview({ review }) {
  return (
    <div style={{
      background: 'var(--bg-base)',
      border: '1px solid var(--border-subtle)',
      borderLeft: `3px solid ${review.sentiment === 'issue'
        ? 'var(--accent-red)' : 'var(--accent-green)'}`,
      borderRadius: 8, padding: '10px 12px', marginBottom: 8,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', marginBottom: 6 }}>
        <div style={{ display: 'flex', gap: 3 }}>
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} style={{
              color: i < review.rating ? 'var(--accent-yellow)' : 'var(--bg-elevated)',
              fontSize: 11,
            }}>★</span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
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
      <p style={{ fontSize: 12, color: 'var(--text-secondary)',
        lineHeight: 1.6, margin: 0 }}>
        {review.text?.slice(0, 200)}{review.text?.length > 200 ? '...' : ''}
      </p>
    </div>
  )
}

export default function AspectPanel({ aspect, aspectData,
  activeKeyword, keywordSentiment, onKeywordClick }) {
  const [expanded, setExpanded] = useState(false)
  if (!aspectData?.issue_summary && !aspectData?.strength_summary &&
    (!aspectData?.urgency_score || aspectData?.urgency_score === 0)) return null
  const urgency = aspectData?.urgency_score || 0
  const us = getUrgencyStyle(urgency)
  const hasFlag = aspectData?.evidence_flag

  const borderColor = urgency >= 7.5
    ? 'rgba(255,45,45,0.4)'
    : urgency >= 5.0
    ? 'rgba(255,140,0,0.3)'
    : 'var(--border-subtle)'

  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: `1px solid ${borderColor}`,
      borderRadius: 12,
      overflow: 'hidden',
    }}>
      {/* 헤더 */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex', alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 18px', cursor: 'pointer',
          background: expanded ? 'rgba(255,255,255,0.02)' : 'transparent',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18 }}>{ASPECT_ICONS[aspect]}</span>
          <span style={{ fontSize: 14, fontWeight: 600,
            color: 'var(--text-primary)' }}>
            {ASPECT_LABELS[aspect]}
          </span>
          {urgency >= 5 && (
            <span style={{
              fontSize: 10, padding: '2px 8px', borderRadius: 10,
              background: `${us.color}22`, color: us.color,
              border: `1px solid ${us.color}44`,
              fontWeight: 700, letterSpacing: 0.5,
            }}>
              {us.label}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: us.color }}>
            {urgency.toFixed(1)}
          </span>
          <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
            {expanded ? '▲' : '▼'}
          </span>
        </div>
      </div>

      {/* 확장 패널 */}
      {expanded && (
        <div style={{ padding: '0 18px 18px',
          borderTop: '1px solid var(--border-subtle)' }}>

          {/* 요약 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr',
            gap: 12, marginTop: 14 }}>
            <div style={{ background: 'rgba(255,85,85,0.05)',
              borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 10, color: 'var(--accent-red)',
                marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                이슈 요약
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)',
                lineHeight: 1.65, margin: 0 }}>
                {aspectData?.issue_summary || '—'}
              </p>
              {hasFlag && (
                <div style={{ marginTop: 6, fontSize: 10,
                  color: 'var(--accent-orange)' }}>
                  ⚠ {hasFlag === 'llm_summary_replaced'
                    ? 'LLM 요약 신뢰도 낮음 (원문 대체)'
                    : '근거 연관성 낮을 수 있음'}
                </div>
              )}
            </div>
            <div style={{ background: 'rgba(78,203,113,0.05)',
              borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 10, color: 'var(--accent-green)',
                marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                강점 요약
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)',
                lineHeight: 1.65, margin: 0 }}>
                {aspectData?.strength_summary || '—'}
              </p>
            </div>
          </div>

          {/* 키워드 */}
          <KeywordPanel
            issueKeywords={aspectData?.issue_keywords}
            strengthKeywords={aspectData?.strength_keywords}
            activeKeyword={activeKeyword}
            onKeywordClick={onKeywordClick}
            aspect={aspect}
          />

          {/* 대표 리뷰 */}
          {aspectData?.issue_summary && aspectData?.issue_summary !== '—' && aspectData?.representative_reviews?.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)',
                marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                대표 리뷰
              </div>
              {aspectData.representative_reviews.slice(0, 2).map((r, i) => (
                <ReviewPreview key={i} review={r} />
              ))}
            </div>
          )}

          {/* 개선 포인트 */}
          {aspectData?.improvement_points?.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 10, color: 'var(--accent-blue)',
                marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                개선 포인트
              </div>
              {aspectData.improvement_points.map((pt, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 5 }}>
                  <span style={{ color: 'var(--accent-blue)', fontSize: 11 }}>→</span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{pt}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
