/**
 * One place that talks to Flask.
 *
 * Every call goes through request(), so the token header, JSON parsing and
 * error shape are handled once. The backend always answers errors as
 * { error: { message, status } }, which is why ApiError can carry a
 * message worth showing the user instead of "Request failed".
 */
const TOKEN_KEY = 'lookout.token';

// In dev, vite proxies /api to Flask (see vite.config.js), so the browser
// makes same-origin requests and CORS never enters the picture.
const BASE = import.meta.env.VITE_API_BASE ?? '/api';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = tokenStore.get();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // fetch only rejects when the request never happened
    throw new ApiError('Cannot reach the server. Is the backend running?', 0);
  }

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const message = data?.error?.message ?? `Request failed (${res.status})`;
    if (res.status === 401 && auth) tokenStore.clear();   // stale token
    throw new ApiError(message, res.status);
  }
  return data;
}

export const api = {
  register: (email, password, displayName) =>
    request('/auth/register', {
      method: 'POST',
      auth: false,
      body: { email, password, display_name: displayName },
    }),
  login: (email, password) =>
    request('/auth/login', { method: 'POST', auth: false, body: { email, password } }),
  me: () => request('/auth/me'),
  health: () => request('/health', { auth: false }),

  getPortfolio: (asOf) => request(`/portfolio${asOf ? `?as_of=${asOf}` : ''}`),
  savePortfolio: (holdings) => request('/portfolio', { method: 'PUT', body: { holdings } }),
  searchTickers: (q) => request(`/tickers/search?q=${encodeURIComponent(q)}`),

  // last close for one ticker, used to price a holding as it is typed
  lastPrice: async (ticker) => {
    const d = await request(`/stocks/${encodeURIComponent(ticker)}/prices?days=1`);
    const row = d.prices?.[d.prices.length - 1];
    return row ? { price: row.adj_close, date: row.date } : null;
  },
  // written separately from /overview so the page never waits on a model
  generateRead: (asOf) =>
    request(`/overview/read${asOf ? `?as_of=${asOf}` : ''}`, { method: 'POST', body: {} }),

  llmStatus: () => request('/llm/status'),
  llmEnsure: () => request('/llm/ensure', { method: 'POST', body: {} }),

  getPreferences: () => request('/preferences'),
  savePreferences: (prefs) => request('/preferences', { method: 'PUT', body: prefs }),

  overview: (asOf) => request(`/overview${asOf ? `?as_of=${asOf}` : ''}`),
  alerts: (asOf, category) => {
    const p = new URLSearchParams();
    if (asOf) p.set('as_of', asOf);
    if (category) p.set('category', category);
    const qs = p.toString();
    return request(`/alerts${qs ? `?${qs}` : ''}`);
  },
  alert: (id) => request(`/alerts/${id}`),
  alertFeedback: (id, vote) =>
    request(`/alerts/${id}/feedback`, { method: 'POST', body: { vote } }),
  stockDetail: (ticker, asOf) =>
    request(`/stocks/${encodeURIComponent(ticker)}/detail${asOf ? `?as_of=${asOf}` : ''}`),

  weather: (asOf) => request(`/weather${asOf ? `?as_of=${asOf}` : ''}`),
  weatherForecast: (asOf) =>
    request(`/weather/forecast${asOf ? `?as_of=${asOf}` : ''}`, { method: 'POST', body: {} }),

  planIdeas: (asOf) => request(`/plan/ideas${asOf ? `?as_of=${asOf}` : ''}`),
  planSimulate: (asOf, ideas) =>
    request(`/plan/simulate${asOf ? `?as_of=${asOf}` : ''}`, { method: 'POST', body: { ideas } }),

  sensitivity: (asOf) => request(`/sensitivity${asOf ? `?as_of=${asOf}` : ''}`),
  stockEvidence: (
    ticker,
    eventType,
    asOf,
    limit = 500
  ) => {
    const params = new URLSearchParams();

    if (asOf) {
      params.set('as_of', asOf);
    }

    if (eventType) {
      params.set(
        'event_type',
        eventType
      );
    }

    params.set(
      'limit',
      String(limit)
    );

    return request(
      `/stocks/${encodeURIComponent(
        ticker
      )}/evidence?${params.toString()}`
    );
  },
};



 