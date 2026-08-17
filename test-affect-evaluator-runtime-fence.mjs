import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const REPOSITORY_ROOT = path.dirname(fileURLToPath(import.meta.url))

export const FORBIDDEN_TOKENS = Object.freeze([
  'must_act_realization',
  'must_act_realization_v1.json',
  'run_guarded_delta_eval',
  'correction_target_realization',
  'correction_target_realization_v1.json',
  'run_correction_realization_postcondition_eval',
  'correction_prepublication_policy',
  'correction_prepublication_policy_v1.json',
  'run_correction_prepublication_eval',
  'correction_target',
  'correction_target_v1.json',
  'run_correction_target_ab_eval',
  'run_affect_broadcast_eval'
])

const SOURCE_EXTENSIONS = new Set([
  '.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.vue', '.ps1',
  '.json', '.yaml', '.yml', '.toml', '.cmd', '.bat'
])
const EXCLUDED_DIRECTORY_NAMES = new Set([
  '.git', '.github', '.codex', '.codex-remote-attachments', 'airi_docs', 'external',
  'asar-inspect', 'tts-samples', 'chatterbox', 'faster-qwen3-tts',
  'qwen3-tts-openai-fastapi', 'node_modules', '.venv', 'venv', '__pycache__',
  'eval', 'training', 'testdata', 'bench-results', 'benchmarks', 'models',
  'debug-recordings', 'local-results', 'local-operator-keys', 'private-replays',
  'reports', 'test', 'tests', '__tests__', 'docs'
])
const CORRECTION_TARGET_IMPORT_PATTERNS = Object.freeze([
  /\b(?:from|import)\s+\.*(?:[a-z0-9_]+\.)*correction_target(?=$|[\s,;])/u,
  /\bfrom\s+\.*(?:[a-z0-9_]+\.)*[a-z0-9_]+\s+import\s+(?:\([^)]*)?correction_target(?=$|[\s,;)])/u,
  /\b(?:importlib\.import_module|__import__)\(\s*['"]\.*(?:[a-z0-9_]+\.)*correction_target['"]/u,
  /['"](?:correction_target|[^'"\r\n]*[./\\]correction_target)(?:\.[a-z0-9_-]+)?['"]/u
])
const COMPACT_CORRECTION_TARGET_IMPORT_PATTERNS = Object.freeze([
  /(?:^|[^a-z0-9_])(?:from|import|import-module|import_module|__import__|require)\(?(?:\.*(?:[a-z0-9_]+\.)*|(?:\.\.?\/|\/)(?:[a-z0-9_-]+\/)*)correction_target(?=$|[^a-z0-9_])/u,
  /(?:^|[^a-z0-9_])from\.*(?:[a-z0-9_]+\.)*[a-z0-9_]+import\(?correction_target(?=$|[^a-z0-9_])/u
])

function compareCodePoints(left, right) {
  const leftPoints = Array.from(left)
  const rightPoints = Array.from(right)
  const length = Math.min(leftPoints.length, rightPoints.length)
  for (let index = 0; index < length; index += 1) {
    if (leftPoints[index] !== rightPoints[index]) {
      return leftPoints[index] < rightPoints[index] ? -1 : 1
    }
  }
  return leftPoints.length - rightPoints.length
}

function isTestFile(fileName) {
  return /^(?:test|spec)[-_]/iu.test(fileName) || /\.(?:test|spec)\.[^.]+$/iu.test(fileName)
}

function isSourceFile(fileName) {
  return SOURCE_EXTENSIONS.has(path.extname(fileName).toLowerCase())
}

function relativePath(root, filePath) {
  return path.relative(root, filePath).split(path.sep).join('/')
}

function failForLink(root, entryPath) {
  throw new Error(`Runtime fence rejects symbolic link or reparse point: ${relativePath(root, entryPath)}`)
}

function assertValidRoot(root) {
  if (typeof root !== 'string' || root.length === 0) {
    throw new Error('Runtime fence root must be an existing non-link directory.')
  }
  let rootStat
  try {
    rootStat = fs.lstatSync(root)
  } catch {
    throw new Error('Runtime fence root must be an existing non-link directory.')
  }
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) {
    throw new Error('Runtime fence root must be an existing non-link directory.')
  }
}

function listEntries(root, directory) {
  try {
    return fs.readdirSync(directory, { withFileTypes: true }).sort((left, right) => compareCodePoints(left.name, right.name))
  } catch {
    throw new Error(`Runtime fence cannot list directory: ${relativePath(root, directory) || '.'}`)
  }
}

function collectRecursiveSourceFiles(root, directory, files) {
  for (const entry of listEntries(root, directory)) {
    const entryPath = path.join(directory, entry.name)
    const excluded = EXCLUDED_DIRECTORY_NAMES.has(entry.name.toLowerCase()) || isTestFile(entry.name)
    if (excluded) continue
    let entryStat
    try {
      entryStat = fs.lstatSync(entryPath)
    } catch {
      throw new Error(`Runtime fence cannot inspect path: ${relativePath(root, entryPath)}`)
    }
    if (entry.isSymbolicLink() || entryStat.isSymbolicLink()) failForLink(root, entryPath)
    if (entryStat.isDirectory()) {
      collectRecursiveSourceFiles(root, entryPath, files)
    } else if (entryStat.isFile() && isSourceFile(entry.name)) {
      files.push(entryPath)
    }
  }
}

function collectPatchFiles(root, files) {
  const airiDocsDirectory = path.join(root, 'airi_docs')
  let airiDocsStat
  try {
    airiDocsStat = fs.lstatSync(airiDocsDirectory)
  } catch (error) {
    if (error?.code === 'ENOENT') return
    throw new Error('Runtime fence cannot inspect path: airi_docs')
  }
  if (airiDocsStat.isSymbolicLink()) failForLink(root, airiDocsDirectory)
  if (!airiDocsStat.isDirectory()) throw new Error('Runtime fence docs path must be a directory: airi_docs')
  const patchesDirectory = path.join(root, 'airi_docs', 'patches')
  let patchesStat
  try {
    patchesStat = fs.lstatSync(patchesDirectory)
  } catch (error) {
    if (error?.code === 'ENOENT') return
    throw new Error('Runtime fence cannot inspect path: airi_docs/patches')
  }
  if (patchesStat.isSymbolicLink()) failForLink(root, patchesDirectory)
  if (!patchesStat.isDirectory()) throw new Error('Runtime fence patches path must be a directory: airi_docs/patches')
  for (const entry of listEntries(root, patchesDirectory)) {
    const entryPath = path.join(patchesDirectory, entry.name)
    if (path.extname(entry.name).toLowerCase() !== '.patch') continue
    let entryStat
    try {
      entryStat = fs.lstatSync(entryPath)
    } catch {
      throw new Error(`Runtime fence cannot inspect path: ${relativePath(root, entryPath)}`)
    }
    if (entry.isSymbolicLink() || entryStat.isSymbolicLink()) failForLink(root, entryPath)
    if (entryStat.isFile()) files.push(entryPath)
  }
}

export function collectRuntimeFenceFiles(root) {
  assertValidRoot(root)
  const files = []
  collectRecursiveSourceFiles(root, root, files)
  collectPatchFiles(root, files)
  return files.sort((left, right) => compareCodePoints(relativePath(root, left), relativePath(root, right)))
}

function compactLiteralSource(source) {
  // This deliberately catches only simple quoted literal concatenation. It is a
  // static fence, not a proof against arbitrary hostile runtime obfuscation.
  return source.replace(/[\s'"`+]/gu, '')
}

function pythonModuleSpecHasCorrectionTarget(specification) {
  const moduleName = specification.trim().split(/\s+as\s+/u, 1)[0]
  return moduleName.split('.').includes('correction_target')
}

function hasPythonCorrectionTargetImport(lowerSource) {
  const logicalSource = lowerSource.replace(/\\\r?\n/gu, '')
  for (const sourceLine of logicalSource.split(/\r?\n/gu)) {
    const line = sourceLine.replace(/#.*$/u, '').trim()
    const directImport = /^import\s+(.+)$/u.exec(line)
    if (directImport && directImport[1].split(',').some(pythonModuleSpecHasCorrectionTarget)) {
      return true
    }
    const fromImport = /^from\s+([^\s]+)\s+import\s+(.+)$/u.exec(line)
    if (!fromImport) continue
    if (pythonModuleSpecHasCorrectionTarget(fromImport[1])) return true
    const importedNames = fromImport[2].replace(/[()]/gu, '')
    if (importedNames.split(',').some(pythonModuleSpecHasCorrectionTarget)) return true
  }
  return false
}

function hasCorrectionTargetReference(lowerSource, compactSource) {
  return hasPythonCorrectionTargetImport(lowerSource) ||
    CORRECTION_TARGET_IMPORT_PATTERNS.some((pattern) => pattern.test(lowerSource)) ||
    COMPACT_CORRECTION_TARGET_IMPORT_PATTERNS.some((pattern) => pattern.test(compactSource))
}

function matchingTokens(source) {
  const lowerSource = source.toLowerCase()
  const compactSource = compactLiteralSource(lowerSource)
  return FORBIDDEN_TOKENS.filter((token) => {
    if (token === 'correction_target') {
      return hasCorrectionTargetReference(lowerSource, compactSource)
    }
    return lowerSource.includes(token) || compactSource.includes(token)
  })
}

export function scanAffectEvaluatorRuntimeFence(root) {
  return collectRuntimeFenceFiles(root).flatMap((filePath) => {
    let source
    try {
      source = fs.readFileSync(filePath, 'utf8')
    } catch {
      throw new Error(`Runtime fence cannot read source: ${relativePath(root, filePath)}`)
    }
    return matchingTokens(source).map((token) => ({ path: relativePath(root, filePath), token }))
  }).sort((left, right) => compareCodePoints(left.path, right.path) || compareCodePoints(left.token, right.token))
}

function withFixture(build, run) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'airi-runtime-fence-'))
  try {
    build(root)
    return run(root)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
}

function writeFixture(root, fileName, source) {
  const filePath = path.join(root, fileName)
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  fs.writeFileSync(filePath, source)
}

test('detects direct and indirect evaluator helper imports', () => {
  withFixture((root) => {
    writeFixture(root, 'ollama-proxy/app.py', 'import must_act_realization')
    writeFixture(root, 'chat-ingress/runtime.mjs', "import './run_guarded_delta_eval.mjs'")
  }, (root) => assert.deepEqual(scanAffectEvaluatorRuntimeFence(root), [
    { path: 'chat-ingress/runtime.mjs', token: 'run_guarded_delta_eval' },
    { path: 'ollama-proxy/app.py', token: 'must_act_realization' }
  ]))
})

test('detects A4.6 prepublication evaluator imports and launcher references', () => {
  withFixture((root) => {
    writeFixture(root, 'ollama-proxy/runtime/worker.py', 'import correction_prepublication_policy')
    writeFixture(root, 'ollama-proxy/runtime/config.json', '{"policy":"correction_prepublication_policy_v1.json"}')
    writeFixture(root, 'broadcast-director/core.mjs', "import './run_correction_prepublication_eval.mjs'")
    writeFixture(root, 'start-a46.cmd', 'run_correction_prepublication_eval')
    writeFixture(root, 'start-airi-local-stack.ps1', 'correction_prepublication_policy_v1.json')
  }, (root) => assert.deepEqual(scanAffectEvaluatorRuntimeFence(root), [
    { path: 'broadcast-director/core.mjs', token: 'run_correction_prepublication_eval' },
    { path: 'ollama-proxy/runtime/config.json', token: 'correction_prepublication_policy' },
    { path: 'ollama-proxy/runtime/config.json', token: 'correction_prepublication_policy_v1.json' },
    { path: 'ollama-proxy/runtime/worker.py', token: 'correction_prepublication_policy' },
    { path: 'start-a46.cmd', token: 'run_correction_prepublication_eval' },
    { path: 'start-airi-local-stack.ps1', token: 'correction_prepublication_policy' },
    { path: 'start-airi-local-stack.ps1', token: 'correction_prepublication_policy_v1.json' }
  ]))
})

test('detects A4.3/A4.4 correction target modules without matching the broadcast seam', () => {
  withFixture((root) => {
    writeFixture(root, 'ollama-proxy/app.py', 'import correction_target')
    writeFixture(root, 'chat-ingress/runtime.mjs', "import './correction_target_v1.json'")
    writeFixture(root, 'broadcast-director/core.mjs', 'run_correction_target_ab_eval run_affect_broadcast_eval')
    writeFixture(root, 'ollama-proxy/broadcast_correction_target.py', 'broadcast_correction_target')
    writeFixture(root, 'stt/loader.py', "Path('correction_target.py')")
    writeFixture(root, 'stt/relative.py', 'from .correction_target import validate')
    writeFixture(root, 'stt/importlib_relative.py', "importlib.import_module('.correction_target')")
    writeFixture(root, 'stt/qualified.py', 'import eval.affect_broadcast.correction_target')
    writeFixture(root, 'stt/multiple.py', 'import os, eval.affect_broadcast.correction_target as target')
    writeFixture(root, 'stt/from_member.py', 'from eval.affect_broadcast import correction_target as target')
  }, (root) => assert.deepEqual(scanAffectEvaluatorRuntimeFence(root), [
    { path: 'broadcast-director/core.mjs', token: 'run_affect_broadcast_eval' },
    { path: 'broadcast-director/core.mjs', token: 'run_correction_target_ab_eval' },
    { path: 'chat-ingress/runtime.mjs', token: 'correction_target_v1.json' },
    { path: 'ollama-proxy/app.py', token: 'correction_target' },
    { path: 'stt/from_member.py', token: 'correction_target' },
    { path: 'stt/importlib_relative.py', token: 'correction_target' },
    { path: 'stt/loader.py', token: 'correction_target' },
    { path: 'stt/multiple.py', token: 'correction_target' },
    { path: 'stt/qualified.py', token: 'correction_target' },
    { path: 'stt/relative.py', token: 'correction_target' }
  ]))
})

test('detects split Python, JavaScript, and PowerShell literal references', () => {
  withFixture((root) => {
    writeFixture(root, 'ollama-proxy/app.py', "importlib.import_module('must_' + 'act_realization')")
    writeFixture(root, 'chat-ingress/runtime.mjs', "import('run_' + 'guarded_delta_eval.mjs')")
    writeFixture(root, 'start-airi-local-stack.ps1', "Import-Module ('correction_' + 'target')")
  }, (root) => assert.deepEqual(scanAffectEvaluatorRuntimeFence(root), [
    { path: 'chat-ingress/runtime.mjs', token: 'run_guarded_delta_eval' },
    { path: 'ollama-proxy/app.py', token: 'must_act_realization' },
    { path: 'start-airi-local-stack.ps1', token: 'correction_target' }
  ]))
})

test('detects root launcher and patch references', () => {
  withFixture((root) => {
    writeFixture(root, 'start-airi-local-stack.ps1', 'run_correction_realization_postcondition_eval')
    writeFixture(root, 'airi_docs/patches/runtime.patch', 'correction_target_realization_v1.json')
  }, (root) => assert.deepEqual(scanAffectEvaluatorRuntimeFence(root), [
    { path: 'airi_docs/patches/runtime.patch', token: 'correction_target_realization' },
    { path: 'airi_docs/patches/runtime.patch', token: 'correction_target_realization_v1.json' },
    { path: 'start-airi-local-stack.ps1', token: 'run_correction_realization_postcondition_eval' }
  ]))
})

test('discovers new first-party runtime components recursively by default', () => {
  withFixture((root) => {
    writeFixture(root, 'ollama-proxy/runtime/worker.py', 'must_act_realization')
    writeFixture(root, 'moss-tts-nano/runtime.py', 'run_affect_broadcast_eval')
    writeFixture(root, 'new-component/runtime.ts', 'run_guarded_delta_eval')
  }, (root) => assert.deepEqual(scanAffectEvaluatorRuntimeFence(root), [
    { path: 'moss-tts-nano/runtime.py', token: 'run_affect_broadcast_eval' },
    { path: 'new-component/runtime.ts', token: 'run_guarded_delta_eval' },
    { path: 'ollama-proxy/runtime/worker.py', token: 'must_act_realization' }
  ]))
})

test('ignores explicit test, documentation, evaluator, and data exclusions', () => {
  withFixture((root) => {
    writeFixture(root, 'component/test-runtime.mjs', 'must_act_realization')
    writeFixture(root, 'component/runtime.spec.ts', 'must_act_realization')
    writeFixture(root, 'component/docs/note.mjs', 'must_act_realization')
    writeFixture(root, 'ollama-proxy/eval/run_guarded_delta_eval.py', 'must_act_realization')
    writeFixture(root, 'moss-tts-nano/benchmarks/result.py', 'must_act_realization')
  }, (root) => assert.deepEqual(scanAffectEvaluatorRuntimeFence(root), []))
})

test('detects case variations with deterministic relative-path ordering', () => {
  withFixture((root) => {
    writeFixture(root, 'stt/z.py', 'MUST_ACT_REALIZATION_V1.JSON')
    writeFixture(root, 'broadcast-director/a.mjs', 'Correction_Target_Realization')
  }, (root) => assert.deepEqual(scanAffectEvaluatorRuntimeFence(root), [
    { path: 'broadcast-director/a.mjs', token: 'correction_target_realization' },
    { path: 'stt/z.py', token: 'must_act_realization' },
    { path: 'stt/z.py', token: 'must_act_realization_v1.json' }
  ]))
})

test('fails closed for missing, invalid, and linked roots', (t) => {
  assert.throws(() => scanAffectEvaluatorRuntimeFence(path.join(os.tmpdir(), 'does-not-exist-airi-runtime-fence')))
  assert.throws(() => scanAffectEvaluatorRuntimeFence(null))
  withFixture((root) => writeFixture(root, 'source.py', 'pass'), (root) => {
    const linkedRoot = `${root}-link`
    try {
      fs.symlinkSync(root, linkedRoot, 'dir')
    } catch (error) {
      if (error?.code === 'EPERM') return t.skip('symlink creation is unavailable')
      throw error
    }
    try {
      assert.throws(() => scanAffectEvaluatorRuntimeFence(linkedRoot), /non-link directory/)
    } finally {
      fs.rmSync(linkedRoot, { recursive: true, force: true })
    }
  })
})

test('skips excluded links and rejects included links without following them', (t) => {
  withFixture((root) => {
    const outside = fs.mkdtempSync(path.join(os.tmpdir(), 'airi-runtime-fence-outside-'))
    try {
      writeFixture(outside, 'secret.py', 'must_act_realization')
      try {
        fs.symlinkSync(outside, path.join(root, '.git'), 'dir')
        fs.symlinkSync(outside, path.join(root, 'runtime-link'), 'dir')
      } catch (error) {
        if (error?.code === 'EPERM') return t.skip('symlink creation is unavailable')
        throw error
      }
      assert.throws(() => scanAffectEvaluatorRuntimeFence(root), /runtime-link/)
      fs.rmSync(path.join(root, 'runtime-link'), { recursive: true, force: true })
      assert.deepEqual(scanAffectEvaluatorRuntimeFence(root), [])
    } finally {
      fs.rmSync(outside, { recursive: true, force: true })
    }
  }, () => {})
})

test('current production scan has no evaluator-only references', () => {
  assert.deepEqual(scanAffectEvaluatorRuntimeFence(REPOSITORY_ROOT), [])
})
