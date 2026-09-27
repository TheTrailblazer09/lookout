import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shell } from '../components/Shell';
import { Card, Tag } from '../components/ui';
import { api } from '../lib/api';
import { useAsOf } from '../lib/useAsOf';

const LEVEL_TONE = { High: 'red', Medium: 'yellow', Low: 'blue', Unknown: 'grey' };

/** A tiny line, drawn from the indicator's own history. */
function Spark({ points }) {
  if (!points || points.length < 3) return <div className="spark-empty" />;
  const lo = Math.min(...points);
  const hi = Math.max(...points);
  const span = hi - lo || 1;
  const d = points
    .map((v, i) => `${i ? 'L' : 'M'}${(i / (points.length - 1)) * 100} ${46 - ((v - lo) / span) * 40}`)
    .join(' ');
  const rising = points[points.length - 1] >= points[0];
  return (
    <svg className="spark" viewBox="0 0 100 50" preserveAspectRatio="none">
      <path d={`${d} L100 50 L0 50 Z`} fill={rising ? '#1F6F99' : '#E0561F'} fillOpacity="0.08" />
      <path d={d} fill="none" stroke={rising ? '#1F6F99' : '#E0561F'} strokeWidth="2" />
    </svg>
  );
}

function fmtDate(iso) {
  const d = new Date(`${iso}T12:00:00`);
  return {
    dow: d.toLocaleDateString(undefined, { weekday: 'short' }).toUpperCase(),
    day: d.getDate(),
    mon: d.toLocaleDateString(undefined, { month: 'short' }).toUpperCase(),
  };
}

export default function WeatherPage() {
  const navigate = useNavigate();
  const { asOf } = useAsOf();
  const [data, setData] = useState(null);
  const [state, setState] = useState('loading');
  const [forecast, setForecast] = useState(null);
  const [writing, setWriting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    api
      .weather(asOf)
      .then((d) => {
        if (cancelled) return;
        if (d.empty) {
          setState('empty');
          return;
        }
        setData(d);
        setForecast(d.forecast ?? null);
        setState('ready');
        if (!d.forecast) {
          // written in the background, like the overview read
          setWriting(true);
          api
            .weatherForecast(asOf)
            .then((r) => !cancelled && setForecast(r.forecast ?? null))
            .catch(() => {})
            .finally(() => !cancelled && setWriting(false));
        }
      })
      .catch(() => !cancelled && setState('error'));
    return () => {
      cancelled = true;
    };
  }, [asOf]);

  if (state === 'loading') {
    return (
      <Shell title="Weather report">
        <div className="page-state">Reading the conditions…</div>
      </Shell>
    );
  }
  if (state === 'error') {
    return (
      <Shell title="Weather report">
        <div className="page-state error">
          <b>Couldn't load the weather.</b>
          <span>Check that the backend is running.</span>
        </div>
      </Shell>
    );
  }
  if (state === 'empty') {
    return (
      <Shell title="Weather report">
        <div className="page-state">
          <b>No holdings yet.</b>
          <span>Add what you own to see which forces push it around.</span>
          <button className="sign-btn" type="button" onClick={() => navigate('/onboarding')}>
            Add holdings →
          </button>
        </div>
      </Shell>
    );
  }

  const strongest = data.exposure.find((e) => e.ratio) ?? null;

  return (
    <Shell
      title="Weather report"
      subtitle="The big forces that push all your stocks at once, and how hard they push yours."
    >
      <div className="weather-top">
        <Card dark className="forecast-card">
          <div className="eyebrow accent">TODAY'S FORECAST</div>
          <h2>
            {forecast?.headline ??
              (strongest
                ? `${strongest.label} matter most to you`
                : 'Not enough history yet')}
          </h2>
          <p>
            {forecast?.forecast ??
              (strongest
                ? strongest.why
                : 'Lookout needs more measured events before it can read the conditions for your mix.')}
          </p>
          {writing && <div className="read-writing">Lookout is writing the forecast…</div>}
        </Card>

        <Card className="exposure-card">
          <h2>How exposed are you?</h2>
          <p className="muted">
            Measured from how your holdings actually reacted to these events in the past, not
            from what the news says.
          </p>
          <div className="exposure">
            {data.exposure.map((e) => (
              <div className="exposure-row-live" key={e.type}>
                <div className="exp-name">
                  <b>{e.label}</b>
                  <span>{e.plain}</span>
                </div>
                <div className="exposure-meter">
                  {[1, 2, 3].map((i) => (
                    <i key={i} className={i <= e.score ? `on level-${e.score}` : ''} />
                  ))}
                  <Tag tone={LEVEL_TONE[e.level]}>{e.level}</Tag>
                </div>
                <p>{e.why}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="weather-bottom">
        <Card className="tide-card">
          <h2>Tide table</h2>
          <p className="muted">What's scheduled, and how much it has mattered to you before.</p>
          {data.upcoming.length === 0 && (
            <div className="chart-empty">Nothing scheduled in the next few weeks.</div>
          )}
          {data.upcoming.map((e) => {
            const d = fmtDate(e.date);
            return (
              <div className="event-row" key={`${e.date}-${e.type}-${e.ticker ?? ''}`}>
                <div className="date-chip">
                  <b>{d.dow}</b>
                  <strong>{d.day}</strong>
                  <span>{d.mon}</span>
                </div>
                <div>
                  <div className="event-title">
                    <b>{e.title}</b>
                    <Tag tone={LEVEL_TONE[e.level]}>{e.level} impact</Tag>
                  </div>
                  <p>{e.why}</p>
                </div>
              </div>
            );
          })}
        </Card>

        <div className="macro-grid">
          {data.indicators.length === 0 && (
            <Card>
              <div className="chart-empty">
                No macro readings stored yet. Run <code>flask ingest</code> with a FRED key.
              </div>
            </Card>
          )}
          {data.indicators.map((i) => (
            <Card key={i.series_id} className="macro-card">
              <div className="eyebrow">{i.label.toUpperCase()}</div>
              <div className="macro-value">
                <b>{i.value.toLocaleString()}</b>
                {i.change !== null && (
                  <span className={i.change < 0 ? 'danger-text' : ''}>
                    {i.change > 0 ? '+' : ''}
                    {i.change}
                  </span>
                )}
              </div>
              <Spark points={i.history} />
              <span className="macro-date">as of {i.as_of_date}</span>
            </Card>
          ))}
        </div>
      </div>
    </Shell>
  );
}