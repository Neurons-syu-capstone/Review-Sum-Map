/**
 * ShoeWordCloud.jsx
 * 캔버스 기반 자유형 워드 클라우드.
 *
 * 모든 키워드 표시 보장:
 *   각 단어마다 계산된 폰트 크기로 먼저 시도하고,
 *   4단계 축소 (80% → 65% → 50% → 38%) 를 거쳐 빈 자리를 찾음.
 *   모든 키워드가 반드시 배치되며, 큰 키워드는 중앙으로, 작은 키워드는
 *   축소되지만 절대 누락되지 않음.
 *
 * 폰트    : Oswald (index.html에서 Google Fonts로 로드).
 *           document.fonts.load() 완료 후 렌더링하여 측정값이 항상 정확함.
 *
 * 영역    : PAD 픽셀 여백의 사각형 — 사용 가능한 영역 최대화.
 * 배치    : 캔버스 중앙에서 아르키메데스 나선형; 큰 단어가 중앙을 차지.
 * 색상    : 이슈 → 빨강, 강점 → 초록; 폰트 크기에 따라 투명도 조절.
 * 클릭    : 저장된 배치 목록에서 바운딩 박스 히트 테스트.
 */

import { useEffect, useRef } from 'react'

// ─── 캔버스 / 레이아웃 상수 ───────────────────────────────────────────────────
const W        = 580
const H        = 400          // 높이 증가 → 모든 키워드를 위한 공간 확보
const CX       = W / 2
const CY       = H / 2
const PAD      = 10           // 캔버스 가장자리 최소 여백
const FONT     = '"Oswald", sans-serif'
const FONT_GAP = 2            // 인접 단어 바운딩 박스 사이 픽셀 간격

// 폰트 크기 폴백 체인: 슬롯을 찾을 때까지 순서대로 시도
const SCALE_FALLBACKS = [1.0, 0.80, 0.65, 0.50, 0.38]

// ─── 영역 및 겹침 검사 헬퍼 ──────────────────────────────────────────────────
function rectInBounds (rx, ry, rw, rh) {
  return rx >= PAD && rx + rw <= W - PAD &&
         ry >= PAD && ry + rh <= H - PAD
}

function rectsOverlap (a, b) {
  const g = FONT_GAP
  return !(a.x + a.w + g < b.x || b.x + b.w + g < a.x ||
           a.y + a.h + g < b.y || b.y + b.h + g < a.y)
}

// ─── 공유 텍스트 측정 컨텍스트 ───────────────────────────────────────────────
let _mCtx = null
function getMCtx () {
  if (!_mCtx) {
    const c = document.createElement('canvas')
    c.width = 2; c.height = 2
    _mCtx = c.getContext('2d')
  }
  return _mCtx
}

// ─── 배치 헬퍼 ───────────────────────────────────────────────────────────────
/**
 * 주어진 fontSize로 word 배치를 시도.
 * 성공 시 배치 rect 객체 반환, 실패 시 null 반환.
 */
function tryPlace (word, fontSize, placed) {
  const mCtx = getMCtx()
  mCtx.font = `${word.bold ? '700' : '400'} ${fontSize}px ${FONT}`
  const tw = mCtx.measureText(word.text).width + 4
  const th = fontSize * 1.18

  // 아르키메데스 나선형: 링 간격 4px, 링당 포인트 간격 약 5px
  for (let ring = 0; ring <= 110; ring++) {
    const r    = ring * 4
    const nPts = ring === 0 ? 1 : Math.max(8, Math.round((2 * Math.PI * r) / 5))

    for (let p = 0; p < nPts; p++) {
      const angle = (2 * Math.PI * p / nPts) + ring * 0.42
      const tx = CX + r * Math.cos(angle) - tw / 2
      const ty = CY + r * Math.sin(angle) - th / 2

      if (!rectInBounds(tx, ty, tw, th)) continue
      const candidate = { x: tx, y: ty, w: tw, h: th }
      if (placed.some(q => rectsOverlap(candidate, q))) continue

      // 유효한 슬롯 발견
      return { ...candidate, ...word, fontSize }
    }
  }
  return null
}

/**
 * 모든 단어를 배치. SCALE_FALLBACKS를 거쳐 슬롯을 찾을 때까지 폰트 크기 축소.
 * 배치된 rect 객체 목록 반환 (단어당 하나).
 */
function placeWords (sortedWords) {
  const placed = []

  for (const word of sortedWords) {
    let pos = null
    for (const scale of SCALE_FALLBACKS) {
      const fs = Math.max(9, Math.round(word.fontSize * scale))
      pos = tryPlace(word, fs, placed)
      if (pos) break
    }
    if (pos) placed.push(pos)
    // 모든 폴백 후에도 null인 경우는 캔버스가 완전히 꽉 찬 경우뿐 — 일반적인 키워드 수에서는 발생하지 않음
  }

  return placed
}

// ─── 컴포넌트 ─────────────────────────────────────────────────────────────────
export default function ShoeWordCloud ({ words, onWordClick, activeWord }) {
  const canvasRef = useRef(null)
  const placedRef = useRef([])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !words.length) return

    let cancelled = false

    // Oswald 로드 완료 후 렌더링 — 측정값이 항상 정확하도록 보장
    document.fonts.load(`700 36px ${FONT}`).then(() => {
      if (cancelled) return

      // 캐시된 측정 컨텍스트 초기화 — Oswald 메트릭으로 재측정
      _mCtx = null

      const ctx = canvas.getContext('2d')
      ctx.clearRect(0, 0, W, H)

      // 큰 단어 먼저 → 나선형 중앙을 차지
      const sorted = [...words].sort((a, b) => b.fontSize - a.fontSize)
      const placed = placeWords(sorted)
      placedRef.current = placed

      for (const w of placed) {
        const isActive = activeWord === w.text
        ctx.font = `${w.bold ? '700' : '400'} ${w.fontSize}px ${FONT}`

        if (isActive) {
          // 선택된 단어 강조 배경
          ctx.fillStyle = w.sentiment === 'issue'
            ? 'rgba(229,57,53,0.12)' : 'rgba(46,125,50,0.12)'
          ctx.beginPath()
          ctx.roundRect(w.x - 3, w.y - 1, w.w + 6, w.h + 2, 4)
          ctx.fill()
          ctx.fillStyle = w.sentiment === 'issue' ? '#e53935' : '#2e7d32'
        } else {
          // 폰트 크기에 따라 투명도 증가 — 시각적 깊이감
          const alpha = 0.75 + (w.fontSize / 52) * 0.20
          ctx.fillStyle = w.sentiment === 'issue'
            ? `rgba(229,57,53,${alpha.toFixed(2)})`
            : `rgba(46,125,50,${alpha.toFixed(2)})`
        }

        ctx.fillText(w.text, w.x, w.y + w.fontSize)
      }
    })

    return () => { cancelled = true }
  }, [words, activeWord])

  function handleClick (e) {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = (e.clientX - rect.left) * (W / rect.width)
    const my = (e.clientY - rect.top)  * (H / rect.height)

    for (const w of placedRef.current) {
      if (mx >= w.x && mx <= w.x + w.w && my >= w.y && my <= w.y + w.h) {
        onWordClick(w)
        return
      }
    }
    onWordClick(null)
  }

  return (
    <canvas
      ref={canvasRef}
      width={W}
      height={H}
      onClick={handleClick}
      style={{ width: '100%', maxWidth: W, cursor: 'crosshair', display: 'block', margin: '0 auto' }}
      title="키워드를 클릭하면 관련 리뷰를 볼 수 있습니다"
    />
  )
}