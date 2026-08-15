# Java / Spring implementation

Use a singleton `WebClient` or Java `HttpClient` with connect/read timeouts.
Load the API base and key from server configuration. Never return either through
an actuator environment endpoint, template model, public JavaScript config, or
error message.

## Proxy mode

Map `/blogs`, `/blogs/{slug}`, `/blogs/sitemap.xml`, and `/blogs/feed.xml`.
Construct upstream paths from fixed templates and an encoded path segment. Set
`Authorization` to `Bearer ` plus the configured RankWin key on the outbound
request; never forward the visitor's Authorization or cookies. Force
`format=page` for HTML.

Forward `If-None-Match`; copy safe response headers (`Content-Type`, `ETag`,
`Last-Modified`, `Vary`). Stream the body and preserve 304/401/404/429/5xx.
Map upstream 401 to an operational configuration failure without revealing the
key; do not return an empty 200.

## Template-rendered JSON mode

Model DTOs with unknown-field tolerance and an explicit `apiVersion` check.
Cache by `(siteIdentity, articleId, contentVersion)`, never article ID alone.
Render title, description, canonical, body, timestamps, and every JSON-LD object
in the server template.

Use summary `id` to call `/articles/by-id/{id}` and include the bearer header.
Validate that returned `article.id` equals the request and that all document
node IDs are unique before persisting a synchronized copy. Keep slug as a route
label, not a primary key.
