import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  typescript: {
    // Build debe fallar si hay errores de tipo.
    // Si se necesita ignorar temporalmente, usar // @ts-expect-error con razón.
    ignoreBuildErrors: false,
  },
  eslint: {
    // Build debe fallar si hay errores de lint.
    ignoreDuringBuilds: false,
  },
};

export default nextConfig;
