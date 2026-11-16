import axios from 'axios'
import { tokenStorage } from '@/utils/storage'

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:5000').replace(/\/$/, '')

const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Attach the JWT to every request.
api.interceptors.request.use((config) => {
  const token = tokenStorage.get()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// A 401 on a protected endpoint means the session is gone. Instead of a hard
// page reload, tell the AuthProvider (registered below) to clear its state so
// React Router redirects to /login and remembers where the user was.
let unauthorizedHandler = null
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

const AUTH_ENDPOINT = /\/api\/auth\/(login|register)$/

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const isAuthRequest = AUTH_ENDPOINT.test(error.config?.url ?? '')
    if (error.response?.status === 401 && !isAuthRequest) unauthorizedHandler?.()
    return Promise.reject(error)
  },
)

const FALLBACK_MESSAGE = 'Something went wrong. Please try again.'
const STATUS_MESSAGES = {
  400: 'Please check the information you entered.',
  401: 'Your session has expired. Please log in again.',
  403: 'You do not have permission to perform this action.',
  404: 'The requested resource could not be found.',
}

// Turn any axios error into a message that is safe and useful to show.
// The backend already sends clear messages ("Invalid status transition...",
// "Invalid email or password"), so prefer them over generic wording.
export function getErrorMessage(error) {
  if (!error?.response) return 'Unable to reach the server. Please check your connection.'
  const { status, data } = error.response
  if (status >= 500) {
    // Show the server's explanation when it gave a specific one (e.g. a missing
    // database table); otherwise say which status it was, which makes problems
    // like 502 "server restarting" vs 500 "code error" easy to tell apart.
    const specific = data?.message && data.message !== 'Internal server error' ? data.message : null
    return specific ?? `The server ran into a problem (error ${status}). Please try again in a moment.`
  }
  return data?.message || STATUS_MESSAGES[status] || FALLBACK_MESSAGE
}

// Every endpoint wraps its payload as { success, message, data }.
export const unwrap = (response) => response.data?.data ?? {}

export default api
