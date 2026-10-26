import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginWithPassword } from "../lib/auth";
import { ApiError } from "../lib/frappe";
import { isPilotUser } from "../lib/config";

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (!isPilotUser(email)) {
        setError("PWA pilot is limited to approved users. Contact IT to request access.");
        setLoading(false);
        return;
      }
      const session = await loginWithPassword(email, password);
      if (!isPilotUser(session.email)) {
        setError("Your account is not enabled for the web pilot.");
        setLoading(false);
        return;
      }
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>Printechs</h1>
          <div className="sub">Business Insight · Web</div>
        </div>
      </header>
      <main className="app-main">
        <div className="login-card">
          <h2>Sign in</h2>
          <p>Same credentials as the mobile app (ERPNext user).</p>
          {error ? <div className="error-banner">{error}</div> : null}
          <form onSubmit={onSubmit}>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
