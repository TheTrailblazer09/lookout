import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, LockKeyhole, Search, X } from 'lucide-react';
import { Brand } from '../components/Brand';
import { LighthouseScene } from '../components/LighthouseScene';
import { api } from '../lib/api';

/**
 * Two steps, both talking to Flask.
 *
 *   1. Which stocks you own  -> PUT /portfolio
 *   2. How loud alerts get   -> PUT /preferences
 *
 * Nothing here is hardcoded: tickers come from /tickers/search, and each
 * one is priced from its own last close, so the value column is real money
 * rather than a placeholder.
 */

const SENSITIVITY = [
  ['calm', 'Calm', 'Only when something big happens. A handful of alerts a month.'],
  ['balanced', 'Balanced', 'The recommended setting. A few alerts a week.'],
  ['vigilant', 'Vigilant', 'Tell me everything the bots notice, even small stuff.'],
];

const BOTS = [
  ['technical', 'Price moves', 'Unusual daily moves, volume spikes, trend changes'],
  ['earnings', 'Earnings', 'Report dates, beats and misses, filings'],
  ['news', 'News mood', 'Layoffs, lawsuits, product news, sentiment swings'],
  ['macro', 'The economy', 'Fed decisions, inflation, jobs reports'],
];

export default function OnboardingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);

  // ---- step 1 state ------------------------------------------------------
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState([]);
  const [searching, setSearching] = useState(false);
  const [rows, setRows] = useState([]);          // { ticker, shares, price }
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // ---- step 2 state ------------------------------------------------------
  const [prefs, setPrefs] = useState(null);

  const owned = useMemo(() => new Set(rows.map((r) => r.ticker)), [rows]);

  // Pick up anything already saved, so re-running onboarding edits rather
  // than starting from nothing.
  useEffect(() => {
    api
      .getPortfolio()
      .then((d) => {
        if (d.holdings?.length) {
          setRows(d.holdings.map((h) => ({ ticker: h.ticker, shares: String(h.shares), price: h.price })));
        }
      })
      .catch(() => {});
    api.getPreferences().then(setPrefs).catch(() => setPrefs(null));
  }, []);

  // Debounced search: one request after typing stops, not one per keystroke.
  const timer = useRef();
  useEffect(() => {
    clearTimeout(timer.current);
    const term = query.trim();
    if (term.length < 1) {
      setMatches([]);
      return () => {};
    }
    setSearching(true);
    timer.current = setTimeout(() => {
      api
        .searchTickers(term)
        .then((d) => setMatches(d.results ?? []))
        .catch(() => setMatches([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => clearTimeout(timer.current);
  }, [query]);

  const addTicker = useCallback(
    async (ticker) => {
      if (owned.has(ticker)) return;
      setRows((r) => [...r, { ticker, shares: '', price: null }]);
      setQuery('');
      setMatches([]);
      try {
        const p = await api.lastPrice(ticker);       // price it for real
        if (p) setRows((r) => r.map((x) => (x.ticker === ticker ? { ...x, price: p.price } : x)));
      } catch {
        /* a missing price just leaves the value blank */
      }
    },
    [owned]
  );

  const setShares = (ticker, value) =>
    setRows((r) => r.map((x) => (x.ticker === ticker ? { ...x, shares: value } : x)));

  const removeRow = (ticker) => setRows((r) => r.filter((x) => x.ticker !== ticker));

  const valued = rows.map((r) => ({
    ...r,
    value: r.price && Number(r.shares) > 0 ? r.price * Number(r.shares) : null,
  }));
  const total = valued.reduce((sum, r) => sum + (r.value ?? 0), 0);
  const ready = rows.length > 0 && rows.every((r) => Number(r.shares) > 0);

  async function saveHoldings() {
    setError('');
    if (!ready) {
      setError('Give every holding a share count above zero.');
      return;
    }
    setSaving(true);
    try {
      await api.savePortfolio(rows.map((r) => ({ ticker: r.ticker, shares: Number(r.shares) })));
      setStep(2);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function savePrefs() {
    setError('');
    setSaving(true);
    try {
      await api.savePreferences(prefs ?? {});
      navigate('/overview', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const toggleBot = (id) =>
    setPrefs((p) => {
      const bots = new Set(p?.bots ?? []);
      if (bots.has(id)) bots.delete(id);
      else bots.add(id);
      return { ...(p ?? {}), bots: [...bots] };
    });

  return (
    <div className="onboard">
      <div className="onboard-side">
        <Brand />
        <h1>{step === 1 ? "Tell us what's on board." : 'How loud should we be?'}</h1>
        <p>
          {step === 1
            ? 'Lookout keeps watch over your stocks day and night, and only taps your shoulder when something actually needs a look.'
            : 'You can change any of this later. Nothing here leaves your machine.'}
        </p>
        <div className="steps">
          <div className={step === 1 ? 'on' : 'done'}>
            <b>{step > 1 ? <Check size={13} /> : 1}</b>
            <span>Add your stocks</span>
          </div>
          <div className={step === 2 ? 'on' : ''}>
            <b>2</b>
            <span>Pick how loud alerts should be</span>
          </div>
        </div>
        <LighthouseScene variant="onboard" />
      </div>

      {step === 1 ? (
        <main className="onboard-main">
          <div className="eyebrow">STEP 1 OF 2</div>
          <h1>What do you own?</h1>
          <p>Search by ticker. Add the number of shares you hold.</p>

          <label htmlFor="add-stock">Add a stock</label>
          <div className="search-box">
            <Search size={18} />
            <input
              id="add-stock"
              value={query}
              onChange={(e) => setQuery(e.target.value.toUpperCase())}
              placeholder="Start typing: NVDA, AAPL…"
              autoComplete="off"
            />
            <span>{searching ? 'searching…' : query ? `${matches.length} matches` : ''}</span>
          </div>

          {query && !searching && (
            <div className="matches">
              {matches.length === 0 && (
                <div className="match-empty">
                  No ticker matches “{query}”. Lookout only knows stocks it has price history for.
                </div>
              )}
              {matches.map((ticker) => (
                <div key={ticker} className={owned.has(ticker) ? 'added' : ''}>
                  <b>{ticker}</b>
                  <span />
                  {owned.has(ticker) ? (
                    <strong>Added</strong>
                  ) : (
                    <button type="button" onClick={() => addTicker(ticker)}>
                      + Add
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="holdings-table">
            <div className="table-head">
              <span>TICKER</span>
              <span>LAST CLOSE</span>
              <span>SHARES</span>
              <span>VALUE</span>
              <span />
            </div>

            {valued.length === 0 && (
              <div className="table-empty">
                Nothing added yet. Search above to add your first holding.
              </div>
            )}

            {valued.map((h) => (
              <div key={h.ticker}>
                <b>{h.ticker}</b>
                <span>{h.price ? `$${h.price.toFixed(2)}` : '—'}</span>
                <input
                  value={h.shares}
                  inputMode="decimal"
                  placeholder="0"
                  aria-label={`${h.ticker} shares`}
                  onChange={(e) => setShares(h.ticker, e.target.value.replace(/[^\d.]/g, ''))}
                />
                <strong>
                  {h.value ? `$${h.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
                </strong>
                <button type="button" aria-label={`Remove ${h.ticker}`} onClick={() => removeRow(h.ticker)}>
                  <X size={15} />
                </button>
              </div>
            ))}

            <div className="table-total">
              <b>
                {rows.length} {rows.length === 1 ? 'holding' : 'holdings'}
              </b>
              <strong>${total.toLocaleString(undefined, { maximumFractionDigits: 0 })}</strong>
            </div>
          </div>

          {error && <div className="form-error" role="alert">{error}</div>}

          <div className="onboard-actions">
            <button className="outline-btn" type="button" onClick={() => navigate('/overview')}>
              Skip for now
            </button>
            <button className="sign-btn" type="button" onClick={saveHoldings} disabled={saving || !ready}>
              {saving ? 'Saving…' : 'Next: alerts →'}
            </button>
          </div>

          <div className="secure-note">
            <LockKeyhole size={14} /> Your holdings stay on this computer. The AI that watches them
            runs here too.
          </div>
        </main>
      ) : (
        <main className="onboard-main">
          <div className="eyebrow">STEP 2 OF 2</div>
          <h1>How loud should we be?</h1>
          <p>Lookout ranks everything by how much it actually moves your money. This sets the bar.</p>

          <div className="pref-group">
            {SENSITIVITY.map(([id, title, blurb]) => (
              <button
                key={id}
                type="button"
                className={`pref-option ${prefs?.sensitivity === id ? 'on' : ''}`}
                onClick={() => setPrefs((p) => ({ ...(p ?? {}), sensitivity: id }))}
              >
                <b>{title}</b>
                <span>{blurb}</span>
              </button>
            ))}
          </div>

          <h3 className="pref-heading">What should the bots watch?</h3>
          <div className="pref-group">
            {BOTS.map(([id, title, blurb]) => {
              const on = (prefs?.bots ?? []).includes(id);
              return (
                <button
                  key={id}
                  type="button"
                  className={`pref-option ${on ? 'on' : ''}`}
                  onClick={() => toggleBot(id)}
                >
                  <b>
                    {title} {on && <Check size={14} />}
                  </b>
                  <span>{blurb}</span>
                </button>
              );
            })}
          </div>

          <h3 className="pref-heading">Nudge me when one stock gets too big</h3>
          <div className="pref-limit">
            <input
              type="range"
              min="5"
              max="60"
              step="5"
              value={prefs?.concentration_limit_pct ?? 25}
              onChange={(e) =>
                setPrefs((p) => ({ ...(p ?? {}), concentration_limit_pct: Number(e.target.value) }))
              }
            />
            <b>{prefs?.concentration_limit_pct ?? 25}% of the portfolio</b>
          </div>

          {error && <div className="form-error" role="alert">{error}</div>}

          <div className="onboard-actions">
            <button className="outline-btn" type="button" onClick={() => setStep(1)}>
              ← Back to holdings
            </button>
            <button className="sign-btn" type="button" onClick={savePrefs} disabled={saving}>
              {saving ? 'Saving…' : 'Start watching →'}
            </button>
          </div>

          <div className="secure-note">
            <LockKeyhole size={14} /> You can change all of this later from the sidebar.
          </div>
        </main>
      )}
    </div>
  );
}