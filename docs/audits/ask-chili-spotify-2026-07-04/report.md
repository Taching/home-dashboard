# Ask Chili And Spotify Panel Audit

Date: 2026-07-04
Viewport: 1366 x 768 desktop
Source: `http://127.0.0.1:8080`

## Evidence

1. `01-dashboard-desktop.png` - full dashboard screenshot.
2. `02-ask-chili-panel.png` - Ask Chili panel crop.
3. `03-spotify-panel.png` - Spotify panel crop.

## Steps

1. Dashboard overview - usable but right rail feels visually underpowered.
   - Evidence: `01-dashboard-desktop.png`
   - The dashboard has a clear three-column structure and the right rail is easy to locate.
   - The assistant and media areas have much lower visual weight than schedule/tasks, so they read as secondary status text rather than active tools.
   - The right rail uses large vertical empty space. This makes both panels feel small even though the column itself has room to support richer controls or stronger empty states.

2. Ask Chili setup state - clear label, weak action path.
   - Evidence: `02-ask-chili-panel.png`
   - Strength: the panel title is direct and the status text tells the user setup is needed.
   - UX issue: the empty/setup state is informational only. There is no visible next action, command, link, or connection status detail, so a user cannot recover from this panel.
   - UX issue: the body text is small and sits close to the heading, which makes the panel feel like a note rather than a primary assistant surface.
   - Accessibility risk: the status uses small, low-contrast muted text. Screenshot-only review cannot verify exact contrast ratios, but visually it is close to the background color and may be hard to read on the Pi display.
   - Recommendation: keep the existing compact dashboard style, but give the setup state one clear action such as "Open setup" or "Check OpenClaw connection", plus a short secondary detail about Telegram/OpenClaw status.

3. Spotify setup state - recognizable but sparse.
   - Evidence: `03-spotify-panel.png`
   - Strength: the Spotify heading and "Connect Spotify" action are clear.
   - UX issue: the artwork placeholder dominates the panel, while the action is separated below it. The panel does not explain whether Spotify is disconnected, unavailable, or simply idle.
   - UX issue: the panel is centered but not balanced with the Ask Chili area above; it feels like a small widget floating inside a much larger right rail.
   - Accessibility risk: the music-note placeholder communicates state visually only. The link text helps, but the screenshot cannot confirm focus order or keyboard behavior.
   - Recommendation: add a one-line setup/status sentence near the connect action, and consider using the panel space for the last-known track or a clearer empty-state control when no track is active.

## Cross-Panel Findings

1. The right rail lacks a strong hierarchy.
   - Ask Chili and Spotify are both important integrations, but their current visual treatment is closer to passive metadata.
   - A better direction would be to keep the calm dashboard density, while giving each panel a clearer container, status row, and obvious recovery/action area.

2. Empty states need action, not just explanation.
   - Ask Chili says setup is needed but does not expose what to do next.
   - Spotify has an action but no context around the connection state.

3. The panels should handle connected states separately from setup states.
   - The current audit captured setup states only.
   - Before redesigning the final UI, capture and compare: OpenClaw ready with messages, OpenClaw unavailable, Spotify connected but idle, and Spotify actively playing.

## Limits

- This audit used screenshots only, so it does not verify keyboard navigation, screen reader announcements, focus order, or exact color contrast.
- The captured dashboard showed OpenClaw as `Setup needed` and Spotify as `Connect Spotify`; connected and playing states were not visible in this audit run.
- The screenshot was captured at desktop size only. Mobile/right-rail stacked behavior still needs a separate capture pass.
