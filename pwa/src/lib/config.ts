/** API origin — empty string = same host as the PWA (production). */
export function apiBase(): string {
  return (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
}

const defaultPilot = "sakeer@printechs.com,raheem@printechs.com";

export function pilotEmails(): Set<string> {
  const raw = import.meta.env.VITE_PILOT_EMAILS || defaultPilot;
  return new Set(
    raw
      .split(",")
      .map((e) => e.trim().toLowerCase())
      .filter(Boolean),
  );
}

export function isPilotUser(email: string | undefined): boolean {
  if (!email) return false;
  const pilots = pilotEmails();
  if (pilots.has("*")) return true;
  return pilots.has(email.trim().toLowerCase());
}
