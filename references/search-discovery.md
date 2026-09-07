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

Each project has **Settings → Integrations → Connect Bing**. Authorize Bing
Webmaster and ensure the exact customer site is verified there. RankWin matches
the project site, submits published URLs and sitemaps, and observes Bing data.
If no verified matching site is found, verify it in Bing and reconnect.

For add/update/delete notifications through IndexNow, enable IndexNow in the
project's blog settings and obtain its generated ownership key. Serve
`https://<exact-customer-host>/<key>.txt` as public `text/plain` containing only
that key, without a redirect. This is a deliberately public IndexNow proof,
NOT `RANKWIN_CMS_API_KEY`; never substitute or expose the secret delivery key.
Reserve the route before any root slug catch-all. The file must stay available
after an article is removed. Test readiness in RankWin. RankWin-hosted CMS sites
serve the proof through the hosted resolver; pull adapters must serve it on the
customer origin. Do not claim IndexNow is ready until the public probe passes.

IndexNow supports removed URLs returning 404/410. Bing's ordinary SubmitUrl API
is for live URLs; do not use it as a deletion API. Bing connection alone enables
sitemap resubmission on removal; direct change notices also require IndexNow.
Neither service guarantees inclusion or immediate removal.

References: [Google sitemap submission](https://developers.google.com/webmaster-tools/v1/sitemaps/submit),
[Google Indexing API scope](https://developers.google.com/search/apis/indexing-api/v3/quickstart),
[Bing OAuth](https://learn.microsoft.com/en-us/bingwebmaster/oauth2),
[IndexNow protocol](https://www.indexnow.org/documentation).
