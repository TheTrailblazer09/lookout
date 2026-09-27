/**
 * The numbers the sidebar shows: how many holdings, how many bots are on,
 * how many alerts are waiting.
 *
 * Refetches whenever the route changes, so saving holdings in onboarding is
 * reflected the moment you land back on a page. Each piece is fetched
 * independently: alerts may legitimately be empty (nobody has run
 * `flask alerts` yet) and that must not blank out the holdings count.
 */
import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { api } from './api';

export function useSummary() {
  const location = useLocation();
  const [summary, setSummary] = useState({
    holdings: null,
    totalValue: null,
    bots: null,
    alerts: null,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;
    const next = {};

    const jobs = [
      api
        .getPortfolio()
        .then((d) => {
          next.holdings = d.holdings?.length ?? 0;
          next.totalValue = d.total_value ?? 0;
        })
        .catch(() => {}),
      api
        .getPreferences()
        .then((p) => {
          next.bots = p.bots?.length ?? null;
        })
        .catch(() => {}),
      api
        .alerts()
        .then((d) => {
          next.alerts = d.count ?? 0;
        })
        .catch(() => {}),
    ];

    Promise.allSettled(jobs).then(() => {
      if (!cancelled) setSummary({ ...next, loading: false });
    });
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  return summary;
}