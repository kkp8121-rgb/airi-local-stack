const EVENT_KEYS = Object.freeze(['eventId', 'viewerKey', 'displayName', 'text', 'kind', 'publishedAtMs'])
const QUESTION_CUES = Object.freeze(['뭐야', '뭐예요', '무엇이야', '무엇인가요', '어떻게 생각해', '어떻게 생각하세요', '어떻게 해', '어떻게 되나요', '어떻게 할까요', '언제 와', '언제 와요', '언제 해', '언제 하나요', '언제 인가요', '오늘 뭐해', '어디야', '왜 그래', '왜 그런가요', '왜 그럴까'])
const QUESTION_ENDINGS = Object.freeze(['인가요', '할까요', '되나요'])
const QUESTION_PREFIXES = Object.freeze(['무슨', '어느', '누구', '몇', '얼마'])
const QUESTION_SUFFIXES = Object.freeze(['야', '예요', '인가요', '인지'])
const TOPIC_CUES = Object.freeze(['그 얘기 더', '이어서', '관련해서', '말 나온 김에', '아까 말한', '자세히', '계속 얘기'])
const SINCERE_CUES = Object.freeze(['고마워', '감사해', '감사합니다', '미안해', '미안합니다', '감동', '진심', '힘들었겠다', '수고했어', '수고했어요', '괜찮아', '공감'])
const CHEER_CUES = Object.freeze(['화이팅', '파이팅', '힘내', '응원', '가보자', '할 수 있어'])

function isBase64UrlCharacter(code) {
  return (code >= 48 && code <= 57) || (code >= 65 && code <= 90) || (code >= 97 && code <= 122) || code === 45 || code === 95
}

function hasId(value, prefix) {
  if (typeof value !== 'string' || !value.startsWith(prefix) || value.length !== prefix.length + 43) return false
  for (let index = prefix.length; index < value.length; index += 1) if (!isBase64UrlCharacter(value.charCodeAt(index))) return false
  return true
}

function safeText(value, maximum) {
  if (typeof value !== 'string' || value.length === 0 || value.length > maximum * 2) return false
  let points = 0
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index)
    if ((code >= 0 && code <= 31) || (code >= 127 && code <= 159) || code === 0x061c || code === 0x200e || code === 0x200f || (code >= 0x202a && code <= 0x202e) || (code >= 0x2066 && code <= 0x2069)) return false
    if (code >= 0xd800 && code <= 0xdbff) {
      if (index + 1 >= value.length) return false
      const next = value.charCodeAt(++index)
      if (next < 0xdc00 || next > 0xdfff) return false
    } else if (code >= 0xdc00 && code <= 0xdfff) return false
    points += 1
    if (points > maximum) return false
  }
  return value === value.normalize('NFC')
}

function snapshotEvent(value) {
  try {
    if (value === null || typeof value !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null
    const keys = Reflect.ownKeys(value)
    if (keys.length !== EVENT_KEYS.length || keys.some(key => typeof key !== 'string') || !EVENT_KEYS.every(key => keys.includes(key))) return null
    const copy = Object.create(null)
    for (const key of EVENT_KEYS) {
      const descriptor = Object.getOwnPropertyDescriptor(value, key)
      if (!descriptor || !('value' in descriptor) || !descriptor.enumerable) return null
      copy[key] = descriptor.value
    }
    return copy
  } catch {
    return null
  }
}

function isWhitespace(code) { return code === 32 || code === 0x00a0 }

function isNegatedAt(text, index, length) {
  const before = text.slice(0, index).trimEnd()
  if (before.endsWith('안') || before.endsWith('못')) return true
  const after = text.slice(index + length, index + length + 20)
  return after.includes('안 해') || after.includes('안해') || after.includes('안 할') || after.includes('못 할') || after.includes('않') || after.includes('하지 않아') || after.includes('하지않아') || after.includes('하지 마') || after.includes('하지마') || after.includes('할 생각 없어') || after.includes('할생각없어') || after.includes('필요 없어') || after.includes('필요없어') || after.includes('필요는 없어') || after.includes('필요는없어') || after.includes('아니')
}

function includesCue(text, cue) {
  let index = text.indexOf(cue)
  while (index !== -1) {
    if (!isNegatedAt(text, index, cue.length)) return true
    index = text.indexOf(cue, index + cue.length)
  }
  return false
}

function includesAny(text, cues) { return cues.some(cue => includesCue(text, cue)) }
function endsWithAny(text, endings) { return endings.some(ending => text.endsWith(ending)) }
function hasShortWhQuestion(text) {
  return QUESTION_PREFIXES.some(prefix => QUESTION_SUFFIXES.some(suffix => text.endsWith(prefix + suffix) || text.endsWith(prefix + ' ' + suffix)))
}

function hasQuestionPunctuation(text) {
  if (text.includes('？')) return true
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] !== '?') continue
    let start = index
    while (start > 0 && !isWhitespace(text.charCodeAt(start - 1))) start -= 1
    let end = index + 1
    while (end < text.length && !isWhitespace(text.charCodeAt(end))) end += 1
    const beforeMark = text.slice(start, index)
    if (!beforeMark.includes('http://') && !beforeMark.includes('https://')) return true
  }
  return false
}

function validEvent(event) {
  return event !== null && hasId(event.eventId, 'yt:v1:') && hasId(event.viewerKey, 'viewer:v1:') &&
    safeText(event.displayName, 80) && safeText(event.text, 1000) && event.kind === 'text' &&
    Number.isSafeInteger(event.publishedAtMs) && event.publishedAtMs >= 0
}

function isQuestion(text) {
  return hasQuestionPunctuation(text) || endsWithAny(text, QUESTION_CUES) || endsWithAny(text, QUESTION_ENDINGS) || hasShortWhQuestion(text)
}

function priorityFor(text) {
  if (isQuestion(text)) return 'question'
  if (includesAny(text, TOPIC_CUES)) return 'topic_expansion'
  if (includesAny(text, SINCERE_CUES)) return 'sincere_reaction'
  if (includesAny(text, CHEER_CUES)) return 'cheer'
  return 'positive'
}

/** Classify an already-screened B1 chat event without retaining event data. */
export function classifyBroadcastPriority(screenedEvent) {
  const event = snapshotEvent(screenedEvent)
  if (!validEvent(event)) return null
  return Object.freeze({ priority: priorityFor(event.text) })
}
