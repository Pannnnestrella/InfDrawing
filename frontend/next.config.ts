import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  transpilePackages: ["@tldraw/tldraw", "tldraw"],
  // Allow opening dev server via 127.0.0.1 (docs default) as well as localhost.
  allowedDevOrigins: ["127.0.0.1"],
  // Scene parse (qwen3-vl-plus) commonly exceeds the 30s rewrite default and
  // surfaces as a generic 500 / socket hang up while the backend still succeeds.
  experimental: {
    proxyTimeout: 180_000,
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
