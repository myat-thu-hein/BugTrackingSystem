// Matches a typed question to the closest FAQ, entirely in the browser
// (instant, free, works offline). No AI: words are normalised and compared,
// with question words counting most, then keywords, then the answer text.
//
// Forgiving on purpose:
//  - small typos match ("notifcation" ~ "notification")
//  - partial words match ("notif" ~ "notification")
//  - any language's letters are kept (Thai, Burmese, accents...), and text
//    without spaces between words is compared by character pairs instead

const STOP_WORDS = new Set(
  `a an and are as at be but by can could do does did for from get got had has have how i if in into is it its
  me my of on or our so than that the their them then there these they this to too us was we were what when where
  which who why will with would you your please hi hello hey thanks thank want need just not no any some way one also`.split(/\s+/),
)

// Words that mean the same thing for our app.
const SYNONYMS = {
  issue: 'bug', issues: 'bug', ticket: 'bug', defect: 'bug', problem: 'bug', error: 'bug',
  mail: 'email', emails: 'email', 'e-mail': 'email',
  remove: 'delete', erase: 'delete',
  make: 'create', new: 'create', open: 'create', add: 'create', submit: 'create', report: 'create', file: 'create',
  invitation: 'invite', join: 'invite', code: 'invite',
  permission: 'role', promote: 'role', promotion: 'role',
  stop: 'off', disable: 'off', unsubscribe: 'off',
}

// Words nearly every question here contains ("bug", "project"...). They can
// support a match but never create one on their own.
const GENERIC = new Set(['bug', 'project', 'app', 'page', 'tracker', 'system', 'list', 'thing'])
const GENERIC_WEIGHT = 0.25
const MIN_SCORE = 0.34
const MIN_CHAR_SIMILARITY = 0.5

function stem(word) {
  if (word.length > 5 && word.endsWith('ing')) return word.slice(0, -3)
  if (word.length > 4 && word.endsWith('ed')) return word.slice(0, -2)
  if (word.length > 3 && word.endsWith('s') && !word.endsWith('ss')) return word.slice(0, -1)
  return word
}

function normalise(text = '') {
  return String(text)
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[^\p{L}\p{M}\p{N}\s-]/gu, ' ') // keep letters/digits of every script
}

export function tokenize(text = '') {
  return normalise(text)
    .split(/[\s-]+/)
    .filter((word) => word && !STOP_WORDS.has(word))
    .map((word) => stem(SYNONYMS[word] ?? word))
    .map((word) => SYNONYMS[word] ?? word)
}

// Levenshtein distance, stopping early once it exceeds `max`.
function editDistance(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i++) {
    const current = [i]
    let rowMin = i
    for (let j = 1; j <= b.length; j++) {
      current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
      rowMin = Math.min(rowMin, current[j])
    }
    if (rowMin > max) return max + 1
    previous = current
  }
  return previous[b.length]
}

/** Does `word` match something in `vocabulary`? Exact, then partial word, then a small typo. */
function hasWord(vocabulary, word) {
  if (vocabulary.has(word)) return true
  if (word.length < 4) return false
  const allowedTypos = word.length >= 8 ? 2 : word.length >= 5 ? 1 : 0
  for (const candidate of vocabulary) {
    if (candidate.length >= 4 && (candidate.startsWith(word) || word.startsWith(candidate))) return true
    if (allowedTypos && editDistance(word, candidate, allowedTypos) <= allowedTypos) return true
  }
  return false
}

// Character-pair similarity (Dice coefficient), for scripts written without
// spaces between words, e.g. Thai or Burmese.
function charPairs(text) {
  const compact = normalise(text).replace(/\s+/g, '')
  const pairs = new Map()
  for (let i = 0; i < compact.length - 1; i++) {
    const pair = compact.slice(i, i + 2)
    pairs.set(pair, (pairs.get(pair) ?? 0) + 1)
  }
  return pairs
}

function charSimilarity(a, b) {
  const pa = charPairs(a)
  const pb = charPairs(b)
  let overlap = 0
  let total = 0
  for (const [pair, count] of pa) {
    overlap += Math.min(count, pb.get(pair) ?? 0)
    total += count
  }
  for (const count of pb.values()) total += count
  return total === 0 ? 0 : (2 * overlap) / total
}

const hasNonLatinLetters = (text) => /[^\p{Script=Latin}\p{N}\s\p{P}\p{S}]/u.test(text)

function wordScore(words, faq) {
  const question = new Set(tokenize(faq.question))
  const keywords = new Set(tokenize(faq.keywords))
  const answer = new Set(tokenize(faq.answer))
  let total = 0
  let strongHits = 0
  for (const word of words) {
    if (GENERIC.has(word)) {
      if (question.has(word) || keywords.has(word)) total += GENERIC_WEIGHT
    } else if (hasWord(question, word)) {
      total += 1
      strongHits += 1
    } else if (hasWord(keywords, word)) {
      total += 0.8
      strongHits += 1
    } else if (answer.has(word)) {
      total += 0.3
    }
  }
  return strongHits > 0 ? total / words.length : 0
}

/**
 * Best FAQ for `query`, or null if nothing is a reasonable match.
 * Returns { faq, score, alternatives } where alternatives are the next
 * closest matches (for "Did you mean...?").
 */
export function findBestFaq(query, faqs = []) {
  if (!query?.trim() || faqs.length === 0) return null
  const words = [...new Set(tokenize(query))]
  const useCharacters = hasNonLatinLetters(query)

  const scored = faqs
    .map((faq) => {
      let score = words.length > 0 ? wordScore(words, faq) : 0
      if (score < MIN_SCORE && useCharacters) {
        const similarity = Math.max(charSimilarity(query, faq.question), charSimilarity(query, faq.keywords ?? ''))
        if (similarity >= MIN_CHAR_SIMILARITY) score = similarity
      }
      return { faq, score }
    })
    .filter((entry) => entry.score >= MIN_SCORE)
    .sort((a, b) => b.score - a.score || (b.faq.hits ?? 0) - (a.faq.hits ?? 0))

  if (scored.length === 0) return null
  const [best, ...rest] = scored
  return { faq: best.faq, score: best.score, alternatives: rest.slice(0, 2).map((entry) => entry.faq) }
}

// The "most asked" suggestions: highest hit count first.
export function topFaqs(faqs = [], count = 4) {
  return [...faqs].sort((a, b) => (b.hits ?? 0) - (a.hits ?? 0)).slice(0, count)
}
