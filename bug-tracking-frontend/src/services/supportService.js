import api, { unwrap } from './api'

export async function getFaqs({ signal } = {}) {
  return unwrap(await api.get('/api/support/faqs', { signal })).faqs ?? []
}

// "This answer helped": ranks the most-asked suggestions. Fire-and-forget.
export function recordFaqHit(id) {
  return api.post(`/api/support/faqs/${id}/hit`).catch(() => {})
}

export async function createFaq(faq) {
  return unwrap(await api.post('/api/support/faqs', faq)).faq
}

export async function updateFaq(id, faq) {
  return unwrap(await api.put(`/api/support/faqs/${id}`, faq)).faq
}

export async function deleteFaq(id) {
  await api.delete(`/api/support/faqs/${id}`)
}

export async function askQuestion(question) {
  return unwrap(await api.post('/api/support/questions', { question })).question
}

export async function getQuestions({ signal } = {}) {
  return unwrap(await api.get('/api/support/questions', { signal })).questions ?? []
}

export async function answerQuestion(id, answer, addToFaq) {
  return unwrap(await api.put(`/api/support/questions/${id}/answer`, { answer, add_to_faq: addToFaq }))
}

// Admin: add the starter questions the project doesn't have yet. Resolves to { faqs, message }.
export async function addDefaultFaqs() {
  const response = await api.post('/api/support/faqs/defaults')
  return { ...unwrap(response), message: response.data?.message }
}
