import { useEffect, useMemo, useState } from 'react';
import { Bell, CalendarDays, Cloud, TrendingUp } from 'lucide-react';
import { Shell } from '../components/Shell';
import { Card, Tag } from '../components/ui';
import { api } from '../lib/api';
import { useAsOf } from '../lib/useAsOf';

const TONE = { Storm: 'red', Choppy: 'yellow', 'Heads-up': 'blue', Calm: 'grey' };

/** What each bot watches. Product copy, not data. */
const BOTS = [
  ['Technical bot', 'unusual moves, volume, trend', TrendingUp],
  ['Earnings bot', 'reports, surprises, filings', CalendarDays],
  ['News-mood bot', 'headlines, topics, tone', Bell],
  ['Macro bot', 'Fed, inflation, jobs, oil', Cloud],
];

/** Past comparable events, drawn from the evidence ledger.
 *  Laid out around a zero line: gains rise, losses hang. Doing the
 *  positioning here rather than in CSS keeps the two directions
 *  symmetrical, which the inherited styles did not. */
function HistoryBars({ events, ticker }) {
  if (!events?.length) return null;
  const max = Math.max(...events.map((e) => Math.abs(e.moved_pct)), 1);
  const HALF = 44;   // px available on each side of the zero line

  return (
    <div className="hist">
      <div className="hist-title">How {ticker} moved after each of these past events (%)</div>
      <div className="hist-plot">
        <div className="hist-zero" />
        {events.map((e) => {
          const up = e.moved_pct >= 0;
          const h = Math.max(3, (Math.abs(e.moved_pct) / max) * HALF);
          return (
            <div className="hist-col" key={`${e.date}-${e.moved_pct}`} title={`${e.date}: ${e.description}`}>
              <span className="hist-val" style={{ top: up ? HALF - h - 16 : HALF + h + 2 }}>
                {up ? '+' : ''}
                {e.moved_pct}
              </span>
              <i
                className={up ? 'up' : 'down'}
                style={{ height: h, top: up ? HALF - h : HALF }}
              />
            </div>
          );
        })}
      </div>
      <div className="hist-foot">
        {events.length} closest past events · hover for the date
      </div>
    </div>
  );
}

