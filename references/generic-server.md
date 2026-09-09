# Generic server, proxy, or edge runtime

Run `scripts/discover_site.py` first. Use its authenticated `blogPath` as the
only routing prefix; never default to `/blogs` or ask for a second path. The
minimum integration is four fixed same-origin public routes whose server
handler makes authenticated upstream requests:

```text
<blogPath>                 -> <api-base>/articles?format=page
<blogPath>/:slug           -> <api-base>/articles/:slug?format=page
<blogPath>/sitemap.xml     -> <api-base>/sitemap.xml
<blogPath>/feed.xml        -> <api-base>/feed.xml
```

Store `RANKWIN_CMS_API_BASE` and `RANKWIN_CMS_API_KEY` in the platform's
server/worker secret store. On every upstream request set a new
`Authorization: Bearer <configured-key>` header. Do not forward the visitor's
Authorization, Cookie, query-supplied upstream URL, or arbitrary headers.

Order sitemap/feed before the slug catch-all. For root mode, preserve every
existing product route before `/:slug` and use a non-conflicting sitemap path.
Build upstream URLs from trusted configuration, percent-encode the slug once,
reject separators/control characters, and use bounded timeouts.

At startup or build time, compare any persisted routing prefix with a fresh
authenticated discovery response. Fail closed on mismatch and regenerate the
route configuration before deployment. A RankWin path change cannot mutate a
customer server's route table without a new build or configuration rollout.

Preserve status and safe content/validator headers. Keep upstream responses
private; if caching a public response, key it by the configured site and route
and invalidate it on ETag change. A redirect to `rankwin.co` is not same-origin
delivery and must not be the final public article URL.

Register `<blogPath>/sitemap.xml` through a `Sitemap:` line in `robots.txt`, a
`<sitemap>` entry in a sitemap index, or a registered root sitemap containing
every published canonical. A sitemap URL inside a normal `<urlset>` is not
sitemap registration. The discovered host itself must be the final URL host;
an apex/`www` redirect is a configuration mismatch, not a valid canonical
delivery result.

For a custom renderer, follow `references/api-contract.md`. Server-render the
list/detail and expose customer canonical, sitemap, and crawlable links in the
initial HTML.

Treat `featuredImage` as nullable structured data, not as a required layout
slot. When present, validate its HTTPS URL, render it with its `alt` on the
index card and article page, and reuse the URL for Open Graph/Twitter metadata
and Article JSON-LD. Browsers, social crawlers, and image optimizers fetch that
media URL without the delivery bearer key. Do not generalize this exception
into an arbitrary asset proxy. When absent, emit no broken `<img>` or empty
wrapper and keep the customer's current text-only/fallback card. Authenticated
HTML proxy mode already contains the correct optional image markup.

Article detail layout must be **one visible `<h1>` title → optional featured
image → description/byline/dates and article body**, in both DOM and visual
order. Place the image immediately after the headline; omit only the image
wrapper when absent. Keep the index-card design independent. Verify this order
in the initial HTML and at desktop and mobile widths.

Fetch sitemap, feed, index, and detail from authenticated RankWin at request
time when immediate publish/removal visibility is required. Disable public
CDN/proxy caches (`Cache-Control: no-store`) unless a tested invalidation flow
covers every lifecycle transition. Do not generate an index-only XML fallback
on upstream failure. Preserve authenticated 404 as a public 404/410 after
unpublication; do not redirect deleted articles to the blog index. Read
`search-discovery.md` for runtime acceptance checks and Google/Bing setup.
