/**
 * WordCloudSection.jsx
 * 자유형 워드 클라우드 + 키워드 필터 리뷰 패널.
 *
 * 워드 클라우드 : 항상 모든 aspect의 키워드를 합산해서 표시.
 *                키워드 크기는 실제 리뷰 등장 빈도수 기준.
 * 리뷰 패널    : 키워드 클릭 시 api_server.py /search 호출 (전체 리뷰 검색).
 *                API 불가 시 representative_reviews로 폴백.
 */

import { useState, useEffect, useMemo } from 'react'
import ShoeWordCloud from './ShoeWordCloud.jsx'

const API_BASE = 'http://127.0.0.1:8000'

// ─── 상수 ─────────────────────────────────────────────────────────────────────
const ASPECTS = ['comfort', 'size', 'durability', 'design', 'price']
const LABELS  = { comfort: '착용감', size: '사이즈', durability: '내구성', design: '디자인', price: '가격' }
const ICONS   = { comfort: '🦶',    size: '📏',     durability: '🔩',    design: '🎨',    price: '💰'   }

// ─── 워드 헬퍼 ────────────────────────────────────────────────────────────────
/**
 * 모든 aspect 키워드를 수집하고 counts(실제 빈도수)로 fontSize 계산.
 * counts가 없으면 urgency_score 기반으로 폴백.
 */
function buildAllWords (aspect_analysis, counts = {}, loSize = 12, hiSize = 48) {
  const map = {}

  const add = (kw, sentiment, aspect, fallbackScore) => {
    const key = kw.toLowerCase()
    if (!map[key]) map[key] = { text: kw, sentiment, aspect, count: 0, fallback: 0 }
    // 실제 빈도수가 있으면 사용, 없으면 fallbackScore 누적
    map[key].count    = counts[kw] ?? counts[key] ?? 0
    map[key].fallback += fallbackScore
  }

  for (const [aspect, data] of Object.entries(aspect_analysis)) {
    if (!data) continue
    const score = data.urgency_score || 5
    ;(data.issue_keywords    || []).forEach(kw => add(kw, 'issue',    aspect, score))
    ;(data.strength_keywords || []).forEach(kw => add(kw, 'strength', aspect, score * 0.6 + 3))
  }

  const words = Object.values(map)
  if (!words.length) return []

  // 실제 빈도수가 있으면 count 기준, 없으면 fallback 기준
  const hasCounts = words.some(w => w.count > 0)
  const weights   = words.map(w => hasCounts ? w.count : w.fallback)

  const mn  = Math.min(...weights)
  const mx  = Math.max(...weights)
  const rng = mx - mn || 1

  return words.map((w, i) => ({
    ...w,
    fontSize: Math.round(loSize + ((weights[i] - mn) / rng) * (hiSize - loSize)),
    bold: (weights[i] - mn) / rng > 0.55,
  }))
}

// ─── 텍스트 하이라이트 ────────────────────────────────────────────────────────
function highlightText (text, kw) {
  if (!kw || !text) return text

  const STOPWORDS = new Set(['is','the','a','an','in','of','for','to','and','or','on','at','my','me'])
  const words = kw.toLowerCase().split(/\s+/).filter(w => w && !STOPWORDS.has(w))
  if (!words.length) return text

  const pattern = words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
  const re = new RegExp(`(${pattern})`, 'gi')
  const parts = text.split(re)

  return parts.map((part, i) =>
    re.test(part)
      ? <mark key={i} style={{ background: 'rgba(255,215,0,0.45)', borderRadius: 2, padding: '0 1px' }}>{part}</mark>
      : part
  )
}

