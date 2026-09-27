/**
 * The time machine, stored in the URL (?as_of=YYYY-MM-DD).
 *
 * Keeping it in the URL rather than component state means a replayed day
 * survives a refresh, can be linked to, and every page reads the same
 * date without prop-drilling. No parameter at all means "live": the
 * backend then defaults to today.
 */
import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

const DAY = 86400000;

export function useAsOf() {
  const [params, setParams] = useSearchParams();
  const asOf = params.get('as_of');          // null = live

  const setAsOf = useCallback(
    (value) => {
      const next = new URLSearchParams(params);
      if (value) next.set('as_of', value);
      else next.delete('as_of');
      setParams(next, { replace: true });
    },
    [params, setParams]
  );

  const shift = useCallback(
    (days) => {
      const base = asOf ? new Date(`${asOf}T12:00:00`) : new Date();
      const moved = new Date(base.getTime() + days * DAY);
      setAsOf(moved.toISOString().slice(0, 10));
    },
    [asOf, setAsOf]
  );

  return { asOf, setAsOf, shift, isLive: !asOf };
}

export function formatDay(iso) {
  const d = iso ? new Date(`${iso}T12:00:00`) : new Date();
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function formatLongDay(iso) {
  const d = iso ? new Date(`${iso}T12:00:00`) : new Date();
  return d
    .toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' })
    .toUpperCase();
}