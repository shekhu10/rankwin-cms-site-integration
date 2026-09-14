# Next.js implementation

External `next.config` rewrites are not sufficient because they cannot safely
inject a delivery secret. Use App Router Route Handlers/server components (or
the equivalent Pages Router API routes and `getStaticProps`).

Run `scripts/discover_site.py` before editing routes. Convert the authenticated
`blogPath` into the matching App Router directory (for example `/resources/blog`
becomes `app/resources/blog`). Do not default to `app/blogs` and do not ask the
operator to enter the path again. Filesystem routes are build artifacts: if
RankWin later returns a different path, fail verification, move/regenerate the
route tree, and redeploy.

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
    cache: "no-store",
  });
}
```

Never import this module from a Client Component and never name the key with a
`NEXT_PUBLIC_` prefix.

## Public renderer marker

Create `app/.well-known/rankwin-site/route.ts`. Its server handler must perform
authenticated no-store discovery, validate the opaque non-secret `site.id`, and
return `rankwin-site:<site.id>` as `text/plain; charset=utf-8` with
`Cache-Control: no-store`. It must never return or log the delivery key. Treat
401/configuration/invalid-contract failures as terminal; treat 429, upstream
5xx, timeouts, and network failures as retryable without replacing the marker
with a fabricated value. Pull delivery needs no TXT or CNAME record.

## Authenticated HTML proxy mode

Create fixed handlers for `<site.blogPath>`, `<site.blogPath>/[slug]`, the
sitemap, and feed. Call `rankWinFetch` with `?format=page` for HTML.
Validate/encode the slug, preserve status and safe content/ETag headers, and
stream or return the body. Do not forward browser cookies/Authorization.
Upstream 401 is a server-configuration or subscription failure, not a
not-found article.

Register the dynamic `<blogPath>/sitemap.xml` as an actual sitemap. With
`next-sitemap`, put its absolute URL in `robotsTxtOptions.additionalSitemaps`
and exclude both `<blogPath>/sitemap.xml` and `<blogPath>/feed.xml` from the
ordinary page URL set. If using a Next metadata `robots.ts`, return the RankWin
sitemap in its `sitemap` field. Do not add the sitemap URL as a normal `<url>`.

Keep the index, detail, sitemap, and feed on the exact non-redirecting hostname
returned by discovery. A `www`/apex redirect means RankWin's configured host and
the customer's primary domain disagree; correct the configuration rather than
teaching the adapter to emit two canonical hosts.

## Customer renderer mode

Fetch the index list in a Server Component. For a detail route, use a fresh
authenticated slug lookup to resolve its stable ID, followed by the by-ID read
below. Do not paginate the entire index to resolve a slug. Validate the site,
ID, slug and publication/version/digest agreement before rendering; permit one
fresh retry if publication changed between reads. Deduplicate metadata and body
reads within the request, without introducing a cross-request content cache.

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
only for authenticated 404. Use an error boundary for 401/429/5xx; never return
an empty 200. A tested stale-content policy may cover transient 429/5xx failures,
but must not serve revoked or removed content after 401/404.

Use no-store by default. ISR requires tested publish/update/delete and key
revocation invalidation; retaining a prior page on every error is insufficient.
Do not catch an authenticated list failure and replace it with an empty array.

When `featuredImage` is non-null, allowlist the exact RankWin production
hostname and CMS media path in `images.remotePatterns`, render its `url` in both
the index card and article header, and use its `alt`. Prefer `next/image` so the
customer origin can optimize it. Prefer the same URL for Open Graph/Twitter
metadata and the Article JSON-LD `image` field. The media request itself is
public and must not contain the delivery key. When `featuredImage` is null,
omit the image wrapper entirely and keep the customer's existing fallback.

Article detail layout must be **one visible `<h1>` title → optional featured
image → description/byline/dates and article body**, in both DOM and visual
order. Place the image immediately after the headline; omit only the image
wrapper when absent. Keep the index-card design independent. Verify this order
in the initial HTML and at desktop and mobile widths.

```tsx
<article>
  <header>
    <h1>{article.title}</h1>
    {article.featuredImage && <FeaturedImage image={article.featuredImage} />}
    {/* Description, byline, and publication dates follow the image. */}
  </header>
  <div dangerouslySetInnerHTML={{ __html: article.html }} />
</article>
```

`FeaturedImage` represents the customer's image component with the supplied
URL/alt and reserved aspect ratio; keep the body server-rendered.

### Table presentation

Preserve `table`, `thead`, `tbody`, `tr`, `th`, `td`, `caption`, and the
`rankwin-table-scroll` wrapper class when sanitizing the body. Apply scoped
styles using the customer's theme colors, for example:

```css
.rankwin-cms-content .rankwin-table-scroll {
  max-width: 100%; overflow-x: auto; margin: 1.5rem 0;
  border: 1px solid var(--table-border); border-radius: .75rem;
}
.rankwin-cms-content table {
  width: 100%; min-width: 40rem; margin: 0; border-collapse: collapse;
  font-size: .9375rem; line-height: 1.6;
}
.rankwin-cms-content :is(th, td) {
  min-width: 9rem;
  padding: .875rem 1rem; text-align: left; vertical-align: top;
  border-bottom: 1px solid var(--table-border); overflow-wrap: anywhere;
}
.rankwin-cms-content th { background: var(--table-header); font-weight: 700; }
.rankwin-cms-content tbody tr:last-child td { border-bottom: 0; }
```

Resolve the example color variables to existing light/dark theme tokens. Keep
the article's flex/grid ancestors shrinkable (`min-width: 0` where needed).
Verify the actual published table at desktop and 390px mobile widths: all
cells remain readable, the last column is reachable by scrolling the wrapper,
and the document itself does not overflow horizontally. The HTTP verifier
checks semantic cells; it cannot certify browser layout from HTML alone.

## Streamed metadata verification

Use `generateMetadata` for the canonical link, robots directives, and the three
RankWin publication markers. Next.js may append resolved metadata directly to
`body` when streaming a dynamic page. RankWin checks both head metadata and
these document-level body tags. Do not duplicate them inside the article or
place them only in JavaScript. Conflicting canonicals, stale markers, and
noindex directives must still fail verification. There is no need to disable
streaming for every visitor or impersonate a search engine's user agent.

Verify the complete HTTP response using `RankWin-PublicationVerifier/1.0
(+https://rankwin.co)` as well as the browser-rendered page. See the official
[Next.js streaming metadata documentation](https://nextjs.org/docs/app/api-reference/functions/generate-metadata#streaming-metadata).

## Runtime sitemap and deletion

Use a dynamic Route Handler for `<blogPath>/sitemap.xml` with
`export const dynamic = "force-dynamic"`. Fetch `<api-base>/sitemap.xml` with
`cache: "no-store"`, preserve the XML and upstream error status, and return
`Cache-Control: no-store` on the customer response. Never fall back to an
index-only sitemap on an upstream error. Existing build-time `next-sitemap`
output may register the dynamic child, but must not freeze its article list.

Use no-store fetches for the article index and detail too when immediate
publish/removal visibility is required. Static export and build-only article
lists cannot satisfy this contract. If using a cache, require a working
invalidation mechanism covering index, detail, sitemap, feed, and CDN before
claiming immediate lifecycle support. A deleted upstream detail must become
an HTTP 404/410, including previously cached routes.

Read `search-discovery.md` for IndexNow's public ownership-file route and the
project-level Google/Bing setup. That public ownership key is distinct from
the secret delivery key.
