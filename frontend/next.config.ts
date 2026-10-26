import type { NextConfig } from "next";

const isProductionBuild = process.env.NODE_ENV === "production";
const configuredApiBase = process.env.MIRA_API_URL || process.env.NEXT_PUBLIC_API_URL;

// Never silently route a deployed frontend's API requests to its own localhost.
// Configure MIRA_API_URL (preferred) or NEXT_PUBLIC_API_URL in Vercel before building.
if (isProductionBuild && !configuredApiBase) {
  throw new Error(
    "MIRA API URL is missing. Set MIRA_API_URL (preferred) or NEXT_PUBLIC_API_URL in the Vercel project environment and redeploy."
  );
}

const apiBase = (configuredApiBase || "http://localhost:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiBase}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
