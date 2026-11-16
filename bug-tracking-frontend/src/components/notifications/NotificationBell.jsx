import { Bell, CheckCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useNotifications } from '@/hooks/useNotifications'
import NotificationItem from './NotificationItem'

const PREVIEW_COUNT = 6

/** Bell with a live unread badge; opens the latest notifications. */
export default function NotificationBell() {
  const { items, unreadCount, mode, markRead, markAllRead } = useNotifications()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (event) => !ref.current?.contains(event.target) && setOpen(false)
    const onKeyDown = (event) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  function openNotification(notification) {
    setOpen(false)
    if (!notification.is_read) markRead(notification.id)
    if (notification.link) navigate(notification.link)
  }

  const badge = unreadCount > 99 ? '99+' : unreadCount
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={unreadCount ? `Notifications, ${unreadCount} unread` : 'Notifications'}
        className="relative rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-red-500 px-1 text-[11px] font-semibold text-white ring-2 ring-white">
            {badge}
          </span>
        )}
      </button>

      {open && (
        <div role="dialog" aria-label="Notifications" className="absolute right-0 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-gray-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <p className="flex items-center gap-2 text-sm font-semibold text-gray-800">
              Notifications
              <span
                className={`h-2 w-2 rounded-full ${{ live: 'bg-green-500', polling: 'bg-amber-400' }[mode] ?? 'bg-gray-300'}`}
                title={{ live: 'Live', polling: 'Checking every few seconds' }[mode] ?? 'Connecting...'}
              />
            </p>
            {unreadCount > 0 && (
              <button type="button" onClick={markAllRead} className="flex items-center gap-1 text-xs font-medium text-primary-600 hover:underline">
                <CheckCheck size={14} aria-hidden="true" /> Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto p-1.5">
            {items.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-gray-500">You&apos;re all caught up.</p>
            ) : (
              items.slice(0, PREVIEW_COUNT).map((notification) => (
                <NotificationItem key={notification.id} notification={notification} onOpen={openNotification} compact />
              ))
            )}
          </div>
          <Link
            to="/notifications"
            onClick={() => setOpen(false)}
            className="block border-t border-gray-100 px-4 py-2.5 text-center text-sm font-medium text-primary-600 hover:bg-gray-50"
          >
            View all
          </Link>
        </div>
      )}
    </div>
  )
}
