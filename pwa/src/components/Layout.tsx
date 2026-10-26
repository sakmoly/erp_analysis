import { ReactNode } from "react";
import { clearSession } from "../lib/auth";
import { useNavigate } from "react-router-dom";

type Props = {
  title: string;
  subtitle?: string;
  children: ReactNode;
};

export function Layout({ title, subtitle, children }: Props) {
  const navigate = useNavigate();

  function logout() {
    clearSession();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>{title}</h1>
          {subtitle ? <div className="sub">{subtitle}</div> : null}
        </div>
        <button type="button" className="btn-ghost" onClick={logout}>
          Log out
        </button>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
