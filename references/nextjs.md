# Next.js implementation

External `next.config` rewrites are not sufficient because they cannot safely
inject a delivery secret. Use App Router Route Handlers/server components (or
the equivalent Pages Router API routes and `getStaticProps`).

## Server-only client

```ts
import "server-only";

const base = process.env.RANKWIN_CMS_API_BASE;
const key = process.env.RANKWIN_CMS_API_KEY;
if (!base || !key) throw new Error("RankWin CMS server configuration missing");

export async function rankWinFetch(path: string, init: RequestInit = {}) {
  return fetch(`${base}${path}`, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${key}`,
    },
    next: { revalidate: 300 },
  });
}
```

Never import this module from a Client Component and never name the key with a
`NEXT_PUBLIC_` prefix.

## Authenticated HTML proxy mode

Create fixed handlers for `/blogs`, `/blogs/[slug]`, the sitemap, and feed. Call
`rankWinFetch` with `?format=page` for HTML. Validate/encode the slug, preserve
status and safe content/ETag headers, and stream or return the body. Do not
forward browser cookies/Authorization. Upstream 401 is a server-configuration or
subscription failure, not a not-found article.

## Customer renderer mode

Fetch list in a Server Component. Use summary `id` for detail and summary
`slug` for `generateStaticParams`/routing:

```ts
async function articleById(id: string) {
  const response = await rankWinFetch(
    `/articles/by-id/${encodeURIComponent(id)}`,
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`RankWin CMS ${response.status}`);
  return (await response.json()).article;
}
```

`generateMetadata` must return title, description, canonical, and Open Graph
data. Initial server HTML must contain the body and JSON-LD. Call `notFound()`
only for authenticated 404. Use an error boundary or known-good cached page for
401/429/5xx; never return an empty 200.

When `featuredImage` is non-null, allowlist the exact RankWin production
hostname and CMS media path in `images.remotePatterns`, render its `url` in both
the index card and article header, and use its `alt`. Prefer `next/image` so the
customer origin can optimize it. Prefer the same URL for Open Graph/Twitter
metadata and the Article JSON-LD `image` field. The media request itself is
public and must not contain the delivery key. When `featuredImage` is null,
omit the image wrapper entirely and keep the customer's existing fallback.
