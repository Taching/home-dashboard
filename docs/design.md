# Dashboard visual direction

## Visual thesis

Quiet, low-light operational display: a deep green-black surface, oversized environmental readings, and just enough status information to be understood from across the room.

## Content plan

1. **Orientation** — product name and the last time data was updated.
2. **Primary workspace** — temperature and humidity, at the largest scale.
3. **Secondary context** — light, sensor, and BroadLink health in one restrained status row.
4. **Operational hint** — available keyboard fallbacks.

The history chart and manual control affordances arrive after live hardware data exists; they are not represented with invented data in the initial UI.

## Interaction thesis

1. Current values update with a brief numeric crossfade when a fresh sensor reading arrives.
2. Light state changes use a short accent-color transition, not a modal or toast.
3. Screen blanking fades the dashboard out while leaving the application and voice service active.

Motion remains optional and respects `prefers-reduced-motion`.

