/**
 * resultsApi.js
 * results.json 로딩 함수
 * public/results.json 을 fetch해서 반환
 */

export async function fetchResults() {
  const res = await fetch('/results.json')
  if (!res.ok) throw new Error('results.json 로딩 실패')
  const json = await res.json()
  // 단일 객체면 배열로 감싸기
  return Array.isArray(json) ? json : [json]
}
