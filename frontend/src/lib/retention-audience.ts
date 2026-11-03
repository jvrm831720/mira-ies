/** Helpers de público de retenção originado de grupo virtual. */

import { api } from "@/lib/api";

const MAX_PAGES = 10;
const PAGE_SIZE = 100;

export async function loadGroupMemberIds(groupId: string): Promise<{
  ids: string[];
  truncated: boolean;
  pagesLoaded: number;
}> {
  const ids: string[] = [];
  let cursor: string | null | undefined = null;
  let pagesLoaded = 0;
  let truncated = false;

  for (let i = 0; i < MAX_PAGES; i++) {
    const page = await api.studentGroupMembers(groupId, {
      limit: PAGE_SIZE,
      cursor: cursor || undefined,
    });
    pagesLoaded += 1;
    for (const m of page.members) {
      ids.push(m.student_id);
    }
    if (page.truncated) truncated = true;
    if (!page.next_cursor || page.has_more === false) break;
    cursor = page.next_cursor;
    if (i === MAX_PAGES - 1 && page.has_more) truncated = true;
  }

  return { ids: [...new Set(ids)], truncated, pagesLoaded };
}
