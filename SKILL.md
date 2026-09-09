---
name: rankwin-cms-site-integration
description: Integrate any customer website with the RankWin CMS pull API using a server-only delivery API key and the authenticated site.blogPath selected in RankWin. Use when implementing or repairing crawlable blog index/detail routes, stable article and block synchronization, authenticated HTML proxying, sitemap/feed delivery, metadata, optional featured images and public media, caching, analytics, or end-to-end verification in Next.js, Java/Spring, another server framework, an edge worker, or a reverse proxy.
---

# RankWin CMS Site Integration

Contract bundle: `cms.v1 / 2026-09-09`. The repository copy is the release source; parent and installed copies must match it.

Implement RankWin CMS on the customer website without adding a publishing
receiver or modifying RankWin. Keep the customer URL canonical, keep the
delivery key on the server, and make the complete article visible in the
initial HTTP response.

## First-run setup

Before editing code, complete this credential and discovery gate:

1. In **RankWin → Settings → Integrations → RankWin CMS**, create or select the
   exact customer hostname and blog path.
2. Copy its persistent API base into the customer development environment as
   `RANKWIN_CMS_API_BASE`, for example
   `https://rankwin.co/api/cms/v1/sites/rwcms_...`.
3. On the same site card, copy an active **production delivery API key**, or create one. This control
   is available while the project has an active subscription or live introductory trial. Save
   the key as `RANKWIN_CMS_API_KEY` in the customer development
   environment. Saved keys remain visible in the authorized RankWin setup screen after reload. Older keys stored only as a hash need **Save existing key** once before they can be displayed again. If either variable is absent, stop and ask the customer to set
   it in their local secret store or shell; never ask them to paste the key into
   chat or source code.
4. Authenticate and discover the authoritative site configuration before
   choosing or creating routes. Resolve the directory containing this
   `SKILL.md`, then run:

   ```bash
   python3 <skill-directory>/scripts/discover_site.py
   ```

   Read `id`, `host`, `blogPath`, and `customerBlogUrl` from the JSON output.
   `id` is an opaque, non-secret site identity. Do not ask the customer to
   retype the path and do not default to `/blogs`. Generate every customer
   route from this exact `blogPath`.

5. Choose authenticated RankWin-rendered HTML proxying or customer-rendered
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
visible on a hostname the customer already controls. It must expose
`/.well-known/rankwin-site` as no-store `text/plain` with the exact body
`rankwin-site:<site.id>`, deriving `site.id` from authenticated discovery. This
marker is not a third secret and must never contain the delivery API key.

## Workflow

### 1. Inspect the customer application

Find the framework, runtime, existing routing, cache layer, sitemap generation,
analytics owner, environment/deployment convention, and routes that could
collide with the discovered `site.blogPath`. Do not edit RankWin, guess the
path, or guess how the customer application deploys. Treat the discovery output
as the route-generation input for this run:

- `<blogPath>` → the crawlable index;
- `<blogPath>/[slug]` → article detail;
- `<blogPath>/sitemap.xml` → sitemap;
- `<blogPath>/feed.xml` → feed.
- `/.well-known/rankwin-site` → `rankwin-site:<site.id>` as no-store plain text.

For root mode (`blogPath === "/"`), use `/[slug]` only after preserving every
existing product route and assigning non-conflicting sitemap/feed routes.

Read the matching reference:

- Next.js/App Router or Pages Router: `references/nextjs.md`
- Java/Spring MVC or WebFlux: `references/java-spring.md`
- other server, edge runtime, or reverse proxy: `references/generic-server.md`
- exact fields, errors, authorization, caching, and identity:
  `references/api-contract.md`

### 2. Validate credentials and path before implementation

Run discovery from a server shell without displaying the key:

```bash
test -n "$RANKWIN_CMS_API_BASE" && test -n "$RANKWIN_CMS_API_KEY"
python3 <skill-directory>/scripts/discover_site.py
```

The script reads both variables from the environment, sends the delivery key
only in the Authorization header, and prints only non-secret site configuration.
Expected: `apiVersion: cms.v1` plus the authenticated `site.id`, `site.host`,
and `site.blogPath`. HTTP 401 means the key is missing, malformed, revoked,
scoped to another site, or the subscription or trial is inactive. Do not retry a
401. Ask an authorized RankWin project manager to create a replacement or
restore the subscription; update the customer server, verify, then revoke the
old key.

