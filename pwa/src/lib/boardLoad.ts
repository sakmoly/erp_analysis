import { BoardDataPayload, fetchBoardData, fetchMyAccess } from "./dashboard";
import { ApiError } from "./frappe";
import {
  cacheGetStale,
  cacheKey,
  cacheWrite,
  formatCacheAge,
} from "./localCache";

const ACCESS_STALE_MS = 7 * 24 * 60 * 60 * 1000;
const BOARD_STALE_MS = 7 * 24 * 60 * 60 * 1000;

export type AccessSnapshot = {
  scope?: {
    company?: string;
    view_territories?: string[];
    territories?: string[];
  };
};

export type BoardLoadResult = {
  company: string;
  territories: string[];
  board: BoardDataPayload;
  fromCache: boolean;
  cacheLabel: string | null;
};

function accessCacheKey(email: string): string {
  return cacheKey("access", email.toLowerCase());
}

function boardCacheKey(
  email: string,
  dashboardId: string,
  period: string,
  territory: string,
): string {
  return cacheKey("board", email.toLowerCase(), dashboardId, period, territory);
}

export function readCachedBoardLoad(
  email: string,
  dashboardId: string,
  period: string,
  territory: string,
): Omit<BoardLoadResult, "board"> & { board: BoardDataPayload | null } | null {
  const accessHit = cacheGetStale<AccessSnapshot>(accessCacheKey(email), ACCESS_STALE_MS);
  const boardHit = cacheGetStale<BoardDataPayload>(
    boardCacheKey(email, dashboardId, period, territory),
    BOARD_STALE_MS,
  );
  if (!accessHit?.data.scope?.company || !boardHit) return null;
  return {
    company: accessHit.data.scope.company,
    territories:
      accessHit.data.scope.view_territories || accessHit.data.scope.territories || [],
    board: boardHit.data,
    fromCache: true,
    cacheLabel: formatCacheAge(boardHit.savedAt),
  };
}

/** Show cached JSON immediately when available; always revalidate unless refresh forces server refresh. */
export async function loadBoardWithLocalCache(options: {
  email: string;
  dashboardId: string;
  period: string;
  territory: string;
  refresh: boolean;
  onCached?: (partial: BoardLoadResult) => void;
}): Promise<BoardLoadResult> {
  const { email, dashboardId, period, territory, refresh, onCached } = options;

  if (!refresh) {
    const cached = readCachedBoardLoad(email, dashboardId, period, territory);
    if (cached?.board) {
      onCached?.({
        company: cached.company,
        territories: cached.territories,
        board: cached.board,
        fromCache: true,
        cacheLabel: cached.cacheLabel,
      });
    }
  }

  const access = await fetchMyAccess();
  cacheWrite(accessCacheKey(email), access);
  const company = access.scope?.company;
  if (!company) throw new ApiError("No company on Access Profile");

  const territories = access.scope?.view_territories || access.scope?.territories || [];

  const board = await fetchBoardData(dashboardId, company, {
    refresh,
    period,
    territory,
  });
  cacheWrite(boardCacheKey(email, dashboardId, period, territory), board);

  return {
    company,
    territories,
    board,
    fromCache: false,
    cacheLabel: null,
  };
}
