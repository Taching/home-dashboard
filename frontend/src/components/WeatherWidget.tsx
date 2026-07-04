import type { WeatherDay, WeatherForecast, WeatherIcon } from '../types'

type IconProps = {
  icon: WeatherIcon
  size?: 'lg' | 'sm'
}

export function WeatherIconArt({ icon, size = 'lg' }: IconProps) {
  const className = `weather-icon is-${icon} is-${size}`
  return (
    <span className={className} aria-hidden="true">
      {icon === 'sunny' && (
        <svg viewBox="0 0 64 64">
          <circle className="weather-sun-core" cx="32" cy="32" r="12" />
          {Array.from({ length: 8 }).map((_, index) => (
            <line
              key={index}
              className="weather-sun-ray"
              x1="32"
              y1="8"
              x2="32"
              y2="14"
              transform={`rotate(${index * 45} 32 32)`}
            />
          ))}
        </svg>
      )}
      {icon === 'evening' && (
        <svg viewBox="0 0 64 64">
          <circle className="weather-moon" cx="38" cy="28" r="11" />
          <circle className="weather-moon-cut" cx="43" cy="24" r="9" />
          <circle className="weather-star" cx="18" cy="18" r="1.4" />
          <circle className="weather-star is-delayed" cx="24" cy="12" r="1" />
          <circle className="weather-star is-slow" cx="14" cy="28" r="1.1" />
        </svg>
      )}
      {icon === 'rain' && (
        <svg viewBox="0 0 64 64">
          <path className="weather-cloud" d="M18 36c0-8 6-14 14-14 2 0 4 .4 5.8 1.2 2.3-3.4 6.2-5.7 10.7-5.7 7 0 12.7 5.7 12.7 12.7 0 .8-.1 1.6-.2 2.3H48c4.4 0 8 3.6 8 8s-3.6 8-8 8H22c-4.4 0-8-3.6-8-8 0-3.7 2.5-6.8 6-7.7z" />
          <path className="weather-rainbow" d="M16 34a18 18 0 0 1 32 0" stroke="#ff8f8f" />
          <path className="weather-rainbow is-inner" d="M20 34a14 14 0 0 1 24 0" stroke="#ffd86b" />
          <path className="weather-rainbow is-inner" d="M24 34a10 10 0 0 1 16 0" stroke="#79e6bd" />
          <line className="weather-rain-drop" x1="24" y1="44" x2="21" y2="52" />
          <line className="weather-rain-drop is-delayed" x1="34" y1="44" x2="31" y2="53" />
          <line className="weather-rain-drop is-slow" x1="44" y1="44" x2="41" y2="52" />
          <path className="weather-umbrella" d="M32 54v8M18 54c0-7.7 6.3-14 14-14s14 6.3 14 14" />
        </svg>
      )}
      {icon === 'cloudy' && (
        <svg viewBox="0 0 64 64">
          <path className="weather-cloud" d="M16 38c0-8 6-14 14-14 2 0 4 .4 5.8 1.2 2.3-3.4 6.2-5.7 10.7-5.7 7 0 12.7 5.7 12.7 12.7 0 .8-.1 1.6-.2 2.3H46c4.4 0 8 3.6 8 8s-3.6 8-8 8H20c-4.4 0-8-3.6-8-8 0-3.7 2.5-6.8 6-7.7z" />
        </svg>
      )}
      {icon === 'fog' && (
        <svg viewBox="0 0 64 64">
          <path className="weather-cloud is-soft" d="M14 28c0-6 5-11 11-11 1.6 0 3.1.3 4.5 1 1.8-2.6 4.8-4.3 8.2-4.3 5.4 0 9.8 4.4 9.8 9.8 0 .6-.1 1.2-.2 1.8H44c3.4 0 6.2 2.8 6.2 6.2S47.4 38 44 38H18c-3.4 0-6.2-2.8-6.2-6.2 0-2.9 2-5.3 4.7-6.1z" />
          <line className="weather-fog-line" x1="12" y1="44" x2="52" y2="44" />
          <line className="weather-fog-line is-delayed" x1="18" y1="50" x2="46" y2="50" />
        </svg>
      )}
      {icon === 'snow' && (
        <svg viewBox="0 0 64 64">
          <path className="weather-cloud" d="M18 34c0-8 6-14 14-14 2 0 4 .4 5.8 1.2 2.3-3.4 6.2-5.7 10.7-5.7 7 0 12.7 5.7 12.7 12.7 0 .8-.1 1.6-.2 2.3H48c4.4 0 8 3.6 8 8s-3.6 8-8 8H22c-4.4 0-8-3.6-8-8 0-3.7 2.5-6.8 6-7.7z" />
          <circle className="weather-snowflake" cx="24" cy="48" r="2" />
          <circle className="weather-snowflake is-delayed" cx="34" cy="52" r="1.6" />
          <circle className="weather-snowflake is-slow" cx="44" cy="47" r="1.8" />
        </svg>
      )}
      {icon === 'storm' && (
        <svg viewBox="0 0 64 64">
          <path className="weather-cloud is-dark" d="M18 34c0-8 6-14 14-14 2 0 4 .4 5.8 1.2 2.3-3.4 6.2-5.7 10.7-5.7 7 0 12.7 5.7 12.7 12.7 0 .8-.1 1.6-.2 2.3H48c4.4 0 8 3.6 8 8s-3.6 8-8 8H22c-4.4 0-8-3.6-8-8 0-3.7 2.5-6.8 6-7.7z" />
          <path className="weather-bolt" d="M34 42 28 52h6l-4 10 12-14h-6l4-6z" />
        </svg>
      )}
    </span>
  )
}

function formatHighLow(day: WeatherDay) {
  return `${Math.round(day.high_c)}° / ${Math.round(day.low_c)}°`
}

type Props = {
  forecast: WeatherForecast
}

function WeatherDayCard({ day, emphasis }: { day: WeatherDay; emphasis: 'today' | 'tomorrow' }) {
  const outdoor = day.current_c !== undefined && day.current_c !== null
    ? `${day.current_c.toFixed(1)}° now`
    : formatHighLow(day)

  return (
    <div className={`weather-day is-${emphasis}`}>
      <WeatherIconArt icon={day.icon} size={emphasis === 'today' ? 'lg' : 'sm'} />
      <div className="weather-day-copy">
        <span className="weather-day-label">{day.label}</span>
        <strong className="weather-day-temp">{emphasis === 'today' ? outdoor : formatHighLow(day)}</strong>
        <span className="weather-day-condition">{day.condition}</span>
      </div>
    </div>
  )
}

export function WeatherWidget({ forecast }: Props) {
  if (forecast.status !== 'ready' || !forecast.today) {
    return null
  }

  return (
    <section className="weather-widget" aria-label={`Weather for ${forecast.location}`}>
      <WeatherDayCard day={forecast.today} emphasis="today" />
      {forecast.tomorrow && <WeatherDayCard day={forecast.tomorrow} emphasis="tomorrow" />}
    </section>
  )
}