Persist the discovered path as ordinary server configuration if the framework
needs it, but never let a separate customer-entered value override it. If an
existing route differs, migrate it to the discovered path or stop and report
the collision. Changing the path later in RankWin requires rerunning this skill,
regenerating affected routes, and redeploying the customer application.

### 3. Choose one SEO-safe delivery architecture

Prefer **same-origin authenticated HTML proxying** when the customer accepts
RankWin's markup. The customer server injects the bearer header and proxies:

- `<site.blogPath>` → `<api-base>/articles?format=page`
- `<site.blogPath>/[slug]` → `<api-base>/articles/<slug>?format=page`
- `<site.blogPath>/sitemap.xml` → `<api-base>/sitemap.xml`
- `<site.blogPath>/feed.xml` → `<api-base>/feed.xml`

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
- one visible article `<h1>` from `title`, followed by the optional
  `featuredImage` (`{ id, url, alt }`), then the article content; keep the title
  and text-only layout when the image is `null`
- optional `featuredImage` in the index card
- article body from sanitized `html` or a complete structured-document renderer
- every object in `jsonLd` as `application/ld+json`
- publication verification meta tags: `rankwin-publication-id` from
  `article.publicationId`, `rankwin-content-version` from `article.contentVersion`,
  and `rankwin-snapshot-digest` from `article.snapshotDigest`. Emit them in the
  server-rendered document metadata when the digest is supplied. Frameworks may
  place metadata in the head or stream it as direct children of the body; it
  must be real HTML tags, not script strings or tags nested in article content.
  Preserve these fields through adapter types and both slug and by-ID reads. Search discovery checks
  the exact active publication before submitting its URL.
- published and modified timestamps
- crawlable index links using each summary's canonical URL/slug

RankWin's `html` is sanitized by the CMS renderer. Do not concatenate untrusted
customer input into it. If rendering `document`, exhaustively handle the
versioned block union and escape text/attributes.

Tables must remain real `<table>` elements with header `<th scope="col">` and
body `<td>` cells. Preserve all rows, columns, and inline formatting through
sanitization. Style cell padding, borders, header contrast, and vertical
alignment; wrap wide tables in a container that scrolls horizontally within
the article on mobile, without widening the page or squeezing words into
single-character columns. Check the actual comparison at desktop and mobile
widths. See the table CSS in `references/nextjs.md` (also usable by other
customer renderers). Do not hide raw pipe Markdown with CSS: if authenticated
delivery already contains a pipe-table paragraph, report an upstream RankWin
conversion defect and save a corrected revision through the normal publication
flow. Never mutate an immutable snapshot or regenerate the article to fix layout.

The `featuredImage.url` is the sole public-media exception to bearer
authorization. It is an immutable HTTPS URL intentionally loadable by browsers
and crawlers, so fetch it without the delivery key. Never turn a private
`/api/files/...` reference or another URL from article content into a public
asset proxy.

When `featuredImage` is non-null, render the exact public media URL in every
corresponding index card. Article detail pages must use this reading order in
both server HTML and the visible desktop/mobile layout: **title (`h1`) → featured
image → article content**. Place the image immediately after the headline, then
the description/byline/dates and main body. Do not place it above the headline
or use CSS ordering that differs from the DOM. This detail-page rule does not
change the customer's index-card layout. Preserve the supplied alt text and
aspect ratio; reserve image space to avoid layout shift. A CSS background or editor-only preview does not satisfy
this contract. Allow the authenticated API's media origin in image optimizers;
never hard-code a customer domain, product name, or article slug.

If the editor has an image but delivery returns null, inspect the saved article
revision and active publication snapshot. Images generated after the first draft
must be saved into a new revision and that revision republished through the
normal publication flow. Do not hide the defect with a stock placeholder, change
an immutable snapshot in place, or expose a private storage URL. Verify real
image bytes without authentication as well as rendered image tags on both pages.

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

Read `references/search-discovery.md` for the runtime sitemap, removal, and
Google/Bing connection contract. Fetch the sitemap at request time; a build-time
copy or hard-coded list is insufficient. Publishing must add the URL and
unpublishing/deleting must remove it without a customer rebuild.

Expose the RankWin sitemap under the customer origin or merge it into the
customer sitemap index. A public crawler reaches the customer route without a
key; the customer server privately fetches RankWin with the key. The XML
contains customer canonical URLs. Merely creating `<blogPath>/sitemap.xml` is
not discovery: either add its absolute URL as a `Sitemap:` line in the
customer's `robots.txt`, include it as a `<sitemap>` child of a real sitemap
index, or merge every published canonical into a registered root sitemap.
Never list a sitemap document as a `<url>` inside a URL set.

