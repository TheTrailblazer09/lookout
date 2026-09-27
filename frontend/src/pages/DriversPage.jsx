// import { useState } from 'react';
// import { Shell } from '../components/Shell';
// import { Card, FooterNote } from '../components/ui';
// import { sensitivity } from '../data/portfolio';

// function DotsPlot() {
//   const xs = [22, 66, 83, 103, 115, 122, 129, 137, 143, 148, 155, 161, 168, 175, 179, 183, 189, 197, 205, 212, 218, 226, 238, 248];
//   return (
//     <svg viewBox="0 0 280 90" className="dots-plot">
//       <line x1="10" y1="44" x2="270" y2="44" stroke="#d2cabd" />
//       <line x1="140" y1="12" x2="140" y2="72" stroke="#d2cabd" />
//       <text x="10" y="84" fontSize="10">
//         -43%
//       </text>
//       <text x="137" y="84" fontSize="10">
//         0
//       </text>
//       <text x="250" y="84" fontSize="10">
//         +43%
//       </text>
//       {xs.map((x, i) => (
//         <circle key={i} cx={x} cy={28 + (i % 3) * 12} r="4.5" fill={x < 140 ? '#d95b2d' : '#2d789e'} stroke="#163047" />
//       ))}
//     </svg>
//   );
// }

// export default function DriversPage() {
//   const { labels, cols, matrix } = sensitivity;
//   const [picked, setPicked] = useState({ r: 0, c: 0 });
//   const value = matrix[picked.r][picked.c];

//   return (
//     <Shell
//       title="What moves my stocks"
//       kicker="LOOKOUT'S MEMORY · SINCE JAN 2019"
//       subtitle="Every event since 2019, lined up against how each of your stocks moved in the 5 days after. Darker means a bigger reaction. Tap any square."
//       headerExtra={
//         <div className="memory-count">
//           <b>1,768</b>
//           <span>stock × event moments learned</span>
//         </div>
//       }
//     >
//       <div className="steps-row">
//         {[
//           ['1', 'Bots log every event.', 'Earnings, Fed days, CPI prints, oil shocks, news-mood swings.'],
//           ['2', 'Lookout measures what happened next', 'to each stock over the following 5 trading days.'],
//           ['3', "That becomes each stock's fingerprint,", 'which decides how loud an alert should be.'],
//         ].map((s) => (
//           <div className="step-box dashed" key={s[0]}>
//             <b>{s[0]}</b>
//             <p>
//               <strong>{s[1]}</strong> {s[2]}
//             </p>
//           </div>
//         ))}
//       </div>

//       <div className="drivers-layout">
//         <Card className="map-card">
//           <div className="map-title">
//             <h2>Sensitivity map</h2>
//             <span className="heat-legend">
//               calm <i /><i /><i /><i /><i /> big moves
//             </span>
//           </div>
//           <div className="heat-grid">
//             <div />
//             {cols.map((c) => (
//               <b key={c}>{c}</b>
//             ))}
//             {matrix.flatMap((row, r) => [
//               <strong key={`lab-${labels[r]}`}>{labels[r]}</strong>,
//               ...row.map((v, c) => (
//                 <button
//                   type="button"
//                   className={picked.r === r && picked.c === c ? 'selected' : ''}
//                   key={`${r}-${c}`}
//                   style={{
//                     background: `rgba(32,119,163,${0.12 + Math.min(1, v / 10) * 0.9})`,
//                     color: v > 5 ? 'white' : '#162b42',
//                   }}
//                   onClick={() => setPicked({ r, c })}
//                 >
//                   ±{v.toFixed(1)}
//                 </button>
//               )),
//             ])}
//           </div>
//           <div className="callout blue">
//             <b>Your two jumpiest stocks, TSLA and NVDA, both react most to earnings.</b> XOM is the
//             odd one out: it barely notices earnings season but jumps on oil shocks.
//           </div>
//         </Card>

//         <Card className="picked-card">
//           <div className="eyebrow">YOU PICKED</div>
//           <h2>
//             {labels[picked.r]} on {cols[picked.c].toLowerCase()} days
//           </h2>
//           <div className="picked-value">
//             ±{value.toFixed(1)}% <span>typical 5-day move</span>
//           </div>
//           <div className="picked-stats">
//             <div>
//               <b>24</b>
//               <span>past events</span>
//             </div>
//             <div>
//               <b>-38.7%</b>
//               <span>biggest move</span>
//             </div>
//             <div>
//               <b>58%</b>
//               <span>went up after</span>
//             </div>
//           </div>
//           <h4>Every past event, one dot each</h4>
//           <DotsPlot />
//           <div className="dashed plain-box">
//             <div className="eyebrow">IN PLAIN ENGLISH</div>
//             <p>
//               {labels[picked.r]} usually moves about {value.toFixed(1)}% in the 5 days after a{' '}
//               {cols[picked.c].toLowerCase()}. That's among the biggest reactions of your 7 holdings,
//               so Lookout raises its voice when one is coming up.
//             </p>
//           </div>
//         </Card>
//       </div>
//       <FooterNote />
//     </Shell>
//   );
// }


