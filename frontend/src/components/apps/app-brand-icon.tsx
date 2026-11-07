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

export function logoSourcesFor(id: string): string[] {
  const profile = profileFor(id);
  const sources: string[] = [];
  if (localLogos[id]) sources.push(localLogos[id]);
  // The icon set only accepts normalised slugs; remote toolkit names are untrusted.
  const simpleIcon = profile?.logo || id;
  if (/^[a-z0-9]+$/.test(simpleIcon)) sources.push(`https://cdn.simpleicons.org/${simpleIcon}`);
  if (profile?.website) {
    try {
      const domain = new URL(profile.website).hostname;
      if (domain) sources.push(`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128`);
    } catch { /* Invalid editorial URL: use the next supported artwork. */ }
  }
  return [...new Set(sources)];
}

export function AppBrandIcon({item, large = false}: {item: CatalogApp; large?: boolean}) {
  const [sourceIndex, setSourceIndex] = useState(0);
  const sources = logoSourcesFor(item.id);
  const source = sources[sourceIndex];
  const dimension = large ? 52 : 30;
  return (
    <span className={"grid shrink-0 place-items-center overflow-hidden rounded-2xl border border-[var(--mira-apps-border)] bg-white " +
      (large ? "h-20 w-20" : "h-12 w-12")} aria-label={`Logo de ${item.name}`} role="img">
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
