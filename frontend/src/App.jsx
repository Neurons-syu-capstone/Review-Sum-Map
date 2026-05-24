/**
 * App.jsx
 * 최상위 컴포넌트
 * results.json 로딩 + DashboardPage 렌더링
 */

import { useState, useEffect } from 'react'
import { fetchResults } from './api/resultsApi.js'
import DashboardPage from './pages/DashboardPage.jsx'

export default function App() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchResults()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      height: '100vh', gap: 16,
      color: 'var(--text-muted)', fontFamily: 'IBM Plex Mono, monospace',
    }}>
      <div style={{
        width: 32, height: 32, border: '3px solid var(--border-default)',
        borderTop: '3px solid var(--accent-blue)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
      <span style={{ fontSize: 12, letterSpacing: 1 }}>Loading...</span>
    </div>
  )

  if (error) return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      height: '100vh', color: 'var(--accent-red)', fontSize: 13,
      fontFamily: 'IBM Plex Mono, monospace', gap: 10,
    }}>
      <div>⚠ 로딩 실패</div>
      <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>{error}</div>
      <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
        public/results.json 파일을 확인해주세요.
      </div>
    </div>
  )

  return <DashboardPage data={data} />
}
