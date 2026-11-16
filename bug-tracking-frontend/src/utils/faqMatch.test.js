import { describe, expect, it } from 'vitest'
import { findBestFaq, tokenize, topFaqs } from './faqMatch'

// Same wording as the backend's starter FAQs (app/services/project_service.py).
const FAQS = [
  { id: 'see', question: "Why can't I see some bugs?", answer: 'Developers only see bugs assigned to them.', keywords: 'see missing hidden visible list developer', hits: 0 },
  { id: 'report', question: 'How do I report a bug?', answer: "Testers click 'Create Bug'.", keywords: 'report create new submit add file log', hits: 2 },
  { id: 'reopen', question: "How do I reopen a bug that isn't really fixed?", answer: 'A tester can click Reopen.', keywords: 'reopen fixed again broken still fail verify', hits: 0 },
  { id: 'email', question: 'How do I turn off email notifications?', answer: 'Go to Settings.', keywords: 'email notifications turn off stop unsubscribe settings', hits: 5 },
  { id: 'role', question: 'How do I become a developer or admin?', answer: 'Ask your admin.', keywords: 'role developer admin promote permission become change', hits: 1 },
]

const best = (query) => findBestFaq(query, FAQS)?.faq.id ?? null

describe('findBestFaq', () => {
  it('matches differently worded questions', () => {
    expect(best('the fix did not work, can I reopen it?')).toBe('reopen')
    expect(best('stop sending me emails')).toBe('email')
    expect(best('How can I submit a new issue')).toBe('report')
    expect(best('can someone promote me to developer')).toBe('role')
  })

  it('returns null when nothing is relevant', () => {
    expect(best("what's the weather in Bangkok")).toBeNull()
    // "bug" and "list" appear everywhere; they mustn't produce a false match.
    expect(best('Can we export the bug list to Excel?')).toBeNull()
    expect(best('   ')).toBeNull()
    expect(findBestFaq('reopen', [])).toBeNull()
  })
})

describe('forgiving matching', () => {
  it('tolerates typos and partial words', () => {
    expect(best('how to turn of emial notifcations')).toBe('email')
    expect(best('reopn')).toBe('reopen')
    expect(best('reopn a bug that is not fixd')).toBe('reopen')
    expect(best('notif settings')).toBe('email')
  })

  it('matches FAQs written in other languages', () => {
    const thai = [...FAQS, { id: 'th', question: 'จะเปิดบั๊กใหม่ได้อย่างไร', answer: 'คลิก Create Bug', keywords: '', hits: 0 }]
    expect(findBestFaq('เปิดบั๊กใหม่', thai)?.faq.id).toBe('th')
    const accented = [...FAQS, { id: 'fr', question: 'Comment créer un rapport?', answer: '...', keywords: 'créer rapport', hits: 0 }]
    expect(findBestFaq('créer rapport', accented)?.faq.id).toBe('fr')
  })

  it('still rejects unrelated short words', () => {
    expect(best('cat')).toBeNull()
    expect(best('สวัสดี')).toBeNull() // "hello" in Thai
  })
})

describe('tokenize / topFaqs', () => {
  it('drops filler words and normalises forms', () => {
    expect(tokenize('How do I reopening the Bugs?')).toEqual(['reopen', 'bug'])
  })

  it('ranks suggestions by how often they helped', () => {
    expect(topFaqs(FAQS, 2).map((faq) => faq.id)).toEqual(['email', 'report'])
  })
})
