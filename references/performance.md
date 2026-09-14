# Blog performance and reader-load telemetry

Use this reference when the customer requests a performance audit or monitoring.
Reuse the site's existing telemetry transport; do not add a large browser SDK
or require a new monitoring vendor merely to integrate the CMS.

## Improve delivery while preserving crawlability

Measure representative short and long articles before and after the change,
using the same environment and several samples. Separate upstream adapter time,
HTML time to first byte, complete HTML transfer and browser-ready time. Do not
present an adapter microbenchmark as a whole-page improvement.

Resolve a slug with one fresh authenticated lookup, then fetch authoritative
detail by stable ID. Share the result between metadata and page rendering in
the same request. Do not walk a growing catalogue for each article or load a
large legacy Markdown/MDX catalogue in the CMS route's critical path. Lazy-import
legacy rendering only after establishing that the requested page is local.

Serve all article text, headings, links, TLDR and structured data in initial
server HTML. Keep the featured image eager when it is above the fold; reserve
its dimensions and lazily load below-fold images and optional embeds. Never
virtualize the article text or fetch sections only after scrolling. Verify full
initial HTML and metadata with the integration verifier after optimization.

Cross-request caching requires proven publish/update/delete, canonical redirect
and key-revocation behavior. Prefer removing duplicate work before adding it.

## Measure what the reader actually waits for

For full navigations, record request-start to the browser load event separately
from request-start to article readiness. Use Navigation Timing timestamps in the
same performance clock. For client navigation, measure from the navigation
intent to article readiness and identify it as a separate navigation type.
Route commit alone does not establish that the article is ready.

Define readiness explicitly: the current article body and an end marker are
mounted, the current hero is loaded/decoded or reports failure, required fonts
settle, and a visible frame has been observed. Track root replacement during
streaming/hydration and cancel observers for an obsolete navigation. Reset image
state when the source changes. Do not report a successful paint if a background
tab or timeout prevented frame observation; record that as incomplete instead.

Report a sanitized canonical path, navigation type, duration unit, completion
state and release identity. Never include query strings, credentials, user text
or arbitrary click URLs. Honor existing consent, Do Not Track and Global Privacy
Control rules. Exclude synthetic checks and incomplete/background samples from
reader averages, but retain separately identifiable diagnostic counts.

For Datadog, verify that events arrive and duration fields are numeric measures
before creating charts. Show averages and p95, sample counts, and the slowest
10–20 canonical paths. Keep full and client navigations separate. Label seconds
correctly when stored values are milliseconds. Preserve the existing dashboard,
back it up before updating, and verify a live release event in the final charts.

## Long-running verification

Preserve the checked publication ID, version, snapshot digest and receipts when
an audit is interrupted. Revalidate any changed publication rather than claiming
that old evidence covers it. A conditional ETag check can legitimately receive
200 if the publication changed between requests: compare fresh identity and
repeat the conditional pair. Do not silently treat all 200 responses as 304 or
discard the original failure. Keep secrets and capability-bearing media URLs
out of diagnostic files and user-facing reports.
