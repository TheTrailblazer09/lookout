/**
 * Charts drawn from API data. All plain SVG: no chart library, so every
 * pixel matches the design and the bundle stays small.
 */

const money = (v) =>
  `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const pct = (v, digits = 1) =>
  `${v > 0 ? '+' : ''}${Number(v).toFixed(digits)}%`;

/** Portfolio vs market, both rebased to 0% at the left edge. */
export function PerformanceChart({ series, pins = [] }) {
  if (!series?.length) return <div className="chart-empty">Not enough price history yet.</div>;

  const W = 760;
  const H = 240;
  const pad = { l: 44, r: 12, t: 12, b: 26 };
  const values = series.flatMap((p) => [p.portfolio, p.market]);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  // round outward to a tidy step so gridlines land on readable numbers
  const span = hi - lo || 1;
  const step = span > 60 ? 20 : span > 24 ? 10 : span > 10 ? 5 : 2;
  lo = Math.floor(lo / step) * step;
  hi = Math.ceil(hi / step) * step;

  const x = (i) => pad.l + (i / (series.length - 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);
  const line = (key) => series.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(' ');

  const ticks = [];
  for (let v = lo; v <= hi + 0.001; v += step) ticks.push(v);

  // a handful of evenly spaced date labels
  const labelIdx = [0, Math.floor(series.length / 3), Math.floor((2 * series.length) / 3), series.length - 1];

  // The series is sampled (every third session), so a pin's exact date
  // rarely appears in it. Snap each pin to the closest point we drew, and
  // drop any that fall outside the window entirely.
  const placed = pins
    .map((pin) => {
      let best = -1;
      let bestGap = Infinity;
      series.forEach((p, i) => {
        const gap = Math.abs(new Date(p.date) - new Date(pin.date));
        if (gap < bestGap) {
          bestGap = gap;
          best = i;
        }
      });
      if (best < 0 || bestGap > 7 * 86400000) return null;
      return { ...pin, i: best, cx: x(best), cy: y(series[best].portfolio) };
    })
    .filter(Boolean);

  return (
    <svg className="perf-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Portfolio versus market">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke={v === 0 ? '#16243A' : '#E4DCCB'} strokeWidth="1" />
          <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#5A6272" fontFamily="JetBrains Mono, monospace">
            {v > 0 ? `+${v}` : v}%
          </text>
        </g>
      ))}
      <path d={`${line('portfolio')} L ${x(series.length - 1)} ${y(lo)} L ${x(0)} ${y(lo)} Z`} fill="#1F6F99" fillOpacity="0.10" />
      <path d={line('market')} fill="none" stroke="#7C8594" strokeWidth="2" strokeDasharray="5 5" />
      <path d={line('portfolio')} fill="none" stroke="#1F6F99" strokeWidth="3" strokeLinejoin="round" />
      {placed.map((pin) => (
        <g key={`${pin.date}-${pin.ticker}`} className="perf-pin">
          <title>{`${pin.label} · ${pin.date}`}</title>
          <circle
            cx={pin.cx}
            cy={pin.cy}
            r="9"
            fill={pin.kind === 'alert' ? '#F2B33D' : '#FFFDF8'}
            stroke={pin.kind === 'alert' ? '#16243A' : '#1F6F99'}
            strokeWidth="2"
          />
          <text
            x={pin.cx}
            y={pin.cy + 4}
            textAnchor="middle"
            fontSize="10"
            fontWeight="700"
            fill={pin.kind === 'alert' ? '#16243A' : '#1F6F99'}
            fontFamily="JetBrains Mono, monospace"
          >
            {pin.kind === 'alert' ? '!' : 'E'}
          </text>
        </g>
      ))}
      {labelIdx.map((i) => (
        <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? 'start' : i === series.length - 1 ? 'end' : 'middle'}
              fontSize="11" fill="#5A6272" fontFamily="JetBrains Mono, monospace">
          {series[i].date.slice(0, 7)}
        </text>
      ))}
    </svg>
  );
}

/** Allocation, biggest first, sized by weight. */
export function Treemap({ weights }) {
  const rows = Object.entries(weights ?? {}).sort((a, b) => b[1] - a[1]);
  if (!rows.length) return <div className="chart-empty">No holdings yet.</div>;

  const shades = ['#16426A', '#2F6B99', '#4E8CB5', '#8DB8D6', '#B9D2E4', '#D9CFBB', '#E7E1D3', '#CFE2EE'];
  // two bands: the largest few on top, the rest below, so small slices stay legible
  const split = Math.min(3, Math.max(1, Math.ceil(rows.length / 2)));
  const bands = [rows.slice(0, split), rows.slice(split)];

  return (
    <div className="treemap-live">
      {bands.map((band, bi) =>
        band.length ? (
          <div className="tm-band" key={bi} style={{ flex: band.reduce((s, [, w]) => s + w, 0) }}>
            {band.map(([ticker, weight], i) => {
              const shade = shades[Math.min(shades.length - 1, bi * split + i)];
              const dark = bi * split + i < 3;
              return (
                <div key={ticker} className="tm-cell" style={{ flex: weight, background: shade, color: dark ? '#FFFDF8' : '#16243A' }}>
                  <b>{ticker}</b>
                  <span>{weight.toFixed(0)}%</span>
                </div>
              );
            })}
          </div>
        ) : null
      )}
    </div>
  );
}

/** Share of money next to share of risk: the gap is the insight. */
export function RiskBars({ weights, riskShare }) {
  const rows = Object.keys(weights ?? {})
    .map((t) => ({ ticker: t, weight: weights[t], risk: riskShare?.[t] ?? 0 }))
    .sort((a, b) => b.risk - a.risk);
  if (!rows.length) return <div className="chart-empty">No holdings yet.</div>;
  const max = Math.max(...rows.flatMap((r) => [r.weight, r.risk]), 10);

  return (
    <div className="risk-bars">
      <div className="risk-legend">
        <span><i className="share" /> Share of your money</span>
        <span><i className="bump" /> Share of the bumpiness</span>
      </div>
      {rows.map((r) => (
        <div className="risk-row-live" key={r.ticker}>
          <span className="rb-ticker">{r.ticker}</span>
          <div className="rb-tracks">
            <div className="rb-line">
              <i style={{ width: `${(r.weight / max) * 100}%` }} />
              <em>{r.weight.toFixed(0)}%</em>
            </div>
            <div className="rb-line">
              <b style={{ width: `${(r.risk / max) * 100}%` }} />
              <strong>{r.risk.toFixed(0)}%</strong>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Correlation matrix as a heat grid. */
export function CorrelationGrid({ correlation }) {
  const labels = Object.keys(correlation ?? {});
  if (labels.length < 2) return <div className="chart-empty">Add at least two holdings to compare them.</div>;

  const shade = (v, same) => {
    if (same) return ['#16243A', '#F3EEE3'];
    if (v >= 0.6) return ['#16426A', '#FFFFFF'];
    if (v >= 0.4) return ['#8DB8D6', '#16243A'];
    if (v >= 0.2) return ['#CFE2EE', '#16243A'];
    if (v >= 0) return ['#F1EADB', '#16243A'];
    return ['#F9CDB0', '#16243A'];
  };

  return (
    <div className="corr-live" style={{ gridTemplateColumns: `56px repeat(${labels.length}, minmax(0,1fr))` }}>
      <div />
      {labels.map((l) => <b key={`h-${l}`}>{l}</b>)}
      {labels.map((row) => (
        <>
          <b key={`r-${row}`}>{row}</b>
          {labels.map((col) => {
            const v = correlation[row]?.[col] ?? 0;
            const same = row === col;
            const [bg, fg] = shade(v, same);
            return (
              <span key={`${row}-${col}`} style={{ background: bg, color: fg }}>
                {same ? '—' : v.toFixed(2).replace(/^0/, '').replace(/^-0/, '-')}
              </span>
            );
          })}
        </>
      ))}
    </div>
  );
}

export { money, pct };