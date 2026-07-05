import type { CSSProperties } from 'react'
import { NOTIFICATION_TTL_MS, type ChiliNotification } from '../lib/chiliNotifications'

type Props = {
  notification: ChiliNotification | null
  exiting?: boolean
}

export function ChiliNotificationBanner({ notification, exiting = false }: Props) {
  if (!notification) return null

  return (
    <div
      key={notification.id}
      className={`chili-notice is-${notification.kind}${exiting ? ' is-exiting' : ''}`}
      style={{ '--notice-duration': `${NOTIFICATION_TTL_MS}ms` } as CSSProperties}
      aria-live="polite"
      role="status"
    >
      <span className="chili-notice-mark" aria-hidden="true" />
      <p className="chili-notice-text">{notification.message}</p>
      {!exiting ? <span className="chili-notice-ttl" aria-hidden="true" /> : null}
    </div>
  )
}
