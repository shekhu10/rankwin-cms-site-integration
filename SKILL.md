---
name: rankwin-cms-site-integration
description: Integrate any customer website with the paid RankWin CMS pull API using a server-only delivery API key. Use when implementing or repairing crawlable blog index/detail routes, stable article and block synchronization, authenticated HTML proxying, sitemap/feed delivery, metadata, optional featured images and public media, caching, analytics, or end-to-end verification in Next.js, Java/Spring, another server framework, an edge worker, or a reverse proxy.
metadata:
  {
    "clawdbot":
      {
        "requires": { "env": ["RANKWIN_CMS_API_BASE", "RANKWIN_CMS_API_KEY"] },
      },
  }
---

# RankWin CMS Site Integration

Implement RankWin CMS on the customer website without adding a publishing
receiver or modifying RankWin. Keep the customer URL canonical, keep the
delivery key on the server, and make the complete article visible in the
initial HTTP response.

## First-run setup

Before editing code, confirm all four inputs:

1. In **RankWin → Settings → Integrations → RankWin CMS**, create or select the
   exact customer hostname and blog path.
2. Copy its persistent API base into the customer server environment as
   `RANKWIN_CMS_API_BASE`, for example
   `https://rankwin.co/api/cms/v1/sites/rwcms_...`.
3. On the same site card, create a **production delivery API key**. This control
   is available only while the project has a paid publishing entitlement. Save
   the one-time secret as `RANKWIN_CMS_API_KEY` in the customer server
   environment.
4. Choose authenticated RankWin-rendered HTML proxying or customer-rendered
   JSON. Both must run on the server.

The skill repository is public; the API is not. Every upstream request needs:

```text
Authorization: Bearer $RANKWIN_CMS_API_KEY
```

Never print, commit, log, screenshot, embed in a URL, expose through a public
environment prefix, or send this key to browser JavaScript. Never forward a
customer visitor's cookies or Authorization header to RankWin. Inject exactly
the configured RankWin key on the customer server.

No DNS TXT or CNAME step exists for pull delivery. Customer code makes content
visible on a hostname the customer already controls.

## Workflow

### 1. Inspect the customer application

Find the framework, runtime, existing routing, cache layer, sitemap generation,
analytics owner, environment/deployment convention, and routes that could
collide with the configured blog path. Do not edit RankWin or guess how the
customer application deploys.

Read the matching reference:

- Next.js/App Router or Pages Router: `references/nextjs.md`
- Java/Spring MVC or WebFlux: `references/java-spring.md`
- other server, edge runtime, or reverse proxy: `references/generic-server.md`
- exact fields, errors, authorization, caching, and identity:
  `references/api-contract.md`

### 2. Validate credentials before implementation

From a server shell, without displaying the key:

```bash
test -n "$RANKWIN_CMS_API_BASE" && test -n "$RANKWIN_CMS_API_KEY"
curl --fail-with-body --silent --show-error \
  --header "Authorization: Bearer $RANKWIN_CMS_API_KEY" \
  "$RANKWIN_CMS_API_BASE/articles?limit=1"
```

Expected: HTTP 200 and `apiVersion: cms.v1`. HTTP 401 means the key is missing,
malformed, revoked, scoped to another site, or the paid entitlement is inactive.
Do not retry a 401. Ask an authorized RankWin project manager to create a
replacement or restore the subscription; update the customer server, verify,
then revoke the old key.

### 3. Choose one SEO-safe delivery architecture

Prefer **same-origin authenticated HTML proxying** when the customer accepts
RankWin's markup. The customer server injects the bearer header and proxies:

- blog index → `<api-base>/articles?format=page`
- article route → `<api-base>/articles/<slug>?format=page`
- sitemap → `<api-base>/sitemap.xml`
- feed → `<api-base>/feed.xml`

A bare external rewrite is invalid because it cannot safely attach a secret
header. Use a Route Handler, server controller, edge/server worker secret, or
reverse-proxy secret variable.

Choose **customer-rendered JSON** when the customer owns markup and layout. The
server calls the list endpoint, selects by stable article `id`, calls the ID
detail endpoint, and renders metadata/body/structured data before returning
HTML. SSR, SSG, ISR, server templates, and build-time generation are valid.

Never implement an indexable article as an empty shell populated only by
`useEffect`, DOM-ready JavaScript, or another browser-only request.

### 4. Implement stable identity

Use these identities exactly:

