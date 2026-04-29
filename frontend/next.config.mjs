/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Use a dedicated tsconfig for Next's typecheck so it can add `.next/types/**`
  // without breaking editors on a fresh clone (no `.next/` yet).
  typescript: {
    tsconfigPath: "./tsconfig.next.json"
  }
};

export default nextConfig;

