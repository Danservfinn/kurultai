import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Removed 'export' to allow dynamic API routes
  // Use standalone deployment instead
  distDir: 'dist',
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
