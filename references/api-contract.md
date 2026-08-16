# RankWin CMS `cms.v1` API contract

## Authorization

All endpoints are read-only GETs beneath a site-specific API base. Every content
GET requires `Authorization: Bearer <RANKWIN_CMS_API_KEY>`. The public site key in
the base URL selects one site; the independently revocable bearer key authorizes
that server deployment; the current paid `publishing.execute` entitlement must
also remain live.

Never expose the bearer value to the browser. Customer public routes terminate
the visitor request and make a separate server-to-server request to RankWin.

## Endpoints

| Request                                     | Response                                  |
| ------------------------------------------- | ----------------------------------------- |
| `GET /articles?limit=20&cursor=<opaque>`    | JSON list; limit is clamped to 1–50       |
| `GET /articles?format=page&cursor=<opaque>` | server-rendered HTML index                |
| `GET /articles/<slug>`                      | JSON detail selected by presentation slug |
| `GET /articles/<slug>?format=page`          | server-rendered HTML article              |
| `GET /articles/<slug>?format=markdown`      | Markdown article                          |
| `GET /articles/by-id/<articleId>`           | JSON detail selected by stable identity   |
| `GET /media/<assetId>`                      | public immutable published image bytes    |
| `GET /sitemap.xml`                          | XML sitemap with customer canonical URLs  |
| `GET /feed.xml`                             | Atom feed                                 |

## List and detail identity

The list response is `cms.v1`. Every summary includes stable `id`, current
`publicationId`, slug, title/metadata, content version, timestamps, and
`canonicalUrl`, and nullable `featuredImage` (`{ id, url, alt }`). Use `id` for sync. `publicationId` changes after republishing;
`slug` is only a customer route label.

Detail `article` contains `id`, `publicationId`, `documentId`,
`contentVersion`, slug, metadata, canonical, timestamps, versioned `document`,
safe `html`, `markdown`, `seo`, and `jsonLd`.

`featuredImage.url` points at `/media/<assetId>`. This media GET intentionally
does not accept or require the bearer key: a browser, image optimizer, or social
crawler must be able to load an image on a public customer page. It resolves
only an active stored image referenced by this site's current published
snapshot and returns immutable caching headers. An unattached, superseded,
cross-site, quarantined, or deleted image returns 404.

The structured document is versioned and has stable IDs:

```json
{
  "version": 1,
  "id": "document-id",
  "locale": "en",
  "blocks": [{ "type": "paragraph", "id": "block-id", "children": [] }]
}
```

Block types include paragraph, heading, list, image, quote, code, table,
callout, CTA, divider, FAQ group, and allowlisted media embed. Every block and
nested node has a unique ID within the document.

## HTTP behavior

- OPTIONS advertises GET and Authorization support.
- Authorized upstream responses are `private, no-store`; customer servers may
  build an explicitly site-scoped public regeneration cache.
- Send `If-None-Match` with a prior ETag; unchanged authorized responses return 304.
- 401 means missing/malformed/revoked/wrong-site key or inactive paid
  entitlement. Do not retry until configuration or billing is corrected.
- 404 means the authenticated site has no requested published article.
- 429 is rate limiting. Back off with jitter; do not fan out without bounds.
- Featured media permits PNG, JPEG, WebP, and GIF. Treat other/missing media as
  absent; do not proxy arbitrary image URLs through the customer application.

## Security invariant

An article ID is not globally readable. The same ID under another site base or
with another site's key must fail. Cache records by site identity + article ID
+ content version, never article ID alone.
