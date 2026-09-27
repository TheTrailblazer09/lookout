import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, RequireAuth } from './lib/auth';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import OnboardingPage from './pages/OnboardingPage';
import OverviewPage from './pages/OverviewPage';
import SignalsPage from './pages/SignalsPage';
import CoursePage from './pages/CoursePage';
import HoldingsPage from './pages/HoldingsPage';
import WeatherPage from './pages/WeatherPage';
import DriversPage from './pages/DriversPage';

/**
 * Signed-out visitors can still reach the app pages: the backend serves the
 * shared demo portfolio when no token is sent, which is what lets a judge
 * click straight in. Only /onboarding is gated, because saving holdings
 * needs somewhere to save them to.
 */
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route
          path="/onboarding"
          element={
            <RequireAuth>
              <OnboardingPage />
            </RequireAuth>
          }
        />
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/signals" element={<SignalsPage />} />
        <Route path="/course" element={<CoursePage />} />
        <Route path="/holdings" element={<HoldingsPage />} />
        <Route path="/weather" element={<WeatherPage />} />
        <Route path="/drivers" element={<DriversPage />} />
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </AuthProvider>
  );
}