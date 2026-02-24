import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080";

const nextConfig: NextConfig = {
  ...(isDev ? {} : { output: "export" }),
  ...(isDev
    ? {
        async rewrites() {
          return [
            { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
            { source: "/ws", destination: `${backendUrl}/ws` },
            { source: "/webhook/:path*", destination: `${backendUrl}/webhook/:path*` },
            { source: "/health", destination: `${backendUrl}/health` },
          ];
        },
      }
    : {}),
};

export default nextConfig;
