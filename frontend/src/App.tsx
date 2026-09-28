import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/layout/Layout";
import DashboardPage from "./pages/DashboardPage";
import ReviewPage from "./pages/ReviewPage";
import IssuesPage from "./pages/IssuesPage";
import ChangesPage from "./pages/ChangesPage";
import MetricsPage from "./pages/MetricsPage";
import HistoryPage from "./pages/HistoryPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/review/:id" element={<ReviewPage />} />
        <Route path="/reviews/:id" element={<ReviewPage />} />
        <Route path="/issues" element={<IssuesPage />} />
        <Route path="/changes" element={<ChangesPage />} />
        <Route path="/metrics" element={<MetricsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
