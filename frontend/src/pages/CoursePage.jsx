import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shell } from '../components/Shell';
import { Card, Tag } from '../components/ui';
import { api } from '../lib/api';
import { useAsOf } from '../lib/useAsOf';

const TONE = {
  Rebalance: 'red',
  Diversify: 'blue',
  Cushion: 'grey',
  'Stay put': 'blue',
  'Take a look': 'yellow',
};

function Compass({ compass }) {
  return (
    <Card className="compass-card">
      <div className="card-title-row">
        <h2>Your compass</h2>
      </div>
      <div className="compass-grid">
        <div>
          <span>No stock above</span>
          <b>{compass.concentration_limit_pct}%</b>
        </div>
        <div>
          <span>Alert level</span>
          <b>{compass.sensitivity}</b>
        </div>
        <div>
          <span>Bots watching</span>
          <b>{compass.bots?.length ?? 0}</b>
        </div>
        <div>
          <span>Rules broken</span>
          <b className={compass.broken?.length ? 'danger-text' : ''}>
            {compass.broken?.length ?? 0}
          </b>
        </div>
      </div>
      {compass.broken?.length > 0 && (
        <div className="compass-broken">
          {compass.broken.map((b) => (
            <div key={b.by}>
              <i />
              <span>
                <b>{b.by}</b> is {b.value}% — your rule is {compass.concentration_limit_pct}%
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/** A number that visibly moves when the plan changes. */
function PreviewRow({ label, before, after, suffix = '', note, better = 'lower' }) {
  const has = after !== null && after !== undefined;
  const improved =
    has && (better === 'lower' ? Number(after) < Number(before) : Number(after) > Number(before));
  const worse =
    has && (better === 'lower' ? Number(after) > Number(before) : Number(after) < Number(before));
  return (
    <div className="preview-row-live">
      <div>
        <b>{label}</b>
        {note && <span>{note}</span>}
      </div>
      <span className="pv-before">
        {before}
        {suffix}
      </span>
      <span className={`pv-after ${improved ? 'good' : ''} ${worse ? 'bad' : ''}`}>
        {has ? `${after}${suffix}` : '—'}
      </span>
    </div>
  );
}

export default function CoursePage() {
  const navigate = useNavigate();
  const { asOf } = useAsOf();
  const [plan, setPlan] = useState(null);
  const [state, setState] = useState('loading');
  const [chosen, setChosen] = useState([]);
  const [dismissed, setDismissed] = useState([]);
  const [sim, setSim] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    setChosen([]);
    setSim(null);
    api
      .planIdeas(asOf)
      .then((d) => {
        if (cancelled) return;
        setPlan(d);
        setState(d.empty ? 'empty' : 'ready');
      })
      .catch(() => !cancelled && setState('error'));
    return () => {
      cancelled = true;
    };
  }, [asOf]);

  // re-run the maths whenever the plan changes
  useEffect(() => {
    let cancelled = false;
    if (!chosen.length) {
      setSim(null);
      return () => {};
    }
    api
      .planSimulate(asOf, chosen)
      .then((d) => !cancelled && setSim(d))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [chosen, asOf]);

  if (state === 'loading') {
    return (
      <Shell title="Chart a course">
        <div className="page-state">Working out what's worth considering…</div>
      </Shell>
    );
  }
  if (state === 'error') {
    return (
      <Shell title="Chart a course">
        <div className="page-state error">
          <b>Couldn't load your plan.</b>
          <span>Check that the backend is running.</span>
        </div>
      </Shell>
    );
  }
  if (state === 'empty') {
    return (
      <Shell title="Chart a course">
        <div className="page-state">
          <b>No holdings yet.</b>
          <span>Add what you own and Lookout can suggest what to think about.</span>
          <button className="sign-btn" type="button" onClick={() => navigate('/onboarding')}>
            Add holdings →
          </button>
        </div>
      </Shell>
    );
  }

  const today = plan.today;
  const after = sim?.after;
  const visible = plan.ideas.filter((i) => !dismissed.includes(i.id));
  const toggle = (id) =>
    setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));

  return (
    <Shell
      title="Chart a course"
      subtitle="Things worth thinking about, drawn from your own holdings and the rules you set."
    >
      <div className="disclaimer">
        <b>Lookout suggests, you decide.</b> These come from your numbers and your rules. They are
        information, not financial advice, and Lookout never places a trade.
      </div>

      <div className="course-layout">
        <div className="idea-column">
          {visible.length === 0 && (
            <div className="page-state">
              <b>Nothing to flag.</b>
              <span>Your portfolio is inside every rule you set.</span>
            </div>
          )}

          {visible.map((idea) => {
            const active = chosen.includes(idea.id);
            return (
              <Card key={idea.id} className={`idea-card ${active ? 'chosen' : ''}`}>
                <div className="idea-head">
                  <div>
                    <div className="idea-tags">
                      <Tag tone={TONE[idea.kind] ?? 'grey'}>{idea.kind}</Tag>
                      <span className="ticker-label">{idea.ticker}</span>
                    </div>
                    <h3>{idea.title}</h3>
                  </div>
                  <div className="fit-dots">
                    <span className="dots">
                      {'●'.repeat(idea.fit)}
                      {'○'.repeat(Math.max(0, 5 - idea.fit))}
                    </span>
                    <span>{idea.fit >= 4 ? 'Strong fit' : 'Worth a look'}</span>
                  </div>
                </div>

                <div className="idea-body">
                  <div>
                    <h4>Why</h4>
                    <ul>
                      {idea.reasons.map((r) => (
                        <li key={r.text}>
                          {r.text}
                          <em> · {r.source}</em>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="idea-notes">
                    <div className="warn-box">
                      <b>What could go wrong:</b> {idea.risk}
                    </div>
                    <div className="effect-box">
                      <b>If you did this:</b> {idea.effect}
                    </div>
                  </div>
                </div>

                <div className="idea-actions">
                  <button type="button" onClick={() => setDismissed((d) => [...d, idea.id])}>
                    Not for me
                  </button>
                  {idea.change ? (
                    <button
                      type="button"
                      className={active ? 'dark-action' : 'yellow-action'}
                      onClick={() => toggle(idea.id)}
                    >
                      {active ? 'In my plan ✓' : 'Add to plan'}
                    </button>
                  ) : (
                    <span className="no-change-note">Nothing to change</span>
                  )}
                </div>
              </Card>
            );
          })}
        </div>

        <div className="plan-column">
          <Compass compass={plan.compass} />

          <Card className="plan-preview">
            <h2>Plan preview</h2>
            <p className="muted">
              {chosen.length === 0
                ? 'Add an idea to see what it would change.'
                : `${chosen.length} ${chosen.length === 1 ? 'idea' : 'ideas'} in your plan.`}
            </p>

            <div className="preview-headers">
              <span />
              <span>Today</span>
              <span>With your plan</span>
            </div>

            <PreviewRow
              label={`Biggest holding${after?.top_ticker ? ` (${after.top_ticker})` : ''}`}
              before={today.top_weight_pct}
              after={after?.top_weight_pct}
              suffix="%"
              note={`Your limit is ${plan.compass.concentration_limit_pct}%`}
            />
            <PreviewRow
              label="Bumpiness from it"
              before={today.top_risk_pct}
              after={after?.top_risk_pct}
              suffix="%"
              note="Share of the portfolio's swings"
            />
            <PreviewRow
              label="Bumpiness (volatility)"
              before={today.volatility_pct}
              after={after?.volatility_pct}
              suffix="%"
              note="How much your value swings in a year"
            />
            <PreviewRow
              label="Beta"
              before={today.beta}
              after={after?.beta}
              note="How much you move when the market moves 1%"
            />
            <PreviewRow
              label="Rules broken"
              before={today.over_limit.length}
              after={after ? after.over_limit.length : null}
              note="Holdings past your own size limit"
            />
            <PreviewRow
              label="Held in cash"
              before={today.cash_pct ?? 0}
              after={after?.cash_pct}
              suffix="%"
              note="Money not in any stock"
              better="higher"
            />

            <p className="fine-print">
              Estimated from the past year of prices, holding the same stocks in different
              amounts. Lookout never trades; selling can have tax consequences your broker can
              show you.
            </p>
          </Card>
        </div>
      </div>
    </Shell>
  );
}