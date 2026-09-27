# Lookout — Portfolio Watch React Frontend

Frontend-only React recreation of the “Portfolio Watch UI Demo” PDF.

## Run locally

```bash
npm install
npm run dev
```

## Pages (`src/pages/`)

| Route | File | Screen |
| --- | --- | --- |
| `/login` | `LoginPage.jsx` | Welcome / sign-in |
| `/onboarding` | `OnboardingPage.jsx` | Add holdings |
| `/overview` | `OverviewPage.jsx` | Overview |
| `/signals` | `SignalsPage.jsx` | Signal log |
| `/course` | `CoursePage.jsx` | Portfolio Recommendations |
| `/holdings` | `HoldingsPage.jsx` | All Stock Holdings Fundamentals|
| `/weather` | `WeatherPage.jsx` | Macro Economic Report |
| `/drivers` | `DriversPage.jsx` | What moves my stocks |

Shared shell/UI lives in `src/components/`. Demo portfolio data is in `src/data/portfolio.js` so you can swap it for API calls later.

## Notes

- Frontend only — static demo data, light UI interactions for navigation and selection.
- Layout, palette, and charts are tuned to the PDF reference.
