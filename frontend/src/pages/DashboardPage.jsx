/**
 * DashboardPage.jsx
 * 메인 페이지
 * 상품 선택 + 전체 레이아웃
 */

import { useState, useEffect } from 'react'
import DonutChart from '../components/DonutChart.jsx'
import UrgentIssuePanel from '../components/UrgentIssuePanel.jsx'
import AspectPanel from '../components/AspectPanel.jsx'
import ReviewDrawer from '../components/ReviewDrawer.jsx'

const ASPECTS = ['comfort', 'size', 'durability', 'design', 'price']

function StarRating({ rating }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <span style={{ color: 'var(--text-primary)', fontSize: 20,
        fontWeight: 700, marginRight: 4 }}>
        {rating?.toFixed(1)}
      </span>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} style={{
          fontSize: 18,
          color: i < Math.round(rating)
            ? 'var(--accent-yellow)' : 'var(--bg-elevated)',
          filter: i < Math.round(rating)
            ? 'drop-shadow(0 0 4px rgba(245,200,66,0.5))' : 'none',
        }}>★</span>
      ))}
    </div>
  )
}

export default function DashboardPage({ data }) {
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [drawerState, setDrawerState] = useState(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)

  useEffect(() => {
    function handleClick(e) {
      if (!e.target.closest('[data-dropdown]')) setDropdownOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const product = data[selectedIdx]
  if (!product) return (
    <div style={{ padding: 40, color: 'var(--text-muted)' }}>
      데이터가 없습니다.
    </div>
  )

  const {
    average_rating = 0,
    urgent_issues = [],
    aspect_analysis = {},
    validation_status,
  } = product

  const review_count = product.review_count ||
    { total: 0, positive: 0, negative: 0 }

  const sortedAspects = ASPECTS
    .filter(a => aspect_analysis[a])
    .sort((a, b) =>
      (aspect_analysis[b]?.urgency_score || 0) -
      (aspect_analysis[a]?.urgency_score || 0)
    )

  function handleKeywordClick(keyword, sentiment, aspect) {
    if (drawerState?.keyword === keyword && drawerState?.aspect === aspect) {
      setDrawerState(null)
    } else {
      setDrawerState({ aspect, keyword, sentiment })
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg-base)',
      paddingRight: drawerState ? 420 : 0,
      transition: 'padding-right 0.25s ease',
    }}>

      {/* ── 상단 헤더 ── */}
      <header style={{
        background: 'linear-gradient(180deg, #e8eaf0 0%, var(--bg-base) 100%)',
        borderBottom: '1px solid var(--border-subtle)',
        padding: '22px 32px',
        position: 'sticky', top: 0, zIndex: 100,
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start',
          justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
          <div style={{ flex: 1, minWidth: 0, marginRight: 16 }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)',
              letterSpacing: 2, textTransform: 'uppercase', marginBottom: 6 }}>
              리뷰 분석 대시보드
            </div>

            {/* 상품명 표시 */}
            <h1 style={{ fontSize: 20, fontWeight: 700,
              color: 'var(--text-primary)', marginBottom: 8, wordBreak: 'break-word' }}>
              {product.product_name || product.product_id}
            </h1>

            {/* 상품 변경 드롭다운 */}
            {data.length > 1 && (
              <div style={{ position: 'relative', display: 'inline-block', marginBottom: 10 }} data-dropdown>
                <button
                  onClick={() => setDropdownOpen(o => !o)}
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-default)',
                    borderRadius: 6, padding: '4px 28px 4px 10px',
                    color: 'var(--text-secondary)', fontSize: 12,
                    fontFamily: 'inherit', cursor: 'pointer', outline: 'none',
                    position: 'relative', whiteSpace: 'nowrap',
                  }}
                >
                  상품 변경
                  <span style={{
                    position: 'absolute', right: 8, top: '50%',
                    transform: 'translateY(-50%)', fontSize: 10,
                    color: 'var(--text-muted)', pointerEvents: 'none',
                  }}>{dropdownOpen ? '▲' : '▼'}</span>
                </button>

                {dropdownOpen && (
                  <div style={{
                    position: 'absolute', top: 'calc(100% + 4px)', left: 0,
                    minWidth: 360,
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-default)',
                    borderRadius: 8, zIndex: 9999,
                    boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
                    maxHeight: 300, overflowY: 'auto',
                  }}>
                    {data.map((p, i) => (
                      <div
                        key={p.product_id}
                        onClick={() => {
                          setSelectedIdx(i)
                          setDrawerState(null)
                          setDropdownOpen(false)
                        }}
                        style={{
                          padding: '10px 14px', cursor: 'pointer', fontSize: 13,
                          color: 'var(--text-primary)',
                          background: i === selectedIdx ? 'var(--bg-elevated)' : 'transparent',
                          borderBottom: i < data.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-elevated)'}
                        onMouseLeave={e => e.currentTarget.style.background = i === selectedIdx ? 'var(--bg-elevated)' : 'transparent'}
                      >
                        {p.product_name || p.product_id}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <StarRating rating={average_rating} />
              {validation_status && validation_status !== 'ok' && (
                <span style={{ fontSize: 11, color: 'var(--accent-orange)',
                  background: 'rgba(255,140,0,0.1)',
                  borderRadius: 6, padding: '2px 10px' }}>
                  ⚠ {validation_status}
                </span>
              )}
            </div>
          </div>

          <DonutChart
            positive={review_count.positive}
            negative={review_count.negative}
            total={review_count.total}
          />
        </div>
      </header>

      {/* ── 본문 ── */}
      <main style={{ padding: '28px 32px', maxWidth: 1100 }}>

        {/* 긴급 이슈 */}
        <UrgentIssuePanel urgentIssues={urgent_issues} />

        {/* Aspect 분석 */}
        <section>
          <div style={{ fontSize: 10, color: 'var(--text-muted)',
            letterSpacing: 2, textTransform: 'uppercase', marginBottom: 12 }}>
            속성별 리뷰 분석 · 긴급 이슈 순
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {sortedAspects.map(aspect => (
              <AspectPanel
                key={aspect}
                aspect={aspect}
                aspectData={aspect_analysis[aspect]}
                activeKeyword={drawerState?.aspect === aspect
                  ? drawerState.keyword : null}
                keywordSentiment={drawerState?.sentiment}
                onKeywordClick={handleKeywordClick}
              />
            ))}
          </div>
        </section>
      </main>

      {/* 리뷰 드로어 */}
      {drawerState && (
        <ReviewDrawer
          aspect={drawerState.aspect}
          aspectData={aspect_analysis[drawerState.aspect]}
          activeKeyword={drawerState.keyword}
          keywordSentiment={drawerState.sentiment}
          onClose={() => setDrawerState(null)}
        />
      )}
    </div>
  )
}