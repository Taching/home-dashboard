import clearDay from '@meteocons/svg-static/fill/clear-day.svg'
import clearNight from '@meteocons/svg-static/fill/clear-night.svg'
import cloudy from '@meteocons/svg-static/fill/overcast.svg'
import fog from '@meteocons/svg-static/fill/fog.svg'
import rain from '@meteocons/svg-static/fill/rain.svg'
import snow from '@meteocons/svg-static/fill/snow.svg'
import storm from '@meteocons/svg-static/fill/thunderstorms.svg'
import type { WeatherDay, WeatherForecast, WeatherIcon } from '../types'

const WEATHER_ICONS: Record<WeatherIcon, string> = {
  sunny: clearDay,
  evening: clearNight,
  cloudy,
  fog,
  rain,
  snow,
  storm,
}

export function WeatherIconArt({ icon, size = 42 }: { icon: WeatherIcon; size?: number }) {
  return (
    <img
      className="weather-icon"
      src={WEATHER_ICONS[icon]}
      alt=""
      width={size}
      height={size}
    />
  )
}

function formatHighLow(day: WeatherDay) {
  return `${Math.round(day.high_c)}° / ${Math.round(day.low_c)}°`
}

function WeatherDayCard({ day, showCurrent = false }: { day: WeatherDay; showCurrent?: boolean }) {
  const current = day.current_c
  const useCurrent = showCurrent && current != null
  const degrees = useCurrent && current != null ? Math.round(current) : Math.round(day.high_c)
  const spoken = useCurrent && current != null ? `${current.toFixed(1)}° now` : formatHighLow(day)

  return (
    <div className="weather-day" aria-label={`${day.label}: ${spoken}, ${day.condition}.`}>
      <WeatherIconArt icon={day.icon} />
      <div className="weather-day-copy">
        <span className="weather-day-label">{day.label}</span>
        <strong className="weather-day-temp">{degrees}<small>°</small></strong>
        <span className="weather-day-condition">{day.condition}</span>
      </div>
    </div>
  )
}

export function WeatherWidget({ forecast }: { forecast: WeatherForecast }) {
  if (forecast.status !== 'ready' || !forecast.today) {
    return null
  }

  return (
    <section className="header-weather" aria-label={`Weather for ${forecast.location}`}>
      <WeatherDayCard day={forecast.today} showCurrent />
      {forecast.tomorrow ? <WeatherDayCard day={forecast.tomorrow} /> : null}
    </section>
  )
}
