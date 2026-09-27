import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shell } from '../components/Shell';
import { Card, Tag } from '../components/ui';
import { api } from '../lib/api';
import { useAsOf } from '../lib/useAsOf';

/** Price with its two moving averages, and numbered pins for real events.
 *  The numbers matter: a chart of ten identical "!" markers tells you
 *  nothing without hovering each one, so every pin is keyed to a list
 *  underneath that says what it was. */
function StockChart({ series, pins, active, onHover }) {
  if (!series?.length) return <div className="chart-empty">No price history.</div>;

  const W = 760;
  const H = 300;
  const pad = { l: 48, r: 14, t: 14, b: 26 };
  const values = series.flatMap((p) => [p.close, p.ma50, p.ma200]).filter((v) => v != null);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  const step = Math.pow(10, Math.floor(Math.log10((hi - lo) / 4 || 1)));
  const tick = Math.ceil((hi - lo) / 4 / step) * step;
  lo = Math.floor(lo / tick) * tick;
  hi = Math.ceil(hi / tick) * tick;

  const x = (i) => pad.l + (i / (series.length - 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);
  const line = (key) =>
    series
      .map((p, i) => (p[key] == null ? null : `${x(i).toFixed(1)} ${y(p[key]).toFixed(1)}`))
      .filter(Boolean)
      .map((pt, i) => `${i ? 'L' : 'M'}${pt}`)
      .join(' ');

  const ticks = [];
  for (let v = lo; v <= hi + 0.001; v += tick) ticks.push(v);

  const byDate = new Map(series.map((p, i) => [p.date, i]));
  const placed = (pins ?? [])
    .map((pin, n) => {
      const i = byDate.get(pin.date);
      if (i == null) return null;
      return { ...pin, n: n + 1, cx: x(i), cy: y(series[i].close) };
    })
    .filter(Boolean);

  const labels = [0, Math.floor(series.length / 2), series.length - 1];
  const hovered = placed.find((p) => p.n === active);

  return (
    <svg className="stock-chart-live" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Price history">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="#E4DCCB" />
          <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#5A6272"
                fontFamily="JetBrains Mono, monospace">
            ${v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)}
          </text>
        </g>
      ))}
      <path d={line('ma200')} fill="none" stroke="#C9B9A0" strokeWidth="2" strokeDasharray="6 5" />
      <path d={line('ma50')} fill="none" stroke="#E0561F" strokeWidth="2" />
      <path d={line('close')} fill="none" stroke="#1F6F99" strokeWidth="2.5" strokeLinejoin="round" />

      {placed.map((pin) => {
        const on = pin.n === active;
        return (
          <g key={`${pin.date}-${pin.n}`} className="chart-pin"
             onMouseEnter={() => onHover(pin.n)} onMouseLeave={() => onHover(null)}>
            <circle cx={pin.cx} cy={pin.cy} r={on ? 11 : 9}
                    fill={pin.kind === 'E' ? '#FFFDF8' : '#F2B33D'}
                    stroke="#16243A" strokeWidth={on ? 3 : 2} />
            <text x={pin.cx} y={pin.cy + 4} textAnchor="middle" fontSize="10" fontWeight="700"
                  fill="#16243A" fontFamily="JetBrains Mono, monospace" pointerEvents="none">
              {pin.n}
            </text>
          </g>
        );
      })}

      {/* The hovered pin's label in full. SVG text does not wrap, so the
          label is split into lines here and the box is sized to fit them,
          then flipped to whichever side has room. */}
      {hovered && (() => {
        const words = `${hovered.date} · ${hovered.label}`.split(' ');
        const MAX = 42;                 // characters per line
        const lines = [];
        words.forEach((w) => {
          const last = lines[lines.length - 1];
          if (last && (`${last} ${w}`).length <= MAX) lines[lines.length - 1] = `${last} ${w}`;
          else lines.push(w);
        });

        const LINE = 15;
        const w = Math.min(340, Math.max(...lines.map((l) => l.length)) * 6.3 + 20);
        const h = lines.length * LINE + 14;
        const flip = hovered.cx + w + 16 > W;
        const bx = flip ? Math.max(2, hovered.cx - w - 16) : hovered.cx + 16;
        const by = Math.max(pad.t, Math.min(hovered.cy - h / 2, H - pad.b - h));

        return (
          <g pointerEvents="none">
            <rect x={bx} y={by} width={w} height={h} rx="6" fill="#16243A" opacity="0.97" />
            {lines.map((line, i) => (
              <text key={line + i} x={bx + 10} y={by + 18 + i * LINE} fontSize="12" fill="#F3EEE3">
                {line}
              </text>
            ))}
          </g>
        );
      })()}

      {labels.map((i) => (
        <text key={i} x={x(i)} y={H - 6}
              textAnchor={i === 0 ? 'start' : i === series.length - 1 ? 'end' : 'middle'}
              fontSize="11" fill="#5A6272" fontFamily="JetBrains Mono, monospace">
          {series[i].date.slice(0, 7)}
        </text>
      ))}
    </svg>
  );
}

