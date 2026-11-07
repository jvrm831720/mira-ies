"use client";

import { useState } from "react";
import Image from "next/image";
import type { CatalogApp } from "./apps-catalog-model";
import { profileFor } from "./apps-brand-profiles";

/** Keep local artwork first; fall back to the vendor's actual favicon, never a guessed domain. */
const localLogos: Record<string, string> = {
  whatsapp: "/apps/whatsapp.svg",
  gmail: "/apps/gmail.svg",
  googlecalendar: "/apps/googlecalendar.svg",
  googledrive: "/apps/googledrive.svg",
  googlesheets: "/apps/googlesheets.svg",
  moodle: "/apps/moodle.svg",
  canvas: "/apps/canvas.svg",
  zapier: "/apps/zapier.svg",
};

function safeHttpsUrl(value?: string | null): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.toString() : undefined;
  } catch { return undefined; }
}

export function logoSourcesFor(item: Pick<CatalogApp, "id" | "logoUrl" | "website">): string[] {
  const profile = profileFor(item.id);
  const sources: string[] = [];
  if (localLogos[item.id]) sources.push(localLogos[item.id]);
  const remoteLogo = safeHttpsUrl(item.logoUrl);
  if (remoteLogo) sources.push(remoteLogo);
  // The icon set only accepts normalized slugs; remote toolkit names are untrusted.
  const simpleIcon = profile?.logo || item.id;
  if (/^[a-z0-9]+$/.test(simpleIcon)) sources.push(`https://cdn.simpleicons.org/${simpleIcon}`);
  const site = safeHttpsUrl(profile?.website) || safeHttpsUrl(item.website);
  if (site) {
    const domain = new URL(site).hostname;
    sources.push(`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128`);
  }
  return [...new Set(sources)];
}

export function AppBrandIcon({item, large = false}: {item: CatalogApp; large?: boolean}) {
  const [sourceIndex, setSourceIndex] = useState(0);
  const sources = logoSourcesFor(item);
  const source = sources[sourceIndex];
  const dimension = large ? 52 : 30;
  return (
    <span className={"grid shrink-0 place-items-center overflow-hidden rounded-2xl border border-[var(--mira-apps-border)] bg-white " +
      (large ? "h-20 w-20" : "h-12 w-12")} aria-label={`Identidade visual de ${item.name}`} role="img">
      {source ? source.startsWith("/") ?
        <Image src={source} alt="" width={dimension} height={dimension} unoptimized onError={() => setSourceIndex(i => i + 1)} /> :
        // eslint-disable-next-line @next/next/no-img-element
        <img src={source} alt="" width={dimension} height={dimension} loading="lazy" referrerPolicy="no-referrer"
          className="max-h-[75%] max-w-[75%] object-contain" onError={() => setSourceIndex(i => i + 1)} /> :
        // A neutral product icon is an explicit fallback, not an invented vendor logo.
        <svg viewBox="0 0 40 40" width={dimension} height={dimension} fill="none" aria-hidden="true">
          <rect x="5" y="5" width="30" height="30" rx="9" fill="#eef2ff"/>
          <path d="M13 20h14M20 13v14" stroke="#4556c9" strokeWidth="3" strokeLinecap="round"/>
          <circle cx="20" cy="20" r="4" fill="#4556c9"/>
        </svg>}
    </span>
  );
}
