import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    if (process.env.NEXT_PUBLIC_APP_MODE !== "prod") {
      return [];
    }
    const backendUrl = (
      process.env.BACKEND_URL || "http://localhost:8000"
    ).replace(/\/+$/, "");
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
      {
        source: "/api/invoice/:path*",
        destination: `${backendUrl}/api/invoice/:path*`,
      },
      {
        source: "/api/explain",
        destination: `${backendUrl}/api/explain`,
      },
    ];
  },
};

export default nextConfig;
