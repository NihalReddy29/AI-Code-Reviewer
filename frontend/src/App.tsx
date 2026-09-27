import { NavLink, Route, Routes } from "react-router-dom";

import DashboardPage from "./pages/DashboardPage";
import ReviewPage from "./pages/ReviewPage";

export default function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand">
          AI Code Reviewer
        </NavLink>
        <nav>
          <NavLink to="/" end>
            Reviews
          </NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/reviews/:id" element={<ReviewPage />} />
        </Routes>
      </main>
    </div>
  );
}
