import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Toaster } from "@/components/ui/sonner";

import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import Dashboard from "@/pages/Dashboard";
import Deals from "@/pages/Deals";
import DealDetail from "@/pages/DealDetail";
import Upload from "@/pages/Upload";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--cv-bg)] font-mono text-sm text-[var(--cv-muted)]">
        booting clearvault…
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function Public({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/dashboard" replace />;
  return children;
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route
              path="/login"
              element={
                <Public>
                  <Login />
                </Public>
              }
            />
            <Route
              path="/signup"
              element={
                <Public>
                  <Signup />
                </Public>
              }
            />
            <Route
              path="/dashboard"
              element={
                <Protected>
                  <Dashboard />
                </Protected>
              }
            />
            <Route
              path="/deals"
              element={
                <Protected>
                  <Deals />
                </Protected>
              }
            />
            <Route
              path="/deals/:id"
              element={
                <Protected>
                  <DealDetail />
                </Protected>
              }
            />
            <Route
              path="/upload"
              element={
                <Protected>
                  <Upload />
                </Protected>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <Toaster position="bottom-right" theme="dark" />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
