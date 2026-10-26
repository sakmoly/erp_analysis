export type AccessProfileLine = {
  access_object?: string;
  object_key?: string;
  can_view?: boolean;
  active?: boolean;
};

export type MyAccessPayload = {
  scope?: Record<string, unknown>;
  profiles?: AccessProfileLine[];
};

export function canViewObject(
  profiles: AccessProfileLine[] | undefined,
  registryKey: string,
): boolean {
  if (!profiles?.length) return true;
  const line = profiles.find((p) => p.object_key === registryKey && p.active !== false);
  if (!line) return false;
  return Boolean(line.can_view);
}

export const PWA_BOARD_MENU_KEYS: Record<string, string> = {
  sales_overview: "menu_sales_performance",
  receivables_overview: "menu_receivables",
  inventory_overview: "menu_inventory",
};
