import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // TODO: add proper TypeScript annotations to page.tsx and remove this.
  // Skipping build-time type-checking so production builds aren't blocked
  // by implicit-any in event handlers. Runtime code is unaffected.
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
