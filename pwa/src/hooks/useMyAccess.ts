import { useEffect, useState } from "react";
import { fetchMyAccess } from "../lib/dashboard";
import { AccessProfileLine } from "../lib/access";

export function useMyAccess(enabled: boolean) {
  const [profiles, setProfiles] = useState<AccessProfileLine[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    void fetchMyAccess()
      .then((data) => {
        if (!cancelled) {
          setProfiles((data.profiles as AccessProfileLine[]) || []);
          setReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { profiles, ready };
}
