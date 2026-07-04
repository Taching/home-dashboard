import { useState } from 'react'
import { sendCommand } from '../lib/api'
import type { CommandIntent, CommandResult } from '../types'

type ExecuteOptions = {
  optimistic?: () => void
  onSuccess?: (result: CommandResult) => void
  onFailure?: () => void
}

export function useDashboardCommand() {
  const [pendingIntent, setPendingIntent] = useState<CommandIntent | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)

  async function execute(intent: CommandIntent, options: ExecuteOptions = {}) {
    if (pendingIntent) return
    options.optimistic?.()
    setPendingIntent(intent)
    setFeedback('Sending…')

    try {
      const result = await sendCommand(intent)
      if (result.status === 'success') options.onSuccess?.(result)
      else options.onFailure?.()
      setFeedback(result.message ?? (result.status === 'success' ? 'Done.' : result.status === 'skipped' ? 'Already running.' : 'Command failed.'))
      return result
    } catch {
      options.onFailure?.()
      setFeedback('The dashboard could not send that command.')
      return null
    } finally {
      setPendingIntent(null)
    }
  }

  return { execute, feedback, pendingIntent }
}