// ─── 서브 컴포넌트 ────────────────────────────────────────────────────────────
function ReviewCard ({ review, keyword }) {
  const isIssue = review.sentiment === 'issue'
  return (
    <div style={{
      background: 'var(--bg-base)',
      border: '1px solid var(--border-subtle)',
      borderLeft: `3px solid ${isIssue ? 'var(--accent-red)' : 'var(--accent-green)'}`,
      borderRadius: 8, padding: '12px 14px', marginBottom: 10,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, flexWrap: 'wrap', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} style={{ color: i < review.rating ? 'var(--accent-yellow)' : 'var(--bg-elevated)', fontSize: 11 }}>★</span>
          ))}
          {review.verified_purchase && (
            <span style={{ fontSize: 10, color: 'var(--accent-blue)', background: 'rgba(74,158,255,0.1)', borderRadius: 4, padding: '1px 6px', marginLeft: 4 }}>
              ✓ verified
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{review.date?.slice(0, 10)}</span>
          {review.helpful_vote > 0 && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>👍 {review.helpful_vote}</span>
          )}
        </div>
      </div>

      {review.aspect && (
        <span style={{
          display: 'inline-block', fontSize: 10, padding: '1px 8px',
          borderRadius: 10, background: 'var(--bg-elevated)', color: 'var(--text-muted)',
          marginBottom: 8,
        }}>
          {ICONS[review.aspect]} {LABELS[review.aspect] || review.aspect}
        </span>
      )}

      <p style={{ fontSize: 12, lineHeight: 1.7, color: 'var(--text-secondary)', margin: 0 }}>
        {highlightText(review.text, keyword)}
      </p>
    </div>
  )
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────────────
export default function WordCloudSection ({ product }) {
  const [selected,  setSelected ] = useState(null)
  const [reviews,   setReviews  ] = useState([])
  const [loading,   setLoading  ] = useState(false)
  const [apiError,  setApiError ] = useState(false)
  const [counts,    setCounts   ] = useState({})

  // ── 상품 변경 시 실제 키워드 빈도수 fetch ──
  useEffect(() => {
    setCounts({})
    setSelected(null)

    const params = new URLSearchParams({ product_id: product.product_id })
    fetch(`${API_BASE}/keyword-counts?${params}`)
      .then(res => {
        if (!res.ok) throw new Error('API error')
        return res.json()
      })
      .then(data => setCounts(data.counts || {}))
      .catch(() => setCounts({})) // 실패 시 urgency_score 폴백 사용
  }, [product.product_id])

  // 빈도수 기반 워드 목록 (counts 로딩 완료 후 재계산)
  const words = useMemo(
    () => buildAllWords(product.aspect_analysis || {}, counts),
    [product.product_id, counts] // eslint-disable-line react-hooks/exhaustive-deps
  )

  // ── 키워드 클릭 시 전체 리뷰 fetch ──
  useEffect(() => {
    if (!selected) {
      setReviews([])
      return
    }

    setLoading(true)
    setApiError(false)

    const params = new URLSearchParams({
      keyword:    selected.text,
      product_id: product.product_id,
      limit:      30,
    })

    fetch(`${API_BASE}/search?${params}`)
      .then(res => {
        if (!res.ok) throw new Error('API error')
        return res.json()
      })
      .then(data => setReviews(data.reviews || []))
      .catch(() => {
        // 폴백: representative_reviews에서 검색
        setApiError(true)
        const kw   = selected.text.toLowerCase()
        const seen = new Set()
        const out  = []

        for (const [asp, data] of Object.entries(product.aspect_analysis || {})) {
          for (const r of (data?.representative_reviews || [])) {
            const key = r.text?.slice(0, 60)
            if (!seen.has(key) && r.text?.toLowerCase().includes(kw)) {
              seen.add(key)
              out.push({ ...r, aspect: asp })
            }
          }
        }

        setReviews(out.sort((a, b) => new Date(b.date) - new Date(a.date)))
      })
      .finally(() => setLoading(false))

  }, [selected?.text, product.product_id]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleWordClick (word) {
    setSelected(prev => (!word || prev?.text === word.text) ? null : word)
  }

  return (
    <section style={{ marginBottom: 28 }}>
      {/* ── 섹션 헤더 ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase' }}>
          🔍 리뷰 워드 클라우드
        </div>
        <div style={{ fontSize: 10, color: 'var(--border-default)' }}>·</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ color: 'var(--accent-red)',   fontWeight: 700, fontSize: 12 }}>■</span>이슈 키워드
          &nbsp;
          <span style={{ color: 'var(--accent-green)', fontWeight: 700, fontSize: 12 }}>■</span>강점 키워드
        </div>
      </div>

      {/* ── 워드 클라우드 + 리뷰 패널 ── */}
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>

        {/* 워드 클라우드 카드 */}
        <div style={{
          flex: 1, minWidth: 0,
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 12,
          padding: '16px 16px 10px',
        }}>
          <ShoeWordCloud
            key={product.product_id}
            words={words}
            activeWord={selected?.text}
            onWordClick={handleWordClick}
          />
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', marginTop: 8 }}>
            {words.length}개 키워드 · 키워드를 클릭하면 관련 리뷰를 볼 수 있습니다
          </div>
        </div>

        {/* ── 리뷰 패널 ── */}
        {selected && (
          <div style={{
            width: 390, flexShrink: 0,
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-default)',
            borderRadius: 12,
            padding: '18px 18px 14px',
            maxHeight: 500,
            overflowY: 'auto',
            animation: 'wcPanelIn 0.2s ease',
          }}>
            <style>{`
              @keyframes wcPanelIn {
                from { opacity: 0; transform: translateX(12px); }
                to   { opacity: 1; transform: translateX(0);     }
              }
            `}</style>

            {/* 패널 헤더 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 7 }}>
                  전체 리뷰 · 키워드 필터
                </div>
                <span style={{
                  fontSize: 13, fontWeight: 700,
                  padding: '4px 12px', borderRadius: 20,
                  background: selected.sentiment === 'issue'
                    ? 'rgba(229,57,53,0.10)' : 'rgba(46,125,50,0.10)',
                  color: selected.sentiment === 'issue'
                    ? 'var(--accent-red)' : 'var(--accent-green)',
                  border: `1px solid ${selected.sentiment === 'issue'
                    ? 'rgba(229,57,53,0.30)' : 'rgba(46,125,50,0.30)'}`,
                }}>
                  "{selected.text}"
                </span>
              </div>
              <button
                onClick={() => setSelected(null)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1, padding: 4, cursor: 'pointer' }}
                title="닫기"
              >✕</button>
            </div>

            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
              {loading ? '검색 중...' : `${reviews.length}개 리뷰 · 최근순`}
              {apiError && (
                <span style={{ fontSize: 10, color: 'var(--accent-orange)' }}>(대표 리뷰 기준)</span>
              )}
            </div>

            {loading
              ? <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '24px 0' }}>검색 중...</div>
              : reviews.length === 0
              ? <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '24px 0' }}>해당 키워드가 포함된 리뷰가 없습니다.</div>
              : reviews.map((r, i) => <ReviewCard key={i} review={r} keyword={selected.text} />)
            }
          </div>
        )}
      </div>
    </section>
  )
}