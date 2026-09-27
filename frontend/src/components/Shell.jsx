import { ChevronLeft, ChevronRight, Radio } from 'lucide-react';
import { NarratorNotice } from './NarratorNotice';
import { Sidebar } from './Sidebar';
import { formatDay, formatLongDay, useAsOf } from '../lib/useAsOf';

export function TimeMachine() {
  const { asOf, setAsOf, shift, isLive } = useAsOf();

  return (
    <div className={`time-machine ${isLive ? '' : 'replaying'}`}>
      <span className="eyebrow">{isLive ? 'LIVE' : 'TIME MACHINE'}</span>
      <button className="circle-btn" type="button" aria-label="Previous day" onClick={() => shift(-1)}>
        <ChevronLeft size={15} />
      </button>
      {/* a real date input: click the text to jump anywhere */}
      <input
        className="tm-date"
        type="date"
        value={asOf ?? new Date().toISOString().slice(0, 10)}
        onChange={(e) => setAsOf(e.target.value)}
        aria-label="Date to view"
      />
      <button className="circle-btn" type="button" aria-label="Next day" onClick={() => shift(1)}>
        <ChevronRight size={15} />
      </button>
      {isLive ? (
        <span className="tm-live">
          <Radio size={13} /> today
        </span>
      ) : (
        <button className="play-btn" type="button" onClick={() => setAsOf(null)}>
          Back to live
        </button>
      )}
    </div>
  );
}

export function Shell({ title, kicker, subtitle, children, headerExtra = null }) {
  const { asOf } = useAsOf();

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-pane">
        <div className="topline">
          <div className="topline-copy">
            <div className="eyebrow kicker">{kicker ?? formatLongDay(asOf)}</div>
            <h1 className="page-title">{title}</h1>
            {subtitle && <p className="page-subtitle">{subtitle}</p>}
          </div>
          {headerExtra ?? <TimeMachine />}
        </div>
        <NarratorNotice />
        {asOf && (
          <div className="replay-banner">
            Replaying history: Lookout is acting as if today is {formatDay(asOf)}. Every alert fires
            exactly as it would have that day.
          </div>
        )}
        {children}
      </main>
    </div>
  );
}