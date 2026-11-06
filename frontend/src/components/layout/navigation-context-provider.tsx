"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import type { ObjectDefaultView, ObjectField } from "@/components/object-index/object-index-types";
import { initialObjectIndexState, type ObjectIndexState } from "@/components/object-index/object-index";
import { buildIndexHref, navigationFingerprint, readObjectIndexState, readRecordId } from "@/lib/navigation-context";

const PREFIX = "mira:navigation:scroll:v1:";
const MAX_AGE = 30 * 60 * 1000;

type NavigationScrollContext = {
  rememberScroll: (scope: string, href: string) => void;
  readScroll: (scope: string, href: string) => number | null;
  clearScroll: () => void;
};

const Context = createContext<NavigationScrollContext | null>(null);

export function NavigationContextProvider({ children }: { children: ReactNode }) {
  const rememberScroll = useCallback((scope: string, href: string) => {
    if (!scope || typeof window === "undefined") return;
    try {
      const key = PREFIX + navigationFingerprint(scope, href);
      window.sessionStorage.setItem(key, JSON.stringify({ y: window.scrollY, at: Date.now() }));
    } catch { /* Session storage can be unavailable; navigation still works. */ }
  }, []);
  const readScroll = useCallback((scope: string, href: string): number | null => {
    if (!scope || typeof window === "undefined") return null;
    try {
      const key = PREFIX + navigationFingerprint(scope, href);
      const raw = window.sessionStorage.getItem(key);
      if (!raw) return null;
      const parsed: unknown = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return null;
      const position = parsed as { y?: unknown; at?: unknown };
      if (typeof position.y !== "number" || !Number.isFinite(position.y) ||
        position.y < 0 || typeof position.at !== "number" ||
        Date.now() - position.at > MAX_AGE) {
        window.sessionStorage.removeItem(key);
        return null;
      }
      return position.y;
    } catch { return null; }
  }, []);
  const clearScroll = useCallback(() => {
    if (typeof window === "undefined") return;
    try {
      for (let i = window.sessionStorage.length - 1; i >= 0; i--) {
        const key = window.sessionStorage.key(i);
        if (key?.startsWith(PREFIX)) window.sessionStorage.removeItem(key);
      }
    } catch { /* No persistent state required to navigate. */ }
  }, []);
  return <Context.Provider value={{ rememberScroll, readScroll, clearScroll }}>{children}</Context.Provider>;
}

export function useNavigationContext(): NavigationScrollContext {
  const context = useContext(Context);
  if (!context) throw new Error("NavigationContextProvider is required");
  return context;
}

/**
 * Object Index URL navigation shared by Alunos and Cobrança.
 * URL: view/search/filters/sort/columns/page/selected record; session: scroll only.
 * URL state is not trusted authorization and never contains full record payloads.
 */
export function useObjectNavigationState<T>(options: {
  fields: ObjectField<T>[];
  views: ObjectDefaultView[];
  tenantId?: string | null;
  userId?: string | null;
  ready?: boolean;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const signature = searchParams.toString();
  const { rememberScroll, clearScroll } = useNavigationContext();
  const initial = () => initialObjectIndexState(options.fields);
  const [state, setState] = useState<ObjectIndexState>(() =>
    readObjectIndexState(new URLSearchParams(signature), options.fields, options.views, initial()));
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    readRecordId(new URLSearchParams(signature)));
  const lastSignature = useRef(signature);
  const lastScope = useRef("");
  const restored = useRef("");
  const scope = options.tenantId && options.userId ? options.tenantId + ":" + options.userId : "";

  // Browser Back/Forward, deep links and native history navigation are authoritative.
  useEffect(() => {
    if (lastSignature.current === signature) return;
    lastSignature.current = signature;
    const params = new URLSearchParams(signature);
    setState(readObjectIndexState(params, options.fields, options.views, initial()));
    setSelectedId(readRecordId(params));
    // fields/views are intentionally stable definitions supplied by each object adapter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  // A workspace switch must never carry a previous tenant's selection or scroll cache.
  useEffect(() => {
    if (!scope) return;
    if (lastScope.current && lastScope.current !== scope) {
      clearScroll();
      const reset = initial();
      setState(reset);
      setSelectedId(null);
      const url = buildIndexHref(pathname, new URLSearchParams(window.location.search), reset, null);
      window.history.replaceState(window.history.state, "", url);
      lastSignature.current = new URL(url, window.location.origin).searchParams.toString();
      restored.current = "";
    }
    lastScope.current = scope;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, pathname, clearScroll]);

  const listingHref = buildIndexHref(pathname, new URLSearchParams(signature), state, null);

  function onStateChange(next: ObjectIndexState) {
    setState(next);
    setSelectedId(null);
    const href = buildIndexHref(pathname, new URLSearchParams(window.location.search), next, null);
    lastSignature.current = new URL(href, window.location.origin).searchParams.toString();
    window.history.replaceState(window.history.state, "", href);
    restored.current = scope + "|" + href; // New filters should not jump to an old scroll offset.
  }

  function openRecord(id: string) {
    const test = new URLSearchParams({ record: id });
    if (!readRecordId(test)) return;
    if (scope) rememberScroll(scope, listingHref);
    setSelectedId(id);
    const href = buildIndexHref(pathname, new URLSearchParams(window.location.search), state, id);
    lastSignature.current = new URL(href, window.location.origin).searchParams.toString();
    window.history.pushState(window.history.state, "", href);
  }

  function closeRecord() {
    setSelectedId(null);
    const href = buildIndexHref(pathname, new URLSearchParams(window.location.search), state, null);
    lastSignature.current = new URL(href, window.location.origin).searchParams.toString();
    window.history.replaceState(window.history.state, "", href);
  }

  return { state, onStateChange, selectedId, openRecord, closeRecord, listingHref };
}

/** Restore the list only after authorized rows are rendered; never restore across tenants. */
export function useObjectScrollRestoration(options: {
  tenantId?: string | null;
  userId?: string | null;
  listingHref: string;
  ready: boolean;
  selectedId: string | null;
}) {
  const { readScroll } = useNavigationContext();
  const restored = useRef("");
  const scope = options.tenantId && options.userId ? options.tenantId + ":" + options.userId : "";
  useEffect(() => {
    if (!scope || !options.ready || options.selectedId) return;
    const key = scope + "|" + options.listingHref;
    if (restored.current === key) return;
    restored.current = key;
    const y = readScroll(scope, options.listingHref);
    if (y === null) return;
    let second = 0;
    const first = window.requestAnimationFrame(() => {
      second = window.requestAnimationFrame(() => window.scrollTo({ top: y, behavior: "auto" }));
    });
    return () => { window.cancelAnimationFrame(first); if (second) window.cancelAnimationFrame(second); };
  }, [scope, options.ready, options.selectedId, options.listingHref, readScroll]);
}