- API base/site key: tenant and site boundary in every upstream URL
- delivery API key: secret authorization, independently revocable per site
- `article.id`: stable article identity used for sync and detail retrieval
- `article.slug`: presentation route only
- `article.document.id`: structured document identity
- `article.document.blocks[*].id`: stable block identity
- every nested inline/list/table/FAQ node also has an `id`

Fetch detail with:

```text
GET <api-base>/articles/by-id/<article.id>
Authorization: Bearer <server-only-key>
```

Do not use a slug as a database key. Two sites may intentionally use the same
slug. Never attempt an ID lookup under another site API base or cache an article
without the site identity.

### 5. Render the complete contract

For customer-rendered JSON, render:

- `<title>` from `metaTitle || title`
- meta description and canonical link from `canonicalUrl`
- Open Graph/Twitter values from `seo`
- optional `featuredImage` (`{ id, url, alt }`) in the index card and article
  header; keep the existing text-only layout when it is `null`
- article body from sanitized `html` or a complete structured-document renderer
- every object in `jsonLd` as `application/ld+json`
- published and modified timestamps
- crawlable index links using each summary's canonical URL/slug

RankWin's `html` is sanitized by the CMS renderer. Do not concatenate untrusted
customer input into it. If rendering `document`, exhaustively handle the
versioned block union and escape text/attributes.

The `featuredImage.url` is the sole public-media exception to bearer
authorization. It is an immutable HTTPS URL intentionally loadable by browsers
and crawlers, so fetch it without the delivery key. Never turn a private
`/api/files/...` reference or another URL from article content into a public
asset proxy.

### 6. Preserve cache and failure semantics

- Keep upstream RankWin responses private; they are bearer-authorized. Cache a
  derived public customer response only in a site-scoped server cache.
- Forward `If-None-Match`; preserve `ETag`, `Content-Type`, `Last-Modified`, and
  safe `Vary` values. Do not copy the upstream `private/no-store` policy onto a
  public customer page if the application has an explicit authenticated
  regeneration cache.
- Use bounded timeouts and stale-if-error behavior where supported.
- Treat 401 as terminal configuration/subscription failure, 404 as
  missing/unpublished, 429 as retryable with jitter, and 5xx/network failures
  as retryable. Never replace a valid cached page with an empty 200.
- Follow `nextCursor` verbatim until null. Do not construct or decode cursors.

### 7. Integrate sitemap, feed, and analytics

Expose the RankWin sitemap under the customer origin or merge it into the
customer sitemap index. A public crawler reaches the customer route without a
key; the customer server privately fetches RankWin with the key. The XML
contains customer canonical URLs.

Choose exactly one GA4 page-view owner. If RankWin-rendered HTML has a configured
measurement ID, do not inject the same automatic page view again. For
customer-rendered JSON, normally let the customer layout own analytics.

### 8. Verify in loops

Run repository and deployment checks, then run from this skill directory:

```bash
python3 scripts/verify_integration.py \
  --api-base "$RANKWIN_CMS_API_BASE" \
  --customer-blog-url "https://customer.example/blogs"
```

The verifier reads `RANKWIN_CMS_API_KEY` from the environment and never accepts
it as a command-line argument. Repeat fetch → inspect → fix → deploy → fetch
until all checks pass. Verify:

1. no/malformed key receives 401, while the configured key receives 200;
2. list JSON is `cms.v1` and every summary has `id`, slug, metadata, the
   customer canonical, and a valid nullable `featuredImage`;
3. ID detail returns the same `id`, a document ID, uniquely-IDed non-empty
   blocks, HTML, SEO, and JSON-LD;
4. another site's API base/key pair cannot retrieve the ID;
5. customer index and article return 200 `text/html`, not API JSON;
6. initial source contains title, canonical, body, and JSON-LD;
7. sitemap/feed contain only the intended site's customer URLs;
8. `If-None-Match` produces 304 through an authorized request;
9. root-path mode does not shadow existing product/account routes;
10. exactly one analytics page view fires;
11. after a replacement is installed, revoking the old key makes that old key
    receive 401 without interrupting the new one.
12. when a featured image exists, it loads without a bearer key, appears in the
    initial customer index card, article HTML, Open Graph/Twitter metadata, and
    Article JSON-LD with meaningful alt text; when absent, no broken or empty
    image container is rendered.

Do not declare completion from an upstream API call alone. The canonical
customer URL and its initial HTML are the acceptance boundary.
