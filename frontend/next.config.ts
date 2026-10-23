import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const apiBase = (
      process.env.MIRA_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000"
    ).replace(/\/+$/, "");

    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiBase}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
