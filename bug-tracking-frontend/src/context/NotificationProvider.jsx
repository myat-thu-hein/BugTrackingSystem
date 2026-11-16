import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import * as notificationService from '@/services/notificationService'
import { openNotificationStream } from '@/services/notificationStream'
import { tokenStorage } from '@/utils/storage'
import { NotificationContext } from './notificationContext'

const POLL_MS = 60_000 // safety net while the live stream is connected
const FALLBACK_POLL_MS = 10_000 // when the server can't do live streams
const MAX_BACKOFF_MS = 30_000
// Notifications that change who you are or where you belong: re-read the session.
const SESSION_TYPES = new Set(['role_changed', 'admin_request_decided'])

/**
 * Notifications for the signed-in user.
 *
 *  1. Loads the latest notifications over HTTP.
 *  2. Opens the live stream; each new notification is added instantly and
 *     shown as a toast.
 *  3. Whenever the stream (re)connects, re-syncs over HTTP, so anything that
 *     happened while disconnected still appears.
 *  4. Reconnects with back-off, and polls once a minute as a safety net.
 *  5. If the server says live streams aren't available (503: it handles one
 *     request at a time), it stops trying and polls every 10 s instead,
 *     still toasting anything new. `mode` tells the UI which one is active.
 */
export function NotificationProvider({ children }) {
  const { user, refreshSession } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [items, setItems] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [mode, setMode] = useState('connecting') // 'live' | 'connecting' | 'polling'
  const userId = user?.id

  const refreshSessionRef = useRef(refreshSession)
  const toastRef = useRef(toast)
  const navigateRef = useRef(navigate)
  useEffect(() => {
    refreshSessionRef.current = refreshSession
    toastRef.current = toast
    navigateRef.current = navigate
  })

  // Ids we've already shown, so polling only announces genuinely new ones.
  const seenRef = useRef(null)

  const announce = useCallback((notification) => {
    toastRef.current.info(notification.message)
    if (SESSION_TYPES.has(notification.type)) {
      // A new role means a different home page; "/" redirects to it.
      refreshSessionRef.current().then(() => {
        if (notification.type === 'role_changed') navigateRef.current('/', { replace: true })
      })
    }
  }, [])

  const sync = useCallback(
    async ({ announceNew = false } = {}) => {
      try {
        const data = await notificationService.getNotifications({ limit: 30 })
        const rows = data.notifications ?? []
        if (announceNew && seenRef.current) {
          rows.filter((n) => !n.is_read && !seenRef.current.has(n.id)).reverse().forEach(announce)
        }
        seenRef.current = new Set([...(seenRef.current ?? []), ...rows.map((n) => n.id)])
        setItems(rows)
        setUnreadCount(data.unread_count ?? 0)
      } catch {
        // keep what we have; the next sync will retry
      }
    },
    [announce],
  )

  useEffect(() => {
    if (!userId) {
      setItems([])
      setUnreadCount(0)
      setMode('connecting')
      seenRef.current = null
      return undefined
    }

    const controller = new AbortController()
    let stopped = false
    let attempt = 0
    let poll = setInterval(() => sync({ announceNew: true }), POLL_MS)
    sync()

    function handleMessage({ event, data }) {
      if (event === 'ready') {
        attempt = 0
        setMode('live')
        sync({ announceNew: true }) // catch up on anything missed while disconnected
        return
      }
      if (event !== 'notification' || !data?.notification) return
      const notification = data.notification
      seenRef.current?.add(notification.id)
      setItems((current) =>
        current.some((item) => item.id === notification.id) ? current : [notification, ...current].slice(0, 50),
      )
      setUnreadCount((count) => count + 1)
      announce(notification)
    }

    function switchToPolling() {
      setMode('polling')
      clearInterval(poll)
      poll = setInterval(() => sync({ announceNew: true }), FALLBACK_POLL_MS)
    }

    async function connectLoop() {
      while (!stopped) {
        const token = tokenStorage.get()
        if (!token) return
        try {
          await openNotificationStream({ token, signal: controller.signal, onMessage: handleMessage })
        } catch (error) {
          if (stopped) return
          if (error.status === 401) return // signed out; AuthProvider handles it
          if (error.status === 503) {
            switchToPolling() // the server can't hold streams open; don't keep trying
            return
          }
          attempt += 1
        }
        if (stopped) return
        setMode('connecting')
        const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** Math.min(attempt, 5))
        await new Promise((resolve) => setTimeout(resolve, delay))
      }
    }

    connectLoop()
    const onVisible = () => document.visibilityState === 'visible' && sync({ announceNew: true })
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      stopped = true
      controller.abort()
      clearInterval(poll)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [userId, sync, announce])

  const markRead = useCallback(async (id) => {
    let wasUnread = false
    setItems((current) =>
      current.map((item) => {
        if (item.id !== id) return item
        wasUnread = !item.is_read
        return { ...item, is_read: true }
      }),
    )
    if (wasUnread) setUnreadCount((count) => Math.max(0, count - 1))
    try {
      const data = await notificationService.markNotificationRead(id)
      setUnreadCount(data.unread_count ?? 0)
    } catch {
      // harmless: it stays unread on the server and the next sync fixes the UI
    }
  }, [])

  const markAllRead = useCallback(async () => {
    setItems((current) => current.map((item) => ({ ...item, is_read: true })))
    setUnreadCount(0)
    try {
      await notificationService.markAllNotificationsRead()
    } catch {
      sync()
    }
  }, [sync])

  const value = useMemo(
    () => ({ items, unreadCount, mode, live: mode === 'live', markRead, markAllRead, refresh: sync }),
    [items, unreadCount, mode, markRead, markAllRead, sync],
  )
  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>
}
