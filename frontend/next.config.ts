import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next.js 16 blocks dev-asset requests from origins other than the
  // bound host by default. The IDE's browser preview proxies through
  // 127.0.0.1 which Next.js considers a separate origin from
  // `localhost`, so HMR fetches get rejected and the dev console
  // fills with warnings. Opt 127.0.0.1 (and the project's preview
  // proxy) into the dev allowlist. Production is unaffected.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
