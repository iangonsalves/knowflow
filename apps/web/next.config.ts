import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The hosted demo accepts 8 MiB PDFs. Leave room for multipart boundaries
  // while keeping the Server Action request below Render's request limits.
  experimental: {
    serverActions: {
      bodySizeLimit: "9mb",
    },
  },
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
