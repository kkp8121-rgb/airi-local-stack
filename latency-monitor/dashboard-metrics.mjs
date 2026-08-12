const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const isFiniteNumber = value => typeof value === 'number' && Number.isFinite(value)

function percentile(values, ratio) {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.max(0, Math.ceil(sorted.length * ratio) - 1)]
}

/**
 * Return the physical acceptance latency for one eligible turn, or null.
 * The substantive playback KPI is the only playback proof used here.
 */
export function acceptanceSample(turn, { vadEndWaitMs = 450 } = {}) {
  if (!isRecord(turn) || !isFiniteNumber(vadEndWaitMs) || vadEndWaitMs < 0) return null
  const { stt, llm, kpi, correlation } = turn
  if (!isRecord(stt) || !isRecord(llm) || !isRecord(kpi) || !isRecord(correlation)) return null
  if (!isRecord(stt.meta) || !isRecord(llm.meta)) return null
  if (stt.meta.synthetic !== undefined && stt.meta.synthetic !== false) return null
  if (llm.meta.cloud_search !== true && llm.meta.cloud_search !== 1) return null
  if (correlation.stt !== 'explicit' || correlation.llm !== 'explicit' ||
      correlation.playback !== 'explicit') return null

  const start = stt.start
  const content = llm.content
  const substantivePlayback = kpi.substantive_playback_start
  if (!isFiniteNumber(start) || !isFiniteNumber(content) || !isFiniteNumber(substantivePlayback)) return null
  if (content < start || substantivePlayback < content) return null
  const sample = substantivePlayback - start + vadEndWaitMs
  return isFiniteNumber(sample) && sample >= 0 ? sample : null
}

export function summarizeAcceptance(turns, {
  vadEndWaitMs = 450,
  targetMs = 2000,
  acceptanceTurns = 5,
} = {}) {
  if (!Array.isArray(turns) || !isFiniteNumber(vadEndWaitMs) || vadEndWaitMs < 0 ||
      !isFiniteNumber(targetMs) || targetMs < 0 ||
      !Number.isInteger(acceptanceTurns) || acceptanceTurns <= 0) {
    return { samples: [], count: 0, worst: null, p50: null, p95: null, passed: null, failed: null }
  }
  const samples = []
  for (const turn of turns) {
    const sample = acceptanceSample(turn, { vadEndWaitMs })
    if (sample !== null) samples.push(sample)
    if (samples.length === acceptanceTurns) break
  }
  const count = samples.length
  const worst = count ? Math.max(...samples) : null
  const complete = count === acceptanceTurns
  const passed = complete ? worst <= targetMs : null
  return {
    samples,
    count,
    worst,
    p50: percentile(samples, .5),
    p95: percentile(samples, .95),
    passed,
    failed: complete ? !passed : null,
  }
}
