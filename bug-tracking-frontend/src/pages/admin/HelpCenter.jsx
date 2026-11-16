import { CheckCircle2, LifeBuoy, MessageCircleQuestion, Pencil, Plus, Send, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import EmptyState from '@/components/feedback/EmptyState'
import ErrorState from '@/components/feedback/ErrorState'
import Button from '@/components/ui/Button'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import Field from '@/components/ui/Field'
import Modal from '@/components/ui/Modal'
import PageHeader from '@/components/ui/PageHeader'
import Skeleton from '@/components/ui/Skeleton'
import { ANSWER_MAX, QUESTION_MAX } from '@/config/constants'
import { useFetch } from '@/hooks/useFetch'
import { useLiveRefresh } from '@/hooks/useLiveRefresh'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/services/api'
import * as support from '@/services/supportService'
import { formatDateTime, formatRelative } from '@/utils/format'

// --- questions from the team ---------------------------------------------------
function QuestionCard({ question, onAnswered }) {
  const toast = useToast()
  const [answer, setAnswer] = useState('')
  const [addToFaq, setAddToFaq] = useState(true)
  const [sending, setSending] = useState(false)
  const answered = question.status === 'answered'

  async function submit(event) {
    event.preventDefault()
    if (answer.trim().length < 3) return
    setSending(true)
    try {
      const result = await support.answerQuestion(question.id, answer.trim(), addToFaq)
      toast.success(addToFaq ? 'Answer sent and added to the FAQ.' : 'Answer sent.')
      onAnswered(result)
    } catch (err) {
      toast.error(getErrorMessage(err))
      setSending(false)
    }
  }

  return (
    <li className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="font-medium text-gray-900">&ldquo;{question.question}&rdquo;</p>
        {answered && <CheckCircle2 size={18} className="shrink-0 text-green-600" aria-label="Answered" />}
      </div>
      <p className="mt-1 text-xs text-gray-400">
        {question.user_name} · <time title={formatDateTime(question.created_at)}>{formatRelative(question.created_at)}</time>
      </p>

      {answered ? (
        <p className="mt-3 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">
          <span className="font-medium">{question.answered_by_name ?? 'Admin'}:</span> {question.answer}
        </p>
      ) : (
        <form onSubmit={submit} className="mt-3 flex flex-col gap-2">
          <textarea
            aria-label={`Answer to: ${question.question}`}
            className="input resize-y"
            rows={2}
            maxLength={ANSWER_MAX}
            placeholder="Write an answer..."
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-xs text-gray-600">
              <input type="checkbox" checked={addToFaq} onChange={(event) => setAddToFaq(event.target.checked)} className="rounded border-gray-300" />
              Also add to the FAQ so the chat answers it next time
            </label>
            <Button type="submit" icon={Send} loading={sending} disabled={answer.trim().length < 3}>
              Send answer
            </Button>
          </div>
        </form>
      )}
    </li>
  )
}

// --- FAQ editor -------------------------------------------------------------------
const EMPTY_FAQ = { question: '', answer: '', keywords: '' }

function FaqDialog({ faq, isOpen, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(EMPTY_FAQ)
  const [saving, setSaving] = useState(false)
  const [openedFor, setOpenedFor] = useState(null)

  // Reset the form each time the dialog opens (for a different FAQ or a new one).
  const key = isOpen ? (faq?.id ?? 'new') : null
  if (key !== openedFor) {
    setOpenedFor(key)
    setForm(faq ? { question: faq.question, answer: faq.answer, keywords: faq.keywords ?? '' } : EMPTY_FAQ)
  }

  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }))
  const valid = form.question.trim().length >= 3 && form.answer.trim().length >= 3

  async function submit(event) {
    event.preventDefault()
    if (!valid) return
    setSaving(true)
    try {
      const saved = faq ? await support.updateFaq(faq.id, form) : await support.createFaq(form)
      toast.success(faq ? 'FAQ updated.' : 'FAQ added.')
      onSaved(saved)
      onClose()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title={faq ? 'Edit FAQ' : 'Add FAQ'} description="The help chat matches questions using these words." isOpen={isOpen} onClose={onClose} dismissible={!saving} size="md">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Question" maxLength={QUESTION_MAX} value={form.question} onChange={update('question')} data-autofocus />
        <Field as="textarea" rows={4} className="resize-y" label="Answer" maxLength={ANSWER_MAX} showCount value={form.answer} onChange={update('answer')} />
        <Field
          label="Keywords (optional)"
          hint="Other words people might use, separated by spaces, e.g. 'export download csv excel'."
          maxLength={300}
          value={form.keywords}
          onChange={update('keywords')}
        />
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" loading={saving} loadingText="Saving..." disabled={!valid}>
            {faq ? 'Save changes' : 'Add FAQ'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export default function HelpCenter() {
  usePageTitle('Help Center')
  const toast = useToast()
  const questionsFetch = useFetch((signal) => support.getQuestions({ signal }), [])
  const faqsFetch = useFetch((signal) => support.getFaqs({ signal }), [])
  const [editing, setEditing] = useState(undefined) // undefined: closed, null: new, object: edit
  const [deleting, setDeleting] = useState(null)
  const [deletingBusy, setDeletingBusy] = useState(false)
  const [seeding, setSeeding] = useState(false)

  // A teammate's new question appears here live.
  useLiveRefresh(questionsFetch.reload, (notification) => notification.type === 'support_question')

  if (questionsFetch.loading || faqsFetch.loading) {
    return (
      <div className="flex flex-col gap-4" role="status" aria-label="Loading help center">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (questionsFetch.error) return <ErrorState message={questionsFetch.error} onRetry={questionsFetch.reload} />
  if (faqsFetch.error) return <ErrorState message={faqsFetch.error} onRetry={faqsFetch.reload} />

  const questions = questionsFetch.data ?? []
  const faqs = faqsFetch.data ?? []
  const open = questions.filter((q) => q.status === 'open')
  const answered = questions.filter((q) => q.status === 'answered').slice(0, 5)

  function handleAnswered({ question, faq }) {
    questionsFetch.setData((current) => current.map((q) => (q.id === question.id ? { ...q, ...question } : q)))
    if (faq) faqsFetch.setData((current) => [...current, faq])
  }

  function handleSaved(saved) {
    faqsFetch.setData((current) =>
      current.some((f) => f.id === saved.id) ? current.map((f) => (f.id === saved.id ? saved : f)) : [...current, saved],
    )
  }

  async function addStarterFaqs() {
    setSeeding(true)
    try {
      const { faqs: added, message } = await support.addDefaultFaqs()
      faqsFetch.setData((current) => [...current, ...(added ?? [])])
      toast.success(`${message}.`)
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSeeding(false)
    }
  }

  async function confirmDelete() {
    setDeletingBusy(true)
    try {
      await support.deleteFaq(deleting.id)
      faqsFetch.setData((current) => current.filter((f) => f.id !== deleting.id))
      toast.success('FAQ deleted.')
      setDeleting(null)
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setDeletingBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Help Center" subtitle="Answer your team's questions and manage what the help chat replies." />

      <section aria-labelledby="questions-heading" className="flex flex-col gap-3">
        <h2 id="questions-heading" className="flex items-center gap-2 text-sm font-semibold text-gray-800">
          <MessageCircleQuestion size={16} aria-hidden="true" /> Questions waiting for an answer
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">{open.length}</span>
        </h2>
        {open.length === 0 ? (
          <div className="card">
            <EmptyState icon={LifeBuoy} message="No open questions." description="When the help chat can't answer something, the question shows up here." />
          </div>
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {open.map((question) => (
              <QuestionCard key={question.id} question={question} onAnswered={handleAnswered} />
            ))}
          </ul>
        )}
        {answered.length > 0 && (
          <details className="card p-4">
            <summary className="cursor-pointer text-sm font-medium text-gray-700">Recently answered ({answered.length})</summary>
            <ul className="mt-3 grid gap-3 lg:grid-cols-2">
              {answered.map((question) => (
                <QuestionCard key={question.id} question={question} onAnswered={handleAnswered} />
              ))}
            </ul>
          </details>
        )}
      </section>

      <section aria-labelledby="faq-heading" className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 id="faq-heading" className="text-sm font-semibold text-gray-800">
            FAQ <span className="font-normal text-gray-400">· most asked first</span>
          </h2>
          <Button icon={Plus} onClick={() => setEditing(null)}>
            Add FAQ
          </Button>
        </div>
        {faqs.length === 0 ? (
          <div className="card">
            <EmptyState
              message="No FAQs yet, so the help chat can't answer anything."
              description="Start with the built-in questions about using the bug tracker, then add your own."
              action={
                <Button icon={Sparkles} loading={seeding} loadingText="Adding..." onClick={addStarterFaqs} className="mt-2">
                  Add starter FAQs
                </Button>
              }
            />
          </div>
        ) : (
          <ul className="card divide-y divide-gray-100">
            {faqs.map((faq) => (
              <li key={faq.id} className="flex items-start gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-gray-900">{faq.question}</p>
                  <p className="mt-1 text-sm text-gray-600">{faq.answer}</p>
                  <p className="mt-1 text-xs text-gray-400">
                    Helped {faq.hits ?? 0} time{faq.hits === 1 ? '' : 's'}
                    {faq.keywords && <> · keywords: {faq.keywords}</>}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button type="button" onClick={() => setEditing(faq)} aria-label={`Edit: ${faq.question}`} className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700">
                    <Pencil size={16} />
                  </button>
                  <button type="button" onClick={() => setDeleting(faq)} aria-label={`Delete: ${faq.question}`} className="rounded-md p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-600">
                    <Trash2 size={16} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <FaqDialog faq={editing ?? null} isOpen={editing !== undefined} onClose={() => setEditing(undefined)} onSaved={handleSaved} />
      <ConfirmDialog
        isOpen={Boolean(deleting)}
        title="Delete this FAQ?"
        message={`"${deleting?.question}" will no longer be answered by the help chat.`}
        confirmLabel="Delete"
        loadingLabel="Deleting..."
        icon={Trash2}
        loading={deletingBusy}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  )
}
