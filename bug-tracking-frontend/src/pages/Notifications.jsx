import { Bell, CheckCheck } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import NotificationItem from '@/components/notifications/NotificationItem'
import EmptyState from '@/components/feedback/EmptyState'
import Button from '@/components/ui/Button'
import PageHeader from '@/components/ui/PageHeader'
import SegmentedControl from '@/components/ui/SegmentedControl'
import { useNotifications } from '@/hooks/useNotifications'
import { usePageTitle } from '@/hooks/usePageTitle'

const MODE_DOT = { live: 'bg-green-500', connecting: 'bg-gray-300', polling: 'bg-amber-400' }
const MODE_TEXT = {
  live: 'Live: new activity appears here instantly.',
  connecting: 'Connecting... new activity will still appear.',
  polling: 'Checking for new activity every few seconds.',
}

export default function Notifications() {
  usePageTitle('Notifications')
  const { items, unreadCount, mode, markRead, markAllRead } = useNotifications()
  const navigate = useNavigate()
  const [filter, setFilter] = useState('all')
  const visible = filter === 'unread' ? items.filter((n) => !n.is_read) : items

  function open(notification) {
    if (!notification.is_read) markRead(notification.id)
    if (notification.link && notification.link !== '/notifications') navigate(notification.link)
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Notifications"
        subtitle={
          <span className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${MODE_DOT[mode]}`} aria-hidden="true" />
            {MODE_TEXT[mode]}
          </span>
        }
        actions={
          unreadCount > 0 && (
            <Button variant="secondary" icon={CheckCheck} onClick={markAllRead}>
              Mark all as read
            </Button>
          )
        }
      />
      <SegmentedControl
        label="Show"
        className="w-full max-w-xs"
        value={filter}
        onChange={setFilter}
        options={[
          { value: 'all', label: 'All' },
          { value: 'unread', label: `Unread (${unreadCount})` },
        ]}
      />
      <div className="card p-2">
        {visible.length === 0 ? (
          <EmptyState
            icon={Bell}
            message={filter === 'unread' ? "You're all caught up." : 'No notifications yet.'}
            description="You'll be notified when bugs are assigned to you, change status, or get comments."
          />
        ) : (
          <div className="flex flex-col divide-y divide-gray-50">
            {visible.map((notification) => (
              <NotificationItem key={notification.id} notification={notification} onOpen={open} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