/** What each numbered pin was. */
function PinLegend({ pins, active, onHover }) {
  if (!pins?.length) return null;
  return (
    <div className="pin-legend-list">
      {pins.map((pin, i) => (
        <button
          key={`${pin.date}-${i}`}
          type="button"
          className={`pin-legend-item ${active === i + 1 ? 'on' : ''}`}
          onMouseEnter={() => onHover(i + 1)}
          onMouseLeave={() => onHover(null)}
        >
          <i className={pin.kind === 'E' ? 'earnings' : 'other'}>{i + 1}</i>
          <span className="pl-date">{pin.date}</span>
          <span className="pl-label">{pin.label}</span>
        </button>
      ))}
    </div>
  );
}

/** RSI as a dial, because a number from 0 to 100 means nothing on its own. */
function RsiGauge({ value }) {
  if (value == null) return null;
  const angle = -90 + (value / 100) * 180;
  const state = value <= 30 ? 'sold hard' : value >= 70 ? 'bought hard' : 'middling';
  return (
    <div className="rsi">
      <svg viewBox="0 0 200 116" width="180">
        <path d="M20 100 A80 80 0 0 1 52.98 35.28" fill="none" stroke="#8DB8D6" strokeWidth="16" />
        <path d="M52.98 35.28 A80 80 0 0 1 147.02 35.28" fill="none" stroke="#E4DCCB" strokeWidth="16" />
        <path d="M147.02 35.28 A80 80 0 0 1 180 100" fill="none" stroke="#F6A57C" strokeWidth="16" />
        <g transform={`rotate(${angle} 100 100)`}>
          <path d="M100 100 L100 38" stroke="#16243A" strokeWidth="4" strokeLinecap="round" />
        </g>
        <circle cx="100" cy="100" r="7" fill="#16243A" />
      </svg>
      <b>{value}</b>
      <span>RSI · {state}</span>
    </div>
  );
}


/** Money in the sizes people actually say them in. */
function big(n) {
  if (n == null) return null;
  const abs = Math.abs(n);
  if (abs >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

const pctOf = (v, digits = 1) => (v == null ? null : `${(v * 100).toFixed(digits)}%`);

/** The company behind the ticker: what it does, what it's worth, how it
 *  earns. Facts about the business, as opposed to the price behaviour the
 *  rest of the page covers. */
function Fundamentals({ f, ticker, price }) {
  if (!f) {
    return (
      <Card>
        <h2>About {ticker}</h2>
        <div className="chart-empty">
          No company profile stored yet. Run <code>flask ingest</code> to fetch it.
        </div>
      </Card>
    );
  }

  const rows = [
    ['Market value', big(f.market_cap)],
    ['Revenue (12m)', big(f.revenue)],
    ['Revenue growth', pctOf(f.revenue_growth)],
    ['Profit margin', pctOf(f.profit_margin)],
    ['Earnings per share', f.eps != null ? `$${f.eps.toFixed(2)}` : null],
    ['Price / earnings', f.pe_trailing != null ? f.pe_trailing.toFixed(1) : null],
    ['Forward P/E', f.pe_forward != null ? f.pe_forward.toFixed(1) : null],
    ['Return on equity', pctOf(f.return_on_equity)],
    ['Dividend yield', f.dividend_yield ? pctOf(f.dividend_yield, 2) : 'None'],
    ['Free cash flow', big(f.free_cash_flow)],
    ['Debt to equity', f.debt_to_equity != null ? f.debt_to_equity.toFixed(0) : null],
    ['Beta', f.beta != null ? f.beta.toFixed(2) : null],
  ].filter(([, v]) => v != null);

  return (
    <Card className="fundamentals-card">
      <div className="card-title-row">
        <div>
          <h2>{f.name ?? ticker}</h2>
          <p className="muted">
            {[f.sector, f.industry].filter(Boolean).join(' · ')}
            {f.employees ? ` · ${f.employees.toLocaleString()} employees` : ''}
          </p>
        </div>
      </div>

      {f.about && <p className="fund-about">{f.about}</p>}

      {/* where today's price sits between the year's low and high */}
      {f.low_52w != null && f.high_52w != null && (
        <div className="range-52">
          <div className="range-head">
            <span>52-week range</span>
            <b>
              ${f.low_52w.toFixed(0)} – ${f.high_52w.toFixed(0)}
            </b>
          </div>
          <div className="range-track">
            <i style={{ left: `${Math.min(100, Math.max(0, f.range_position_pct ?? 0))}%` }} />
          </div>
          <span className="range-note">
            {f.range_position_pct != null
              ? `Today sits ${f.range_position_pct}% of the way up that range.`
              : ''}
          </span>
        </div>
      )}

      <div className="fund-grid">
        {rows.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <b>{value}</b>
          </div>
        ))}
      </div>

      {f.analyst_target != null && (
        <div className="callout">
          Analysts' average target is ${f.analyst_target.toFixed(0)}
          {f.vs_target_pct != null && (
            <>
              , {Math.abs(f.vs_target_pct)}% {f.vs_target_pct >= 0 ? 'above' : 'below'} today's
              price
            </>
          )}
          {f.analyst_count ? ` (${f.analyst_count} analysts` : ''}
          {f.analyst_view ? `, view: ${f.analyst_view}` : ''}
          {f.analyst_count ? ')' : ''}. A target is an opinion, not a measurement.
        </div>
      )}

      {f.fetched_at && <div className="fund-stamp">Company facts as of {f.fetched_at}</div>}
    </Card>
  );
}

