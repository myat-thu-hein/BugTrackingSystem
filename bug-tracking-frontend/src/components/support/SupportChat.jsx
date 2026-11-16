import { Bot, MessageCircleQuestion, RotateCcw, Send, ThumbsUp, UserRound, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { QUESTION_MAX } from '@/config/constants'
import { getErrorMessage } from '@/services/api'
import { askQuestion, getFaqs, recordFaqHit } from '@/services/supportService'
import { findBestFaq, topFaqs } from '@/utils/faqMatch'

const GREETING = {
  from: 'bot',
  text: "Hi! I'm the help assistant. Ask a question about using the bug tracker, or pick one of the most asked questions.",
}

let nextId = 0
const message = (fields) => ({ id: ++nextId, ...fields })

function Bubble({ from, children }) {
  const isBot = from === 'bot'
  return (
    <div className={`flex items-end gap-2 ${isBot ? '' : 'flex-row-reverse'}`}>
      <span
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${isBot ? 'bg-primary-100 text-primary-700' : 'bg-gray-200 text-gray-600'}`}
        aria-hidden="true"
      >
        {isBot ? <Bot size={15} /> : <UserRound size={15} />}
      </span>
      <div
        className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
          isBot ? 'rounded-bl-sm bg-gray-100 text-gray-800' : 'rounded-br-sm bg-primary-600 text-white'
        }`}
      >
        {children}
      </div>
    </div>
  )
}

function Chip({ children, onClick, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-full border border-primary-200 bg-white px-3 py-1.5 text-left text-xs font-medium text-primary-700 hover:bg-primary-50 disabled:opacity-50"
    >
      {children}
    </button>
  )
}

/**
 * Floating "Help" chat for project members.
 *  - suggests the most asked questions (ranked by how often they helped)
 *  - answers typed questions instantly from the project's FAQ
 *  - when there's no good answer, sends the question to the project admins
 *    (they get a live notification + email, and the reply comes back as a
 *    notification)
 */
