import assert from 'node:assert/strict'
import test from 'node:test'
import { acceptanceSample, summarizeAcceptance } from './dashboard-metrics.mjs'

function turn({
  id = 'turn', start = 100, content = 150, substantive = 210,
  playback = 110, synthetic = false, cloudSearch = 1,
  sttCorrelation = 'explicit', llmCorrelation = 'explicit', playbackCorrelation = 'explicit',
} = {}) {
  return {
    turn_id: id,
    stt: { start, meta: { synthetic } },
    llm: { content, meta: { cloud_search: cloudSearch } },
    kpi: { substantive_playback_start: substantive },
    playback: { start: playback },
    correlation: { stt: sttCorrelation, llm: llmCorrelation, playback: playbackCorrelation },
  }
}

test('excludes synthetic and heuristic or mixed STT/LLM turns', () => {
  assert.equal(acceptanceSample(turn({ synthetic: true })), null)
  assert.equal(acceptanceSample(turn({ sttCorrelation: 'heuristic' })), null)
  assert.equal(acceptanceSample(turn({ llmCorrelation: 'mixed' })), null)
  assert.equal(acceptanceSample(turn({ playbackCorrelation: 'mixed' })), null)
})

test('uses explicit substantive playback instead of raw ACK playback', () => {
  assert.equal(acceptanceSample(turn({ playback: 110, substantive: 210 })), 560)
})

test('uses substantive playback after an ACK before LLM content', () => {
  const sample = turn({ playback: 110, content: 150, substantive: 220 })
  sample.kpi.ack_playback_start = 110
  assert.equal(acceptanceSample(sample), 570)
})

test('excludes missing, invalid, and chronologically invalid KPI values', () => {
  assert.equal(acceptanceSample({}), null)
  const missing = turn()
  delete missing.kpi.substantive_playback_start
  assert.equal(acceptanceSample(missing), null)
  assert.equal(acceptanceSample(turn({ substantive: Number.NaN })), null)
  assert.equal(acceptanceSample(turn({ substantive: Infinity })), null)
  assert.equal(acceptanceSample(turn({ substantive: true })), null)
  assert.equal(acceptanceSample(turn({ start: 200, content: 150, substantive: 210 })), null)
  assert.equal(acceptanceSample(turn({ substantive: 149 })), null)
  assert.equal(acceptanceSample(turn({ substantive: 99 })), null)
  assert.equal(acceptanceSample(turn(), { vadEndWaitMs: -1 }), null)
  assert.equal(acceptanceSample(turn({ start: -Number.MAX_VALUE, substantive: Number.MAX_VALUE, content: 0 })), null)
})

test('keeps newest five eligible turns and reports percentiles and final status', () => {
  const turns = [
    turn({ id: 'newest', substantive: 300 }),
    turn({ id: 'second', substantive: 250 }),
    turn({ id: 'ignored', synthetic: true, substantive: 9999 }),
    turn({ id: 'third', substantive: 200 }),
    turn({ id: 'fourth', substantive: 400 }),
    turn({ id: 'fifth', substantive: 350 }),
    turn({ id: 'oldest', substantive: 1000 }),
  ]
  const summary = summarizeAcceptance(turns, { targetMs: 800 })
  assert.deepEqual(summary.samples, [650, 600, 550, 750, 700])
  assert.equal(summary.count, 5)
  assert.equal(summary.worst, 750)
  assert.equal(summary.p50, 650)
  assert.equal(summary.p95, 750)
  assert.equal(summary.passed, true)
  assert.equal(summary.failed, false)

  const failed = summarizeAcceptance(turns, { targetMs: 700 })
  assert.equal(failed.passed, false)
  assert.equal(failed.failed, true)
  const incomplete = summarizeAcceptance(turns.slice(0, 4))
  assert.equal(incomplete.passed, null)
  assert.equal(incomplete.failed, null)
  const invalid = summarizeAcceptance(turns, { targetMs: -1 })
  assert.deepEqual(invalid, {
    samples: [], count: 0, worst: null, p50: null, p95: null, passed: null, failed: null,
  })
})