import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shell, TimeMachine } from '../components/Shell';
import { Card, FooterNote } from '../components/ui';
import { api } from '../lib/api';
import { useAsOf } from '../lib/useAsOf';

const EVENT_LABELS = {
  earnings: 'Earnings',
  fed: 'Fed decision',
  cpi: 'CPI surprise',
  jobs: 'Jobs report',
  oil: 'Oil shock',
  news: 'News mood swing',
  rates: 'Rate move',
  vix: 'VIX move',
};

const EVENT_ORDER = [
  'earnings',
  'fed',
  'cpi',
  'jobs',
  'oil',
  'news',
  'rates',
  'vix',
];

const MACRO_TYPES = new Set([
  'cpi',
  'fed',
  'jobs',
  'oil',
  'rates',
  'vix',
]);

function eventLabel(type) {
  if (EVENT_LABELS[type]) {
    return EVENT_LABELS[type];
  }

  return String(type ?? '')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function reactionWindow(type) {
  return MACRO_TYPES.has(type)
    ? 'on the event day and the next trading day'
    : 'around the event and over the following 5 trading days';
}

function signed(value, digits = 1) {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }

  const n = Number(value);

  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`;
}

function DotsPlot({ events }) {
  const values = (events ?? [])
    .map((event) => Number(event.abnormal_ret_pct))
    .filter((value) => Number.isFinite(value));

  if (!values.length) {
    return (
      <div className="dots-empty">
        No past event-level reactions are available yet.
      </div>
    );
  }

  const maxAbs = Math.max(
    ...values.map((value) => Math.abs(value)),
    1
  );

  const center = 140;
  const span = 118;

  return (
    <svg
      viewBox="0 0 280 90"
      className="dots-plot"
      aria-label="Past event reactions"
    >
      <line
        x1="10"
        y1="44"
        x2="270"
        y2="44"
        stroke="#d2cabd"
      />

      <line
        x1={center}
        y1="12"
        x2={center}
        y2="72"
        stroke="#d2cabd"
      />

      <text x="10" y="84" fontSize="10">
        -{maxAbs.toFixed(1)}%
      </text>

      <text x="137" y="84" fontSize="10">
        0
      </text>

      <text x="244" y="84" fontSize="10">
        +{maxAbs.toFixed(1)}%
      </text>

      {values.map((value, index) => {
        const x = center + (value / maxAbs) * span;
        const y = 24 + (index % 4) * 12;

        return (
          <circle
            key={`${index}-${value}`}
            cx={x}
            cy={y}
            r="4.5"
            fill={value < 0 ? '#d95b2d' : '#2d789e'}
            stroke="#163047"
          />
        );
      })}
    </svg>
  );
}

export default function DriversPage() {
  const navigate = useNavigate();
  const { asOf } = useAsOf();

  const [data, setData] = useState(null);

  const [picked, setPicked] = useState(null);

  const [events, setEvents] = useState([]);

  const [state, setState] = useState('loading');
  // loading | ready | empty | no-data | error

  const [message, setMessage] = useState('');

  const [evidenceLoading, setEvidenceLoading] = useState(false);

  /*
   * -------------------------------------------------------
   * Load sensitivity matrix for CURRENT USER'S PORTFOLIO
   * -------------------------------------------------------
   *
   * We do NOT send tickers here.
   *
   * The backend gets portfolio_id from the auth token,
   * reads the user's holdings from the database,
   * and builds the matrix for those holdings.
   */
  useEffect(() => {
    let cancelled = false;

    setState('loading');
    setMessage('');

    api
      .sensitivity(asOf)
      .then((response) => {
        if (cancelled) {
          return;
        }

        setData(response);

        /*
         * User has no portfolio.
         */
        if (!response.tickers?.length) {
          setPicked(null);
          setState('empty');
          return;
        }

        /*
         * Portfolio exists, but fingerprints haven't been built
         * for these stocks/date yet.
         */
        if (!response.cells?.length) {
          setPicked(null);

          setMessage(
            response.message ??
              'No sensitivity history is available for these holdings yet.'
          );

          setState('no-data');
          return;
        }

        /*
         * Keep current selected square if it still exists.
         *
         * Otherwise select the first valid square returned
         * by the backend.
         */
        setPicked((current) => {
          const stillExists =
            current &&
            response.cells.some(
              (cell) =>
                cell.ticker === current.ticker &&
                cell.event_type === current.eventType
            );

          if (stillExists) {
            return current;
          }

          const first = response.cells[0];

          return {
            ticker: first.ticker,
            eventType: first.event_type,
          };
        });

        setState('ready');
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }

        setMessage(error.message);
        setState('error');
      });

    return () => {
      cancelled = true;
    };
  }, [asOf]);

  /*
   * The sensitivity matrix may actually use the most recent
   * fingerprint snapshot BEFORE asOf.
   *
   * Use that same snapshot date for the evidence dots so the
   * right panel and heatmap are historically consistent.
   */
  const evidenceAsOf =
    data?.fingerprint_as_of ?? asOf;

  /*
   * -------------------------------------------------------
   * Load details for whichever heatmap square is selected.
   * -------------------------------------------------------
   */
  useEffect(() => {
    let cancelled = false;

    setEvents([]);

    if (!picked) {
      return () => {};
    }

    setEvidenceLoading(true);

    api
      .stockEvidence(
        picked.ticker,
        picked.eventType,
        evidenceAsOf
      )
      .then((response) => {
        if (!cancelled) {
          setEvents(response.events ?? []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setEvents([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setEvidenceLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [picked, evidenceAsOf]);

  /*
   * -------------------------------------------------------
   * Transform backend response into heatmap data
   * -------------------------------------------------------
   */

  const cells = data?.cells ?? [];

  const labels = data?.tickers ?? [];

  const cols = useMemo(() => {
    const types = [...(data?.event_types ?? [])];

    return types.sort((a, b) => {
      const ai = EVENT_ORDER.indexOf(a);
      const bi = EVENT_ORDER.indexOf(b);

      if (ai === -1 && bi === -1) {
        return a.localeCompare(b);
      }

      if (ai === -1) {
        return 1;
      }

      if (bi === -1) {
        return -1;
      }

      return ai - bi;
    });
  }, [data]);

  /*
   * Makes lookup easy:
   *
   * "AAPL|earnings" -> cell
   */
  const cellMap = useMemo(
    () =>
      new Map(
        cells.map((cell) => [
          `${cell.ticker}|${cell.event_type}`,
          cell,
        ])
      ),
    [cells]
  );

  const selectedCell = picked
    ? cellMap.get(
        `${picked.ticker}|${picked.eventType}`
      )
    : null;

  /*
   * Used for heatmap color intensity.
   */
  const maxMove = Math.max(
    ...cells.map(
      (cell) =>
        Number(cell.shrunk_move_pct) || 0
    ),
    1
  );

  /*
   * Number shown in top-right memory box.
   */
  const memoryCount = cells.reduce(
    (sum, cell) =>
      sum + (Number(cell.n) || 0),
    0
  );

  /*
   * Find strongest sensitivity values for the
   * explanation underneath the map.
   */
  const ranked = [...cells]
    .filter((cell) =>
      Number.isFinite(
        Number(cell.shrunk_move_pct)
      )
    )
    .sort(
      (a, b) =>
        Number(b.shrunk_move_pct) -
        Number(a.shrunk_move_pct)
    );

  const strongest = ranked[0];

  const secondDistinct = ranked.find(
    (cell) =>
      cell.ticker !== strongest?.ticker
  );

  /*
   * Find biggest individual historical move for
   * selected stock/event.
   */
  const biggestEvent = events.reduce(
    (best, event) => {
      if (event.abnormal_ret_pct == null) {
        return best;
      }

      if (!best) {
        return event;
      }

      return Math.abs(
        Number(event.abnormal_ret_pct)
      ) >
        Math.abs(
          Number(best.abnormal_ret_pct)
        )
        ? event
        : best;
    },
    null
  );

  /*
   * The number of event columns is dynamic now.
   *
   * The old page assumed exactly six columns.
   */
  const gridStyle = {
    gridTemplateColumns: `60px repeat(${Math.max(
      cols.length,
      1
    )}, minmax(72px, 1fr))`,

    minWidth: `${
      60 +
      Math.max(cols.length, 1) * 78
    }px`,
  };

  /*
   * Shell normally shows only TimeMachine.
   *
   * Since this page needs both the memory count AND
   * TimeMachine, we provide both ourselves.
   */
  const headerExtra = (
    <div className="drivers-header-extra">
      <div className="memory-count">
        <b>
          {memoryCount.toLocaleString()}
        </b>

        <span>
          stock × event moments learned
        </span>
      </div>

      <TimeMachine />
    </div>
  );

  /*
   * -------------------------------------------------------
   * Page states
   * -------------------------------------------------------
   */

  if (state === 'loading') {
    return (
      <Shell
        title="What moves my stocks"
        kicker="LOOKOUT'S MEMORY · SINCE JAN 2019"
        headerExtra={headerExtra}
      >
        <div className="page-state">
          Building your stocks&apos;
          sensitivity map…
        </div>
      </Shell>
    );
  }

  if (state === 'error') {
    return (
      <Shell
        title="What moves my stocks"
        kicker="LOOKOUT'S MEMORY · SINCE JAN 2019"
        headerExtra={headerExtra}
      >
        <div className="page-state error">
          <b>
            Couldn&apos;t load your
            sensitivity map.
          </b>

          <span>{message}</span>

          <span className="hint">
            Check that the Flask backend
            is running on port 5000.
          </span>
        </div>
      </Shell>
    );
  }

  if (state === 'empty') {
    return (
      <Shell
        title="What moves my stocks"
        kicker="LOOKOUT'S MEMORY · SINCE JAN 2019"
        headerExtra={headerExtra}
      >
        <div className="page-state">
          <b>No holdings yet.</b>

          <span>
            Add your portfolio first,
            then Lookout can build a
            sensitivity map for those
            stocks.
          </span>

          <button
            className="sign-btn"
            type="button"
            onClick={() =>
              navigate('/onboarding')
            }
          >
            Add holdings →
          </button>
        </div>
      </Shell>
    );
  }

  if (state === 'no-data') {
    return (
      <Shell
        title="What moves my stocks"
        kicker="LOOKOUT'S MEMORY · SINCE JAN 2019"
        headerExtra={headerExtra}
      >
        <div className="page-state">
          <b>
            No fingerprint data for this
            date yet.
          </b>

          <span>{message}</span>
        </div>
      </Shell>
    );
  }

  /*
   * -------------------------------------------------------
   * Main Drivers page
   * -------------------------------------------------------
   */

  return (
    <Shell
      title="What moves my stocks"
      kicker="LOOKOUT'S MEMORY · SINCE JAN 2019"
      subtitle="Past events lined up against how the stocks you currently own reacted. Darker means a bigger measured reaction. Tap any square."
      headerExtra={headerExtra}
    >
      <div className="steps-row">
        {[
          [
            '1',
            'Bots log every event.',
            'Earnings, Fed days, CPI prints, oil shocks, and news-mood swings.',
          ],
          [
            '2',
            'Lookout measures what happened next',
            'over the event window appropriate for that kind of event.',
          ],
          [
            '3',
            "That becomes each stock's fingerprint,",
            'which decides how loud an alert should be.',
          ],
        ].map((step) => (
          <div
            className="step-box dashed"
            key={step[0]}
          >
            <b>{step[0]}</b>

            <p>
              <strong>{step[1]}</strong>{' '}
              {step[2]}
            </p>
          </div>
        ))}
      </div>

      <div className="drivers-layout">
        {/* LEFT: HEATMAP */}
        <Card className="map-card">
          <div className="map-title">
            <h2>Sensitivity map</h2>

            <span className="heat-legend">
              calm
              <i />
              <i />
              <i />
              <i />
              <i />
              big moves
            </span>
          </div>

          <div className="heat-scroll">
            <div
              className="heat-grid"
              style={gridStyle}
            >
              {/* Empty top-left cell */}
              <div />

              {/* Column headings */}
              {cols.map((eventType) => (
                <b key={eventType}>
                  {eventLabel(eventType)}
                </b>
              ))}

              {/* Stock rows */}
              {labels.flatMap((ticker) => [
                <strong
                  key={`label-${ticker}`}
                >
                  {ticker}
                </strong>,

                ...cols.map((eventType) => {
                  const cell = cellMap.get(
                    `${ticker}|${eventType}`
                  );

                  /*
                   * Stock exists in portfolio,
                   * but no fingerprint exists for
                   * this stock/event combination.
                   */
                  if (!cell) {
                    return (
                      <button
                        type="button"
                        className="missing"
                        key={`${ticker}-${eventType}`}
                        disabled
                        title="Not enough past events to estimate this reaction yet"
                      >
                        —
                      </button>
                    );
                  }

                  const value =
                    Number(
                      cell.shrunk_move_pct
                    ) || 0;

                  /*
                   * Scale blue intensity relative
                   * to biggest reaction in user's
                   * current portfolio.
                   */
                  const alpha =
                    0.12 +
                    Math.min(
                      1,
                      value / maxMove
                    ) *
                      0.88;

                  const selected =
                    picked?.ticker ===
                      ticker &&
                    picked?.eventType ===
                      eventType;

                  return (
                    <button
                      type="button"
                      className={
                        selected
                          ? 'selected'
                          : ''
                      }
                      key={`${ticker}-${eventType}`}
                      style={{
                        background: `rgba(32, 119, 163, ${alpha})`,
                        color:
                          alpha > 0.58
                            ? 'white'
                            : '#162b42',
                      }}
                      title={`${cell.n} past events · ordinary comparable move ±${cell.baseline_move_pct}%`}
                      onClick={() =>
                        setPicked({
                          ticker,
                          eventType,
                        })
                      }
                    >
                      ±{value.toFixed(1)}
                    </button>
                  );
                }),
              ])}
            </div>
          </div>

          {strongest && (
            <div className="callout blue">
              <b>
                The largest measured
                reaction in your current
                holdings is{' '}
                {strongest.ticker} on{' '}
                {eventLabel(
                  strongest.event_type
                ).toLowerCase()}{' '}
                days: ±
                {Number(
                  strongest.shrunk_move_pct
                ).toFixed(1)}
                %.
              </b>{' '}

              {secondDistinct && (
                <>
                  Next,{' '}
                  {
                    secondDistinct.ticker
                  }{' '}
                  reacts most to{' '}
                  {eventLabel(
                    secondDistinct.event_type
                  ).toLowerCase()}{' '}
                  at ±
                  {Number(
                    secondDistinct.shrunk_move_pct
                  ).toFixed(1)}
                  %.
                </>
              )}
            </div>
          )}
        </Card>

        {/* RIGHT: SELECTED CELL DETAILS */}
        <Card className="picked-card">
          {!selectedCell ? (
            <div className="page-state">
              Pick a measured square to
              inspect it.
            </div>
          ) : (
            <>
              <div className="eyebrow">
                YOU PICKED
              </div>

              <h2>
                {selectedCell.ticker} on{' '}
                {eventLabel(
                  selectedCell.event_type
                ).toLowerCase()}{' '}
                days
              </h2>

              <div className="picked-value">
                ±
                {Number(
                  selectedCell.shrunk_move_pct
                ).toFixed(1)}
                %{' '}
                <span>
                  typical measured move
                </span>
              </div>

              <div className="picked-stats">
                <div>
                  <b>
                    {selectedCell.n}
                  </b>

                  <span>
                    past events
                  </span>
                </div>

                <div>
                  <b>
                    {biggestEvent
                      ? signed(
                          biggestEvent.abnormal_ret_pct
                        )
                      : '—'}
                  </b>

                  <span>
                    biggest move
                  </span>
                </div>

                <div>
                  <b>
                    {selectedCell.share_up ==
                    null
                      ? '—'
                      : `${Math.round(
                          Number(
                            selectedCell.share_up
                          ) * 100
                        )}%`}
                  </b>

                  <span>
                    went up after
                  </span>
                </div>
              </div>

              <div className="picked-meta">
                Ordinary comparable move:{' '}
                <b>
                  ±
                  {Number(
                    selectedCell.baseline_move_pct
                  ).toFixed(1)}
                  %
                </b>

                {selectedCell.vs_baseline !=
                  null && (
                  <span>
                    {' '}
                    ·{' '}
                    {Number(
                      selectedCell.vs_baseline
                    ).toFixed(1)}
                    × baseline
                  </span>
                )}
              </div>

              <h4>
                Every past event, one dot
                each
              </h4>

              {evidenceLoading ? (
                <div className="dots-empty">
                  Loading past events…
                </div>
              ) : (
                <DotsPlot
                  events={events}
                />
              )}

              <div className="dashed plain-box">
                <div className="eyebrow">
                  IN PLAIN ENGLISH
                </div>

                <p>
                  {selectedCell.ticker}{' '}
                  has typically moved about{' '}
                  {Number(
                    selectedCell.shrunk_move_pct
                  ).toFixed(1)}
                  %{' '}
                  {reactionWindow(
                    selectedCell.event_type
                  )}{' '}
                  when this kind of event
                  occurred. That estimate
                  comes from{' '}
                  {selectedCell.n} usable
                  past events
                  {selectedCell.reliable
                    ? ' and is strong enough to stand out from its ordinary movement.'
                    : '; treat it as a pattern with limited statistical separation from ordinary movement.'}
                </p>
              </div>
            </>
          )}
        </Card>
      </div>

      <FooterNote />
    </Shell>
  );
}