export default function SignalsPage() {
  const { asOf } = useAsOf();
  const [alerts, setAlerts] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [category, setCategory] = useState('All');
  const [state, setState] = useState('loading');
  const [narrator, setNarrator] = useState(null);
  const [tuning, setTuning] = useState([]);
  const [vote, setVote] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    setDetail(null);
    api
      .alerts(asOf)
      .then((d) => {
        if (cancelled) return;
        const list = d.alerts ?? [];
        setNarrator(d.narrator ?? null);
        setTuning(d.tuning ?? []);
        setAlerts(list);
        setSelectedId(list[0]?.id ?? null);
        setState(list.length ? 'ready' : 'empty');
      })
      .catch(() => !cancelled && setState('error'));
    return () => {
      cancelled = true;
    };
  }, [asOf]);

  // the full story is a second call, so the list stays fast
  useEffect(() => {
    let cancelled = false;
    setVote(null);
    if (!selectedId) {
      setDetail(null);
      return () => {};
    }
    api
      .alert(selectedId)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => !cancelled && setDetail(null));
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // categories come from the alerts themselves, so no list can go stale
  const categories = useMemo(() => {
    const counts = new Map();
    alerts.forEach((a) => counts.set(a.category, (counts.get(a.category) ?? 0) + 1));
    return [['All', alerts.length], ...[...counts.entries()].sort((a, b) => b[1] - a[1])];
  }, [alerts]);

  const shown = category === 'All' ? alerts : alerts.filter((a) => a.category === category);

  async function sendVote(value) {
    setVote(value);
    try {
      await api.alertFeedback(selectedId, value);
      // reflect the new ranking straight away, so the vote visibly does
      // something instead of disappearing into the database
      const d = await api.alerts(asOf);
      setTuning(d.tuning ?? []);
      setAlerts(d.alerts ?? []);
    } catch {
      /* a failed vote should never interrupt reading */
    }
  }

  const facts = detail?.facts ?? {};

  return (
    <Shell
      title="Signal log"
      subtitle="Everything Lookout's bots noticed, ranked by how much it moves your money."
    >
      <div className="bot-row">
        {BOTS.map(([name, desc, Icon]) => (
          <div className="bot-card dashed" key={name}>
            <Icon size={21} />
            <div>
              <b>{name}</b>
              <span>{desc}</span>
            </div>
          </div>
        ))}
      </div>

      {state === 'loading' && <div className="page-state">Checking what the bots found…</div>}

      {state === 'error' && (
        <div className="page-state error">
          <b>Couldn't reach the backend.</b>
          <span>Check that Flask is running on port 5000.</span>
        </div>
      )}

      {state === 'empty' && (
        <div className="page-state">
          <b>Nothing to report for this day.</b>
          <span>
            The bots looked and found nothing that moves your money much. Try another date with the
            time machine.
          </span>
        </div>
      )}

      {state === 'ready' && (
        <>
          {tuning.length > 0 && (
            <div className="tuning-note">
              Learned from your votes:{' '}
              {tuning
                .map((t) => `${t.direction} ${t.category.toLowerCase()} alerts`)
                .join(', ')}
              . These now rank {tuning[0].direction === 'more' ? 'higher' : 'lower'}.
            </div>
          )}

          <div className="filter-pills">
            {categories.map(([name, count]) => (
              <button
                key={name}
                type="button"
                className={category === name ? 'active' : ''}
                onClick={() => setCategory(name)}
              >
                {name} <b>{count}</b>
              </button>
            ))}
          </div>

          <div className="signal-layout">
            <div className="signal-list">
              {shown.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  className={`signal-item ${selectedId === a.id ? 'selected' : ''}`}
                  onClick={() => setSelectedId(a.id)}
                >
                  <div>
                    <Tag tone={TONE[a.severity] ?? 'grey'}>{a.severity}</Tag>
                    <span>{a.weight_pct != null ? `${a.weight_pct}% of you` : ''}</span>
                  </div>
                  <div>
                    <b>{a.title}</b>
                    <span>{a.category}</span>
                  </div>
                  <strong>{a.ticker}</strong>
                </button>
              ))}
            </div>

            <Card className="signal-detail">
              {!detail ? (
                <div className="page-state">Opening…</div>
              ) : (
                <>
                  <div className="detail-head">
                    <b>
                      {detail.severity} · {detail.category}
                    </b>
                    <span>{facts.when ?? detail.as_of}</span>
                  </div>

                  <div className="detail-inner">
                    <div className="eyebrow">{detail.ticker}</div>
                    <h2>{detail.text?.title}</h2>

                    {detail.text ? (
                      <>
                        <div className="dashed take-box">
                          <div className="eyebrow">
                            LOOKOUT'S TAKE · WRITTEN BY {narrator?.model ?? 'the local model'}
                            {detail.grounded && <span className="grounded-chip">numbers checked</span>}
                          </div>
                          <p>{facts.headline}</p>
                        </div>

                        <h3>Why it matters to you</h3>
                        <p>{detail.text.why}</p>

                        <h3>What history says</h3>
                        <p>{detail.text.history}</p>
                      </>
                    ) : (
                      <>
                        <h3>What happened</h3>
                        <p>{facts.headline}</p>
                      </>
                    )}
                    <HistoryBars events={detail.past_events} ticker={detail.ticker} />

                    {facts.drivers?.length > 0 && (
                      <>
                        <h3>What the risk model is reading</h3>
                        <div className="driver-list">
                          {facts.drivers.map((d) => (
                            <div className="driver" key={d.label}>
                              <i className={d.direction === 'raises risk' ? 'up' : 'down'} />
                              <span>{d.label}</span>
                              <em>{d.direction}</em>
                            </div>
                          ))}
                        </div>
                        <p className="fine-print">
                          These are patterns the model links to risk, not causes.
                        </p>
                      </>
                    )}

                    <h3>The numbers behind this</h3>
                    <div className="fact-grid">
                      <div>
                        <span>Position size</span>
                        <b>{facts.weight_pct}% · ${facts.position_usd?.toLocaleString()}</b>
                      </div>
                      <div>
                        <span>Move that day</span>
                        <b>{facts.day_move_pct > 0 ? '+' : ''}{facts.day_move_pct}%</b>
                      </div>
                      <div>
                        <span>Effect on portfolio</span>
                        <b>{facts.portfolio_impact_pct > 0 ? '+' : ''}{facts.portfolio_impact_pct}%</b>
                      </div>
                      <div>
                        <span>Chance of a sharp drop</span>
                        <b>{facts.risk_probability_pct}%</b>
                      </div>
                      <div>
                        <span>Typical move after this</span>
                        <b>±{facts.typical_move_pct}%</b>
                      </div>
                      <div>
                        <span>An ordinary stretch</span>
                        <b>±{facts.baseline_move_pct}%</b>
                      </div>
                    </div>

                    <h3>Where this came from</h3>
                    {facts.sources?.length > 0 && (
                      <div className="source-articles">
                        {facts.sources.map((src) => (
                          <article className="news-item" key={src.url}>
                            <div className="news-item-head">
                              <a href={src.url} target="_blank" rel="noreferrer" className="news-title">
                                {src.title}
                              </a>
                            </div>
                            {src.summary && src.summary.length > 5 && (
                              <p className="news-summary">{src.summary}</p>
                            )}
                            <div className="news-meta-row">
                              <span>{src.source}</span>
                              <span>relevance {src.relevance}</span>
                            </div>
                          </article>
                        ))}
                      </div>
                    )}
                    <div className="source-chips">
                      <span>{facts.n_past ? `${facts.n_past} past events` : 'No past events yet'}</span>
                      {facts.sources?.length ? null : <span>Daily prices</span>}
                    </div>
                  </div>

                  <div className="detail-actions">
                    <span>Teach Lookout what you care about</span>
                    <button
                      type="button"
                      className={vote === 'useful' ? 'voted' : ''}
                      onClick={() => sendVote('useful')}
                    >
                      {vote === 'useful' ? 'Noted ✓' : 'Useful'}
                    </button>
                    <button
                      type="button"
                      className={vote === 'less' ? 'voted' : ''}
                      onClick={() => sendVote('less')}
                    >
                      {vote === 'less' ? 'Noted ✓' : 'Less like this'}
                    </button>
                  </div>
                </>
              )}
            </Card>
          </div>
        </>
      )}
    </Shell>
  );
}