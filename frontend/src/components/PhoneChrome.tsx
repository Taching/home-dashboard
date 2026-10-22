import { useEffect, useId, useRef, useState, type ReactElement } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { useScrollHide } from '../hooks/useScrollHide'
import {
  AlertIcon,
  CalendarIcon,
  ChevronBackIcon,
  DumbbellIcon,
  ListIcon,
  MenuIcon,
  ScaleIcon,
  SlidersIcon,
} from './icons'

export function todayStamp() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
}

function path() {
  return window.location.pathname.replace(/\/+$/, '') || '/'
}

function isActive(href: string, current: string) {
  if (href.startsWith('/daily')) return current === '/daily' || current.startsWith('/daily/')
  if (href === '/workout') return current === '/workout'
  if (href === '/weekly') return current === '/weekly' || current.startsWith('/weekly/')
  if (href === '/weight') return current === '/weight'
  if (href === '/sober') return current === '/sober'
  if (href === '/schedule-change') return current === '/schedule-change'
  if (href === '/training/preferences') return current === '/training/preferences'
  if (href === '/training/exercises') {
    return current === '/training/exercises' || current.startsWith('/training/exercises/')
  }
  return current === href
}

function goBack() {
  if (window.history.length > 1) {
    window.history.back()
    return
  }
  window.location.href = `/daily/${todayStamp()}`
}

type MenuItem = {
  href: string
  label: string
  Icon: (props: { size?: number }) => ReactElement
}

type MenuSection = {
  title: string
  items: MenuItem[]
}

function menuSections(): MenuSection[] {
  const today = todayStamp()
  return [
    {
      title: 'Today',
      items: [
        { href: `/daily/${today}`, label: 'Daily', Icon: CalendarIcon },
        { href: '/workout', label: 'Train', Icon: DumbbellIcon },
        { href: '/weekly', label: 'Week', Icon: ListIcon },
        { href: '/weight', label: 'Body', Icon: ScaleIcon },
      ],
    },
    {
      title: 'Body',
      items: [
        { href: '/weight', label: 'Weight', Icon: ScaleIcon },
        { href: '/sober', label: 'Sober', Icon: CalendarIcon },
      ],
    },
    {
      title: 'Train tools',
      items: [
        { href: '/schedule-change', label: 'Change plan', Icon: AlertIcon },
        { href: '/training/preferences', label: 'Preferences', Icon: SlidersIcon },
        { href: '/training/exercises', label: 'Exercises', Icon: DumbbellIcon },
      ],
    },
  ]
}

export function PhoneChrome() {
  const [open, setOpen] = useState(false)
  const titleId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const current = path()
  const scrolledAway = useScrollHide()
  const hidden = scrolledAway && !open

  useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <>
      <header className={`phone-chrome${hidden ? ' is-hidden' : ''}`}>
        <button type="button" className="phone-chrome-btn" onClick={goBack} aria-label="Back">
          <ChevronBackIcon size={22} />
          <span>Back</span>
        </button>
        <a className="phone-chrome-brand" href={`/daily/${todayStamp()}`}>
          <img src={chiliLogo} alt="" />
          Chili
        </a>
        <button
          type="button"
          className="phone-chrome-btn phone-chrome-menu-btn"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls={open ? titleId : undefined}
        >
          <MenuIcon size={22} />
        </button>
      </header>

      {open && (
        <div className="phone-menu" role="presentation">
          <button
            type="button"
            className="phone-menu-backdrop"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
          />
          <div
            className="phone-menu-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
          >
            <div className="phone-menu-head">
              <h2 id={titleId}>Menu</h2>
              <button
                ref={closeRef}
                type="button"
                className="phone-chrome-btn"
                onClick={() => setOpen(false)}
                aria-label="Close menu"
              >
                Close
              </button>
            </div>
            <nav className="phone-menu-nav" aria-label="Phone destinations">
              {menuSections().map((section) => (
                <div key={section.title} className="phone-menu-section">
                  <p className="phone-menu-section-title">{section.title}</p>
                  <ul>
                    {section.items.map(({ href, label, Icon }) => {
                      const active = isActive(href, current)
                      return (
                        <li key={`${section.title}-${href}-${label}`}>
                          <a
                            href={href}
                            className={`phone-menu-link${active ? ' is-active' : ''}`}
                            aria-current={active ? 'page' : undefined}
                            onClick={() => setOpen(false)}
                          >
                            <Icon size={18} />
                            <span>{label}</span>
                          </a>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              ))}
            </nav>
          </div>
        </div>
      )}
    </>
  )
}
