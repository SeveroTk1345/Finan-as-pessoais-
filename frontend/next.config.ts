import type { NextConfig } from "next";

// Produção: export estático (HTML/JS/CSS) servido pelo mesmo domínio da API.
// Desenvolvimento: o servidor do Next encaminha /api para o FastAPI local,
// reproduzindo a "mesma origem" de produção.
const isDev = process.env.NODE_ENV !== "production";
const apiOrigin = process.env.FIN_DEV_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = isDev
  ? {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
      },
    }
  : {
      output: "export",
      trailingSlash: true,
      images: { unoptimized: true },
    };

export default nextConfig;
