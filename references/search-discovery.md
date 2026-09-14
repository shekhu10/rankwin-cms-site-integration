# Runtime sitemap and search discovery

The skill configures the customer adapter once. RankWin's durable publishing
jobs perform subsequent search submissions; do not put OAuth tokens or search
engine submission calls in visitor requests.

## Sitemap lifecycle

Proxy the authenticated `<api-base>/sitemap.xml` on every request at the
customer's `<blogPath>/sitemap.xml`. It reads active published snapshots and
contains their canonical URLs and modification times. It excludes drafts,
superseded versions and retracted publications. Do not copy its output into a
static file or manufacture an index-only response on error.

Register that customer route in robots.txt or the root sitemap index, retaining
all existing customer sitemap entries. A registered dynamic child is sufficient;
there is no need to rewrite the root index on each publication. If merging into
a root URL set, merge at runtime and preserve non-RankWin pages.

No-store is the default for sitemap, feed, index and detail. A cache is acceptable
only with tested publish/update/delete invalidation. SSG/static exports alone
cannot deliver these semantics. On removal, return 404/410 at the old article
URL and omit it from sitemap, feed and index. Removing a sitemap entry alone
does not remove a page from search results.

Verify a disposable article's publish, update and unpublish transitions without
rebuilding the customer site. Compare customer XML to authenticated upstream
XML, and check that the old detail URL returns 404/410. Do not remove real
customer content to exercise the test. Re-run the HTTP verifier after changes; pass `--removed-url <old-customer-url>`
(repeatable) to check already unpublished URLs without changing content.

## Google

In RankWin's project integrations, connect Google Search Console and choose the
verified property covering the customer canonical URL. RankWin needs the
`webmasters` scope for sitemap submission; reconnect older read-only grants.
RankWin verifies the public page and sitemap membership, submits the customer
sitemap, and uses URL Inspection to observe indexing separately.

Google provides no general blog URL “request indexing” API. Its Indexing API is
restricted to eligible JobPosting and BroadcastEvent/VideoObject pages. Do not
add misleading schema or use deprecated sitemap ping URLs. On removal RankWin
resubmits the updated sitemap after verifying 404/410; Google decides when to
recrawl and remove the URL. Manual URL Inspection remains available in Search
Console. Submission success is not proof of indexing or removal.

## Bing and IndexNow

Treat the Bing Webmaster account connection and IndexNow readiness as separate
states. IndexNow working does not mean a Bing OAuth grant exists, and a Bing
grant does not prove that the public IndexNow ownership file is reachable.

**Settings → Integrations → Connect Bing** requires the RankWin operator to
configure `BING_WEBMASTER_CLIENT_ID` and `BING_WEBMASTER_CLIENT_SECRET` in the web
and worker runtimes. The registered callback is the application's canonical
origin plus `/api/integrations/oauth/bing/callback`; use `webmaster.manage`.
Register or reuse the client in Bing Webmaster Tools' API Access settings. If
platform OAuth is unavailable, report it explicitly; do not label IndexNow as a
completed Bing account connection or ask the customer to invent client secrets.

Authorize the customer's Bing account and ensure the property covering the
canonical customer URL is verified. RankWin submits published URLs and sitemaps
and observes Bing data. If no verified matching site is found, verify it in Bing
and reconnect. When connecting several projects, inventory their owner,
workspace, canonical host and verified Bing property separately. Never copy an
encrypted grant between workspaces; use the normal connection flow and its
project-scoped encryption and audit trail.

For add/update/delete notifications through IndexNow, enable IndexNow in the
project's blog settings and generate a key or import the site's existing valid
IndexNow ownership key (8–128 ASCII letters, digits or hyphens). Serve
`https://<exact-customer-host>/<key>.txt` as public `text/plain` containing only
that key, without a redirect. This is a deliberately public IndexNow proof,
NOT `RANKWIN_CMS_API_KEY`; never substitute or expose the secret delivery key.
This is also different from a Bing Webmaster API credential. Preserve a working
key instead of rotating it as part of CMS setup. If an existing integration
serves only `/indexnow-key.txt`, provide the root `/<key>.txt` alias required by
RankWin's readiness probe while keeping the old route working.

Reserve the route before any root slug catch-all or tenant rewrite. A platform's
own static ownership file must not be intercepted by its hosted-tenant resolver;
keep tenant isolation intact when adding an exception. The file must stay available
after an article is removed. Test readiness in RankWin. RankWin-hosted CMS sites
serve the proof through the hosted resolver; pull adapters must serve it on the
customer origin. Do not claim IndexNow is ready until the public probe passes.

A successful local proof probe does not prove that the engine has validated
the key. If IndexNow still returns 403, record the refusal and inspect the
exact host and ownership route. Do not repeatedly resubmit every article or
erase the failed attempts. When a replacement CMS key is necessary, preserve
any legacy integration's key, verify the replacement with the provider, then
use an audited retry that retains the previous error and attempt count. Treat
202 as accepted with ownership validation pending; a later 200 confirms the
notification succeeded. Neither response establishes search indexing.

IndexNow supports removed URLs returning 404/410. Bing's ordinary SubmitUrl API
is for live URLs; do not use it as a deletion API. Bing connection alone enables
sitemap resubmission on removal; direct change notices also require IndexNow.
Neither service guarantees inclusion or immediate removal.

## Existing publications and verification

Enabling a connection does not prove that historical URLs were submitted.
Inventory current, unsuperseded publications for each project and use RankWin's
audited, idempotent discovery jobs for any requested catch-up. Preserve successful
receipts so a resumed batch does not submit those versions again. Keep batches
bounded and release database connections before waiting on external providers.
Verify the provider receipt and terminal job result; an enqueued job is not a
successful submission. Record notification acceptance separately from search
engine indexing observations.

A build-time script may notify only URLs directly listed in its local sitemap;
do not assume it traverses a dynamic child CMS sitemap. Verify that behavior and
let RankWin's publication jobs handle new CMS URLs without a customer rebuild.

References: [Google sitemap submission](https://developers.google.com/webmaster-tools/v1/sitemaps/submit),
[Google Indexing API scope](https://developers.google.com/search/apis/indexing-api/v3/quickstart),
[Bing OAuth](https://learn.microsoft.com/en-us/bingwebmaster/oauth2),
[IndexNow protocol](https://www.indexnow.org/documentation).
