type Props = {
  className?: string
}

export function SpotifyDjIcon({ className = '' }: Props) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="10.25" fill="var(--bg-sunken)" stroke="var(--spotify)" strokeWidth="1.1" opacity=".9" />
      <path d="M6.2 16.1c3.4-1.1 8.2-1.1 11.6 0" stroke="var(--spotify)" strokeWidth="1.85" strokeLinecap="round" />
      <path d="M7.8 12.4c2.7-.8 5.7-.8 8.4 0" stroke="var(--spotify)" strokeWidth="1.85" strokeLinecap="round" />
      <path d="M9.4 8.8c1.9-.5 4.3-.5 6.2 0" stroke="var(--spotify)" strokeWidth="1.85" strokeLinecap="round" />
    </svg>
  )
}
