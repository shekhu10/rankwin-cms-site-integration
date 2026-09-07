# Java / Spring implementation

Use a singleton `WebClient` or Java `HttpClient` with connect/read timeouts.
Load the API base and key from server configuration. Never return either through
an actuator environment endpoint, template model, public JavaScript config, or
error message.

Before creating controller mappings, run `scripts/discover_site.py` with the
same server environment. Generate the controller's route prefix from its
authenticated `blogPath`; do not hard-code `/blogs` or maintain a separate
operator-entered path. If a subsequent discovery differs from the compiled or
configured prefix, fail the deployment check and rebuild/redeploy.

## Proxy mode

Map `<blogPath>`, `<blogPath>/{slug}`, `<blogPath>/sitemap.xml`, and
`<blogPath>/feed.xml`. Construct upstream paths from fixed templates and an
encoded path segment. Set
`Authorization` to `Bearer ` plus the configured RankWin key on the outbound
request; never forward the visitor's Authorization or cookies. Force
`format=page` for HTML.

Forward `If-None-Match`; copy safe response headers (`Content-Type`, `ETag`,
`Last-Modified`, `Vary`). Stream the body and preserve 304/401/404/429/5xx.
Map upstream 401 to an operational configuration failure without revealing the
key; do not return an empty 200.

Add the same-origin sitemap to `robots.txt`, a real sitemap index, or merge all
published canonicals into the registered root sitemap. Do not list the sitemap
document as a page URL. Verify that the discovered hostname is already the final
non-redirecting hostname for the index, article, sitemap, and feed.

## Template-rendered JSON mode

Model DTOs with unknown-field tolerance and an explicit `apiVersion` check.
Cache by `(siteIdentity, articleId, contentVersion)`, never article ID alone.
Render title, description, canonical, body, timestamps, and every JSON-LD object
in the server template.

Use summary `id` to call `/articles/by-id/{id}` and include the bearer header.
Validate that returned `article.id` equals the request and that all document
node IDs are unique before persisting a synchronized copy. Keep slug as a route
label, not a primary key.

Model `featuredImage` as a nullable DTO containing `id`, HTTPS `url`, and
meaningful `alt`. When present, render it in the server-generated index card and
article header, and use the same URL in Open Graph/Twitter metadata and Article
JSON-LD. Fetch the media URL without the delivery bearer key; it is the single
public-media exception and is safe only because RankWin binds it to the active
published site snapshot. When it is null, omit the `<img>`/wrapper and preserve
the customer's existing text-only fallback. In proxy mode RankWin's HTML
already performs this rendering; do not add a second hero image around it.


Fetch sitemap, feed, index, and detail from authenticated RankWin at request
time when immediate publish/removal visibility is required. Disable public
CDN/proxy caches (`Cache-Control: no-store`) unless a tested invalidation flow
covers every lifecycle transition. Do not generate an index-only XML fallback
on upstream failure. Preserve authenticated 404 as a public 404/410 after
unpublication; do not redirect deleted articles to the blog index. Read
`search-discovery.md` for runtime acceptance checks and Google/Bing setup.
