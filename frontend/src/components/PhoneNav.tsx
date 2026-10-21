import { CalendarIcon, DumbbellIcon, ListIcon, ScaleIcon } from './icons'

function todayStamp() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
}

function path() {
  return window.location.pathname.replace(/\/+$/, '') || '/'
}

/** Immersive task screens hide the hub nav. */
export function shouldHidePhoneNav(pathname = path()) {
  if (pathname === '/schedule-change') return true
  if (/^\/workout\/[0-9a-f-]{36}$/i.test(pathname)) return true
  return false
}

function isActive(href: string, current: string) {
  if (href.startsWith('/daily')) return current === '/daily' || current.startsWith('/daily/')
  if (href === '/workout') return current === '/workout'
  if (href === '/weekly') return current === '/weekly' || current.startsWith('/weekly/')
  if (href === '/weight') return current === '/weight' || current === '/sober'
  return current === href
}

const ITEMS = [
  { href: () => `/daily/${todayStamp()}`, match: '/daily', label: 'Today', Icon: CalendarIcon },
  { href: () => '/workout', match: '/workout', label: 'Train', Icon: DumbbellIcon },
  { href: () => '/weekly', match: '/weekly', label: 'Week', Icon: ListIcon },
  { href: () => '/weight', match: '/weight', label: 'Body', Icon: ScaleIcon },
] as const

export function PhoneNav() {
  const current = path()
  if (shouldHidePhoneNav(current)) return null

  return (
    <nav className="phone-nav" aria-label="Phone">
      {ITEMS.map(({ href, match, label, Icon }) => {
        const to = href()
        const active = isActive(match, current)
        return (
          <a
            key={label}
            href={to}
            className={`phone-nav-item${active ? ' is-active' : ''}`}
            aria-current={active ? 'page' : undefined}
          >
            <Icon size={20} />
            <span>{label}</span>
          </a>
        )
      })}
    </nav>
  )
}
