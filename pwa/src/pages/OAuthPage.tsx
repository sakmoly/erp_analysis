import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

/**
 * OAuth redirect target: https://printechs.com/mobile/oauth
 * Phase 2a uses password grant on the login form; this route is reserved
 * for authorization-code flow later.
 */
export function OAuthPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  useEffect(() => {
    const code = params.get("code");
    const error = params.get("error");
    if (error) {
      navigate("/login", { replace: true, state: { oauthError: error } });
      return;
    }
    if (code) {
      navigate("/login", { replace: true, state: { oauthCode: code } });
      return;
    }
    navigate("/login", { replace: true });
  }, [navigate, params]);

  return <div className="loading">Completing sign-in…</div>;
}
