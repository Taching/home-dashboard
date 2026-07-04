type Props = {
  feedback: string | null
}

export function SystemStrip({ feedback }: Props) {
  if (!feedback) return null

  return (
    <section className="system-strip" aria-label="System status">
      <p className="command-feedback" aria-live="polite">{feedback}</p>
    </section>
  )
}
