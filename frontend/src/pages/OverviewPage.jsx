import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Shell } from '../components/Shell';
import { Card, MetricCard, Tag } from '../components/ui';
import { CorrelationGrid, PerformanceChart, RiskBars, Treemap, money, pct } from '../components/charts';
import { api } from '../lib/api';
import { useAsOf } from '../lib/useAsOf';

const SEVERITY_TONE = { Storm: 'red', Choppy: 'yellow', 'Heads-up': 'blue', Calm: 'grey' };

/** The one sentence that explains today, built from the numbers we have.
 *  Says both things a person wants to know: how big the move was in plain
 *  terms, and whether that is unusual for this particular portfolio. */
function seaSentence(d) {
  const move = Math.abs(d.day_change_pct ?? 0);
  const sds = Math.abs(d.day_move_in_sds ?? 0);
  const dir = (d.day_change_pct ?? 0) < 0 ? 'fell' : 'rose';
  const scale =
    sds >= 1.15 ? `about ${sds.toFixed(1)}× a normal day's swing` : 'within its usual daily range';

  if (d.sea_state === 'Calm') {
    return `Your portfolio ${dir} ${move.toFixed(1)}% — an ordinary day for this mix.`;
  }
  return `Your portfolio ${dir} ${move.toFixed(1)}%, ${scale}.`;
}

