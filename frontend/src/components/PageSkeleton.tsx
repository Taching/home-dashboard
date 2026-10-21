import { PhoneChrome } from './PhoneChrome'

export function PageSkeleton() {
  return (
    <main className="workout-page page-skeleton" aria-label="Loading page" aria-busy="true">
      <PhoneChrome />
      <section className="workout-hero">
        <span className="skeleton-block is-kicker" />
        <span className="skeleton-block is-title" />
        <span className="skeleton-block is-copy" />
      </section>
      <section className="workout-section">
        <span className="skeleton-block is-heading" />
        <span className="skeleton-block is-row" />
        <span className="skeleton-block is-row" />
        <span className="skeleton-block is-row short" />
      </section>
    </main>
  )
}
