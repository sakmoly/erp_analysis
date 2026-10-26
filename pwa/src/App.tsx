import { Navigate, Route, Routes } from "react-router-dom";
import { getAccessToken } from "./lib/auth";
import { LoginPage } from "./pages/LoginPage";
import { OAuthPage } from "./pages/OAuthPage";
import { HomePage } from "./pages/HomePage";
import { BoardPage } from "./pages/BoardPage";

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!getAccessToken()) return <Navigate to="/login" replace />;
  return children;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/oauth" element={<OAuthPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <HomePage />
          </RequireAuth>
        }
      />
      <Route
        path="/board/:boardId"
        element={
          <RequireAuth>
            <BoardPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