export default function OverviewPage() {
  const navigate = useNavigate();
  const { asOf } = useAsOf();
  const [data, setData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [state, setState] = useState('loading');   // loading | ready | empty | error
  const [message, setMessage] = useState('');
  // the written paragraph arrives after the page, so it lives apart from
  // the rest of the overview data
  const [read, setRead] = useState(null);
  const [writing, setWriting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    api
      .overview(asOf)
      .then((d) => {
        if (cancelled) return;
        if (d.empty) {
          setState('empty');
          return;
        }
        setData(d);
        setState('ready');
        setRead(d.read ?? null);
        // no cached paragraph: ask for one in the background. Loading a
        // model takes a while, and the page must not wait for it.
        if (!d.read) {
          setWriting(true);
          api
            .generateRead(asOf)
            .then((r) => !cancelled && setRead(r.read ?? null))
            .catch(() => {})
            .finally(() => !cancelled && setWriting(false));
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setMessage(err.message);
        setState('error');
      });
    api.alerts(asOf).then((d) => !cancelled && setAlerts(d.alerts ?? [])).catch(() => setAlerts([]));
    return () => {
      cancelled = true;
    };
  }, [asOf]);

  if (state === 'loading') {
    return (
      <Shell title="Overview">
        <div className="page-state">Reading your portfolio…</div>
      </Shell>
    );
  }

  if (state === 'error') {
    return (
      <Shell title="Overview">
        <div className="page-state error">
          <b>Couldn't load your overview.</b>
          <span>{message}</span>
          <span className="hint">Is the backend running on port 5000?</span>
        </div>
      </Shell>
    );
  }

  if (state === 'empty') {
    return (
      <Shell title="Overview">
        <div className="page-state">
          <b>No holdings yet.</b>
          <span>Add what you own and Lookout will start watching it.</span>
          <button className="sign-btn" type="button" onClick={() => navigate('/onboarding')}>
            Add holdings →
          </button>
        </div>
      </Shell>
    );
  }

  const behind = (data.return_pct ?? 0) < (data.market_return_pct ?? 0);
  const volRatio = data.market_volatility_pct
    ? (data.volatility_pct / data.market_volatility_pct).toFixed(1)
    : null;
  const top = alerts.slice(0, 3);

  // the largest gap between risk share and money share: the headline insight
  const gaps = Object.keys(data.weights ?? {})
    .map((t) => ({ t, gap: (data.risk_share?.[t] ?? 0) - data.weights[t] }))
    .sort((a, b) => b.gap - a.gap);
  const riskiest = gaps[0];

  return (
    <Shell title="Overview">
      <div className="overview-grid top-grid">
        <Card dark className="sea-card">
          <div className="eyebrow accent">SEA STATE {asOf ? 'THAT DAY' : 'TODAY'}</div>
          <div className="storm-row">
            <div className="storm-word">{data.sea_state}</div>
            <div className={`storm-loss ${data.day_change_pct < 0 ? '' : 'up'}`}>
              {pct(data.day_change_pct)}
            </div>
          </div>
          <p>{read?.read ?? seaSentence(data)}</p>
          {read?.headline && <div className="read-headline">{read.headline}</div>}
          {writing && <div className="read-writing">Lookout is writing today's read…</div>}
          <div className="sea-scale">
            <span>Calm</span>
            <span>Choppy</span>
            <span>Stormy</span>
          </div>
          <div className="sea-bars">
            {['Calm', 'Choppy', 'Stormy'].map((s) => (
              <i key={s} className={data.sea_state === s ? 'here' : ''} />
            ))}
          </div>
          <svg className="sea-illustration" viewBox="0 0 400 170" aria-hidden="true">
            <path d="M0 112 C32 78 58 150 97 105 S165 147 205 95 S260 133 296 75 S353 133 400 89 V170 H0Z" fill="#1f6b8f" />
            <path d="M0 126 C39 96 63 153 109 123 S180 151 222 111 S287 150 330 105 S364 129 400 109 V170 H0Z" fill="#3596be" />
            <path d="M198 59l37 8-27 15z" fill="#f3b336" />
            <path d="M216 44v20l18 3z" fill="#f4efe2" />
          </svg>
        </Card>

        <Card className="needs-card">
          <div className="card-title-row">
            <h2>{top.length ? `${top.length} ${top.length === 1 ? 'thing needs' : 'things need'} a look` : 'Nothing needs a look'}</h2>
            <Link className="text-link" to={`/signals${asOf ? `?as_of=${asOf}` : ''}`}>
              {alerts.length ? `See all ${alerts.length} signals →` : 'Open signal log →'}
            </Link>
          </div>

          {top.length === 0 && (
            <div className="chart-empty tall">
              No alerts for this day. Run <code>flask alerts</code> to generate them, or pick a
              different date.
            </div>
          )}

          {top.map((a) => (
            <div className="need-row" key={a.id}>
              <div>
                <Tag tone={SEVERITY_TONE[a.severity] ?? 'grey'}>{a.severity}</Tag>
                <div className="mini-source">{a.category}</div>
              </div>
              <div className="need-copy">
                <b>{a.title}</b>
                <span>{a.why}</span>
              </div>
              <strong>{a.ticker}</strong>
            </div>
          ))}
        </Card>
      </div>

      <div className="metrics-row">
        <MetricCard
          label="PORTFOLIO VALUE"
          value={money(data.value)}
          detail={`${pct(data.day_change_pct)} today`}
          foot={`What your holdings are worth at the ${asOf ? 'close that day' : 'latest close'}.`}
          danger={data.day_change_pct < 0}
        />
        <MetricCard
          label="1-YEAR RETURN"
          value={pct(data.return_pct)}
          detail={`Market: ${pct(data.market_return_pct)}`}
          foot={behind ? 'Behind the market over this stretch.' : 'Ahead of the market over this stretch.'}
        />
        <MetricCard
          label="VOLATILITY"
          value={`${data.volatility_pct?.toFixed(0)}%`}
          detail={`Market: ${data.market_volatility_pct?.toFixed(0)}%`}
          foot={volRatio ? `About ${volRatio}× as bumpy as the market.` : 'How much your value swings.'}
        />
        <MetricCard
          label="WORST DROP"
          value={`${data.max_drawdown_pct?.toFixed(1)}%`}
          detail="Peak to bottom, past year"
          foot="The deepest dip you would have sat through."
          danger
        />
        <MetricCard
          label="BETA"
          value={data.beta?.toFixed(2) ?? '—'}
          detail="Market = 1.00"
          foot={
            data.beta
              ? `When the market moves 1%, you tend to move about ${data.beta.toFixed(1)}%.`
              : 'Needs more history to measure.'
          }
        />
      </div>

      <div className="overview-grid chart-grid">
        <Card className="voyage-card">
          <div className="card-title-row">
            <div>
              <h2>The voyage so far</h2>
              <p className="muted">Your portfolio against the market, both starting from zero.</p>
            </div>
          </div>
          <div className="legend-row">
            <b>You {pct(data.return_pct)}</b>
            <span className="dash-legend">Market {pct(data.market_return_pct)}</span>
            <span className="pin-legend earnings">E Earnings</span>
            <span className="pin-legend alert">! Lookout alert</span>
          </div>
          <PerformanceChart series={data.series} pins={data.pins} />
        </Card>

        <Card className="hold-card">
          <h2>What's in the hold</h2>
          <p className="muted">How your money is split. Bigger box, bigger share.</p>
          <Treemap weights={data.weights} />
          <div className="callout">
            {(() => {
              const biggest = Object.entries(data.weights ?? {}).sort((a, b) => b[1] - a[1])[0];
              return biggest
                ? `${biggest[0]} is your largest position at ${biggest[1].toFixed(0)}% of the portfolio.`
                : 'Add holdings to see how your money is split.';
            })()}
          </div>
        </Card>
      </div>

      <div className="overview-grid bottom-grid">
        <Card>
          <h2>Who's rocking the boat</h2>
          <p className="muted">
            How much of your money sits in each stock, next to how much of your portfolio's
            bumpiness it causes.
          </p>
          <RiskBars weights={data.weights} riskShare={data.risk_share} />
          {riskiest && riskiest.gap > 3 && (
            <div className="callout peach">
              <b>{riskiest.t}</b> is {data.weights[riskiest.t].toFixed(0)}% of your money but{' '}
              {data.risk_share[riskiest.t].toFixed(0)}% of the bumpiness.
            </div>
          )}
        </Card>

        <Card>
          <h2>Who sails together</h2>
          <p className="muted">
            Close to 1 means two stocks move in lockstep. Near zero means they go their own way,
            which is what protects you.
          </p>
          <CorrelationGrid correlation={data.correlation} />
        </Card>
      </div>
    </Shell>
  );
}