export default function HoldingsPage() {
  const navigate = useNavigate();
  const { asOf } = useAsOf();
  const [holdings, setHoldings] = useState([]);
  const [ticker, setTicker] = useState(null);
  const [detail, setDetail] = useState(null);
  const [state, setState] = useState('loading');
  const [activePin, setActivePin] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getPortfolio(asOf)
      .then((d) => {
        if (cancelled) return;
        const list = d.holdings ?? [];
        setHoldings(list);
        if (!list.length) {
          setState('empty');
          return;
        }
        setTicker((t) => (t && list.some((h) => h.ticker === t) ? t : list[0].ticker));
      })
      .catch(() => !cancelled && setState('error'));
    return () => {
      cancelled = true;
    };
  }, [asOf]);

  useEffect(() => {
    let cancelled = false;
    if (!ticker) return () => {};
    setState('loading');
    api
      .stockDetail(ticker, asOf)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setState('ready');
      })
      .catch(() => !cancelled && setState('error'));
    return () => {
      cancelled = true;
    };
  }, [ticker, asOf]);

  if (state === 'empty') {
    return (
      <Shell title="Holdings">
        <div className="page-state">
          <b>No holdings yet.</b>
          <span>Add what you own to look at any of it in detail.</span>
          <button className="sign-btn" type="button" onClick={() => navigate('/onboarding')}>
            Add holdings →
          </button>
        </div>
      </Shell>
    );
  }

  const pos = detail?.position;
  const tech = detail?.technicals;
  const risk = detail?.risk;

  return (
    <Shell title="One ship at a time" kickerFallback>
      <nav className="holding-tabs">
        {holdings.map((h) => (
          <button
            key={h.ticker}
            type="button"
            className={`holding-tab ${ticker === h.ticker ? 'on' : ''}`}
            onClick={() => setTicker(h.ticker)}
          >
            <b>{h.ticker}</b>
            <span className={h.day_change_pct < 0 ? 'danger-text' : ''}>
              {h.day_change_pct > 0 ? '+' : ''}
              {h.day_change_pct}%
            </span>
          </button>
        ))}
      </nav>

      {state === 'loading' && <div className="page-state">Opening {ticker}…</div>}
      {state === 'error' && (
        <div className="page-state error">
          <b>Couldn't load {ticker}.</b>
          <span>Check that the backend is running.</span>
        </div>
      )}

      {state === 'ready' && detail && (
        <>
          <Card className="holding-head">
            <div>
              <div className="hh-name">
                <span className="hh-ticker">{detail.ticker}</span>
                {pos && (
                  <span className={`hh-move ${pos.day_change_pct < 0 ? 'danger-text' : 'up'}`}>
                    {pos.day_change_pct > 0 ? '+' : ''}
                    {pos.day_change_pct}% today
                  </span>
                )}
              </div>
              {pos && <div className="hh-price">${pos.price.toLocaleString()}</div>}
            </div>
            {pos && (
              <div className="hh-stats">
                <div>
                  <span>YOU OWN</span>
                  <b>{pos.shares} shares</b>
                </div>
                <div>
                  <span>WORTH</span>
                  <b>${pos.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</b>
                </div>
                <div>
                  <span>SHARE OF PORTFOLIO</span>
                  <b>{pos.weight_pct}%</b>
                </div>
                <div>
                  <span>CHANCE OF A SHARP DROP</span>
                  <b>{risk ? `${risk.p_drawdown_pct}%` : '—'}</b>
                </div>
              </div>
            )}
          </Card>

          <div className="holding-grid">
            <Card className="chart-card">
              <div className="card-title-row">
                <div>
                  <h2>A year on the water</h2>
                  <p className="muted">
                    Price with its 50 and 200-day averages. Pins mark real events — hover for
                    what they were.
                  </p>
                </div>
                <div className="legend-row">
                  <span className="lg blue">Price</span>
                  <span className="lg orange">50-day</span>
                  <span className="lg sand">200-day</span>
                </div>
              </div>
              <StockChart
                series={detail.series}
                pins={detail.pins}
                active={activePin}
                onHover={setActivePin}
              />
              <PinLegend pins={detail.pins} active={activePin} onHover={setActivePin} />
            </Card>

            <Card className="tech-card">
              <h2>Instrument panel</h2>
              <p className="muted">What the technical bot reads.</p>
              <RsiGauge value={tech?.rsi} />
              <div className="tech-rows">
                <div>
                  <span>50-day average</span>
                  <b className={tech?.vs_ma50_pct < 0 ? 'danger-text' : ''}>
                    {tech?.vs_ma50_pct > 0 ? '+' : ''}
                    {tech?.vs_ma50_pct}%
                  </b>
                </div>
                <div>
                  <span>200-day average</span>
                  <b className={tech?.vs_ma200_pct < 0 ? 'danger-text' : ''}>
                    {tech?.vs_ma200_pct == null ? '—' : `${tech.vs_ma200_pct > 0 ? '+' : ''}${tech.vs_ma200_pct}%`}
                  </b>
                </div>
                <div>
                  <span>From its 1-year high</span>
                  <b className="danger-text">{tech?.from_high_pct}%</b>
                </div>
                <div>
                  <span>Swings vs its normal</span>
                  <b>{tech?.vol_ratio}×</b>
                </div>
              </div>
              {risk?.drivers?.length > 0 && (
                <>
                  <h3 className="tech-sub">What the risk model reads</h3>
                  <div className="driver-list">
                    {risk.drivers.map((d) => (
                      <div className="driver" key={d.label}>
                        <i className={d.direction === 'raises risk' ? 'up' : 'down'} />
                        <span>{d.label}</span>
                        <em>{d.direction}</em>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </Card>
          </div>

          <div className="holding-grid">
            <Fundamentals f={detail.fundamentals} ticker={detail.ticker} price={pos?.price} />

            <Card className="evidence-card">
              <h2>The evidence</h2>
              <p className="muted">
                Every past event, and what actually happened to {detail.ticker} afterwards.
              </p>
              {detail.evidence.length === 0 && <div className="chart-empty">Nothing recorded yet.</div>}
              {detail.evidence.length > 0 && (
                <div className="ev-table ev-scroll">
                  <div className="ev-head">
                    <span>DATE</span>
                    <span>EVENT</span>
                    <span>STOCK</span>
                    <span>MARKET</span>
                    <span>BEYOND</span>
                  </div>
                  {detail.evidence.map((e) => (
                    <div className="ev-row" key={`${e.date}-${e.event_type}`}>
                      <span className="mono">{e.date}</span>
                      <span title={e.description}>
                        {e.event_type}
                        {e.subtype ? ` · ${e.subtype}` : ''}
                      </span>
                      <span className={`mono ${e.stock_pct < 0 ? 'danger-text' : ''}`}>{e.stock_pct}%</span>
                      <span className="mono muted-num">{e.market_pct}%</span>
                      <span className={`mono strong ${e.abnormal_pct < 0 ? 'danger-text' : ''}`}>
                        {e.abnormal_pct > 0 ? '+' : ''}
                        {e.abnormal_pct}%
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          {detail.news.articles.length > 0 && (
            <Card>
              <h2>Recent coverage</h2>
              <p className="muted">
                Scored for how much each story is really about {detail.ticker}.
              </p>
              <div className="news-topics">
                {detail.news.topics.map((t) => (
                  <Tag key={t.topic} tone="grey">
                    {t.label} · {t.n}
                  </Tag>
                ))}
              </div>
              <div className="news-scroll">
                {detail.news.articles.map((a) => (
                <article className="news-item" key={a.url}>
                  <div className="news-item-head">
                    <span className="mono">{a.date}</span>
                    <a href={a.url} target="_blank" rel="noreferrer" className="news-title">
                      {a.title}
                    </a>
                    <span className={`news-mood ${a.sentiment < -0.15 ? 'neg' : a.sentiment > 0.15 ? 'pos' : ''}`}>
                      {a.sentiment > 0 ? '+' : ''}
                      {a.sentiment}
                    </span>
                  </div>
                  {/* the summary, because a headline is written to be clicked
                      and often names the sector rather than the company */}
                  {a.summary && a.summary.length > 5 && <p className="news-summary">{a.summary}</p>}
                  <div className="news-meta-row">
                    <span>{a.source}</span>
                    <span>{a.topic_label}</span>
                    <span>relevance {a.relevance}</span>
                  </div>
                </article>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </Shell>
  );
}