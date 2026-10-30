import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Server components only; no env vars are inlined into the browser bundle.
  poweredByHeader: false,
};

export default nextConfig;