export default function SupportChat() {
  const [open, setOpen] = useState(false)
  const [faqs, setFaqs] = useState(null) // null until the first successful load
  const [loadError, setLoadError] = useState('')
  const [messages, setMessages] = useState([message(GREETING)])
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const endRef = useRef(null)
  const inputRef = useRef(null)

  // The FAQ is (re)loaded every time the chat opens, so answers an admin just
  // added are available without reloading the page. A failed load is NOT
  // remembered as "no FAQs" (that used to make the chat useless until a page
  // reload, e.g. when the server was still waking up); it can be retried.
  const loadingRef = useRef(null)
  const loadFaqs = useCallback(() => {
    if (!loadingRef.current) {
      setLoadError('')
      loadingRef.current = getFaqs()
        .then((rows) => {
          setFaqs(rows)
          return rows
        })
        .catch((err) => {
          setLoadError(getErrorMessage(err))
          return null
        })
        .finally(() => {
          loadingRef.current = null
        })
    }
    return loadingRef.current
  }, [])

  useEffect(() => {
    if (open) loadFaqs()
  }, [open, loadFaqs])

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const suggestions = useMemo(() => topFaqs(faqs ?? [], 4), [faqs])
  const push = (...items) => setMessages((current) => [...current, ...items.map(message)])

  function answerWith(faq, alternatives = []) {
    push({ from: 'bot', text: faq.answer, faq, alternatives, kind: 'answer' })
  }

  async function ask(question) {
    const trimmed = question.trim()
    if (!trimmed) return
    setText('')
    push({ from: 'user', text: trimmed })

    // A question typed while the FAQ is still loading waits for it, instead
    // of being matched against an empty list.
    // Likewise when the chat was just reopened and a refresh is in flight:
    // use the fresh list, not the one from last time.
    const available = loadingRef.current || faqs === null ? await loadFaqs() : faqs
    if (available === null) {
      push({ from: 'bot', text: "I couldn't load the FAQ just now. You can still send your question to your admin.", kind: 'no-match', question: trimmed })
      return
    }
    if (available.length === 0) {
      push({ from: 'bot', text: "This project doesn't have any FAQs yet, so I can't answer that myself.", kind: 'no-match', question: trimmed })
      return
    }
    const match = findBestFaq(trimmed, available)
    if (match) answerWith(match.faq, match.alternatives)
    else push({ from: 'bot', text: "I couldn't find an answer to that in this project's FAQ.", kind: 'no-match', question: trimmed })
  }

  function pickSuggestion(faq) {
    push({ from: 'user', text: faq.question })
    answerWith(faq)
    recordFaqHit(faq.id)
  }

  function markHelpful(item) {
    recordFaqHit(item.faq.id)
    setMessages((current) => current.map((m) => (m.id === item.id ? { ...m, resolved: true } : m)))
    push({ from: 'bot', text: 'Great, glad that helped!' })
  }

  async function sendToAdmin(item, question) {
    setSending(true)
    setMessages((current) => current.map((m) => (m.id === item.id ? { ...m, resolved: true } : m)))
    try {
      await askQuestion(question)
      push({ from: 'bot', text: "Sent to your project admin. You'll get a notification when they reply." })
    } catch (err) {
      push({ from: 'bot', text: `Sorry, that didn't send: ${getErrorMessage(err)}` })
      setMessages((current) => current.map((m) => (m.id === item.id ? { ...m, resolved: false } : m)))
    } finally {
      setSending(false)
    }
  }

  // The question a "not helpful" answer was for: the user message just before it.
  function questionBefore(item) {
    const index = messages.findIndex((m) => m.id === item.id)
    return [...messages.slice(0, index)].reverse().find((m) => m.from === 'user')?.text ?? ''
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-label={open ? 'Close help chat' : 'Open help chat'}
        className="fixed bottom-4 right-4 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-primary-600 text-white shadow-lg transition hover:bg-primary-700 sm:bottom-6 sm:right-6"
      >
        {open ? <X size={24} /> : <MessageCircleQuestion size={26} />}
      </button>

      {open && (
        <section
          aria-label="Help chat"
          className="fixed bottom-20 right-4 z-30 flex h-[min(32rem,calc(100vh-7rem))] w-[min(23rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl sm:bottom-24 sm:right-6"
        >
          <header className="flex items-center gap-3 bg-primary-600 px-4 py-3 text-white">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20" aria-hidden="true">
              <Bot size={18} />
            </span>
            <div>
              <h2 className="text-sm font-semibold">Help &amp; Support</h2>
              <p className="text-xs text-primary-100">Instant answers · your admin for the rest</p>
            </div>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
            {messages.map((item) => (
              <div key={item.id} className="space-y-2">
                <Bubble from={item.from}>{item.text}</Bubble>

                {item.kind === 'answer' && !item.resolved && (
                  <div className="ml-9 flex flex-wrap gap-1.5">
                    <Chip onClick={() => markHelpful(item)}>
                      <ThumbsUp size={12} className="mr-1 inline" aria-hidden="true" />
                      That helped
                    </Chip>
                    {item.alternatives?.map((faq) => (
                      <Chip key={faq.id} onClick={() => pickSuggestion(faq)}>
                        {faq.question}
                      </Chip>
                    ))}
                    <Chip disabled={sending} onClick={() => sendToAdmin(item, questionBefore(item))}>
                      No, ask my admin
                    </Chip>
                  </div>
                )}
                {item.kind === 'no-match' && !item.resolved && (
                  <div className="ml-9 flex flex-wrap gap-1.5">
                    <Chip disabled={sending} onClick={() => sendToAdmin(item, item.question)}>
                      Send this question to my admin
                    </Chip>
                  </div>
                )}
              </div>
            ))}

            <div ref={endRef} />
          </div>

          {/* Always visible, so new FAQs, load errors and the most asked
              questions show up at any point in the conversation. */}
          <div className="border-t border-gray-100 px-3 pt-2.5">
            {loadError && faqs === null ? (
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs text-red-600">Couldn&apos;t load the FAQ: {loadError}</p>
                <Chip onClick={loadFaqs}>
                  <RotateCcw size={12} className="mr-1 inline" aria-hidden="true" />
                  Try again
                </Chip>
              </div>
            ) : faqs === null ? (
              <p className="text-xs text-gray-400">Loading the FAQ...</p>
            ) : suggestions.length === 0 ? (
              <p className="text-xs text-gray-500">This project has no FAQs yet. Type your question and I&apos;ll pass it to your admin.</p>
            ) : (
              <div>
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-400">Most asked</p>
                <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
                  {suggestions.map((faq) => (
                    <span key={faq.id} className="shrink-0">
                      <Chip onClick={() => pickSuggestion(faq)}>{faq.question}</Chip>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault()
              ask(text)
            }}
            className="flex items-center gap-2 p-3 pt-2"
          >
            <input
              ref={inputRef}
              aria-label="Type your question"
              className="input flex-1 rounded-full"
              placeholder="Type your question..."
              maxLength={QUESTION_MAX}
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
            <button
              type="submit"
              disabled={!text.trim()}
              aria-label="Send"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-40"
            >
              <Send size={16} />
            </button>
          </form>
        </section>
      )}
    </>
  )
}