The configured `site.host`, each page's final response URL, its canonical link,
Open Graph URL, sitemap URL, and feed URLs must use the same hostname. A 301/302
from RankWin's configured canonical hostname to `www` (or the reverse) is a
failed integration; correct the RankWin site hostname or the customer's primary
domain before launch.

Choose exactly one GA4 page-view owner. If RankWin-rendered HTML has a configured
measurement ID, do not inject the same automatic page view again. For
customer-rendered JSON, normally let the customer layout own analytics.

### 8. Verify in loops

Run repository and deployment checks, then run from this skill directory:

```bash
python3 scripts/verify_integration.py \
  --api-base "$RANKWIN_CMS_API_BASE"
```

The verifier reads `RANKWIN_CMS_API_KEY` from the environment and never accepts
it as a command-line argument. It derives the customer URL from authenticated
`site.host` + `site.blogPath`; an optional `--customer-blog-url` must match that
exact URL. It follows every list cursor and checks every published article,
stable document node, canonical/final URL, initial HTML response, ETag, optional
featured image, sitemap, feed, and sitemap registration. Repeat fetch → inspect
→ fix → deploy → fetch until all deterministic checks pass.

For a live two-site isolation exercise, set a second entitled site's
`RANKWIN_CMS_OTHER_API_BASE` and `RANKWIN_CMS_OTHER_API_KEY`; the verifier proves
that neither valid key works against the other site. After a safe key rotation,
set the already-revoked secret as `RANKWIN_CMS_REVOKED_API_KEY` to prove it now
receives 401. These secrets remain environment-only.

The HTTP verifier prints any control it could not exercise instead of claiming
it passed. A consent-aware browser or GA4 DebugView must separately prove one
page-view event. Root-path mode also requires a customer-framework route-manifest
audit because a generic HTTP client cannot know every protected application
route.

The complete acceptance list is:

1. no/malformed key receives 401, while the configured key receives 200;
2. list JSON is `cms.v1` and every summary has `id`, slug, metadata, the
   customer canonical, and a valid nullable `featuredImage`;
3. ID detail returns the same `id`, a document ID, uniquely-IDed non-empty
   blocks, HTML, SEO, and JSON-LD;
4. another site's valid API base/key pair cannot retrieve the ID in either
   direction (live when the optional second-site environment is supplied, and
   always covered by RankWin's tenant-isolation test suite);
5. customer index and article return 200 `text/html`, not API JSON;
6. initial source contains title, canonical, body, and JSON-LD;
7. sitemap/feed contain only the intended site's customer URLs, and the sitemap
   is registered in robots.txt/a sitemap index or fully merged into a registered
   root sitemap;
8. `If-None-Match` produces 304 through an authorized request;
9. root-path mode does not shadow existing product/account routes (route-manifest
   plus browser regression when root mode applies);
10. exactly one analytics page view fires (consent-aware browser/GA4 DebugView);
11. after a replacement is installed, revoking the old key makes that old key
    receive 401 without interrupting the new one (live when the revoked-key
    environment is supplied, and always covered by RankWin's lifecycle tests).
12. when a featured image exists, it loads without a bearer key, appears in the
    initial customer index card, article HTML, Open Graph/Twitter metadata, and
    Article JSON-LD with meaningful alt text; when absent, no broken or empty
    image container is rendered. The visible article `h1` precedes the featured
    image, which precedes the body, in initial HTML and desktop/mobile browser
    checks; metadata, preload links, and breadcrumb text do not count as the title.
13. the deployed index path exactly equals authenticated `site.blogPath`; no
    hard-coded `/blogs` fallback or second customer-entered path is accepted.
14. the configured canonical hostname is the final non-redirecting hostname for
    the index, every article, sitemap, and feed.
15. `/.well-known/rankwin-site` returns no-store plain text exactly equal to
    `rankwin-site:<site.id>` from authenticated discovery, with no redirect.

Do not declare completion from an upstream API call alone. The canonical
customer URL and its initial HTML are the acceptance boundary.

16. publish/update/unpublish a disposable article when authorized: verify the
    customer sitemap reflects every transition without redeployment, and a
    removed detail URL returns 404/410. Report this lifecycle check as untested
    if no disposable article is available; do not delete existing content.
17. every structured table appears in initial customer HTML with matching
    headers, rows, and cell text; desktop/mobile browser checks confirm readable
    cells and horizontal scrolling confined to the table container.
