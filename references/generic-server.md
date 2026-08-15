# Generic server, proxy, or edge runtime

The minimum integration is four fixed same-origin public routes whose server
handler makes authenticated upstream requests:

```text
/blogs                 -> <api-base>/articles?format=page
/blogs/:slug           -> <api-base>/articles/:slug?format=page
/blogs/sitemap.xml     -> <api-base>/sitemap.xml
/blogs/feed.xml        -> <api-base>/feed.xml
```

Store `RANKWIN_CMS_API_BASE` and `RANKWIN_CMS_API_KEY` in the platform's
server/worker secret store. On every upstream request set a new
`Authorization: Bearer <configured-key>` header. Do not forward the visitor's
Authorization, Cookie, query-supplied upstream URL, or arbitrary headers.

Order sitemap/feed before the slug catch-all. For root mode, preserve every
existing product route before `/:slug` and use a non-conflicting sitemap path.
Build upstream URLs from trusted configuration, percent-encode the slug once,
reject separators/control characters, and use bounded timeouts.

Preserve status and safe content/validator headers. Keep upstream responses
private; if caching a public response, key it by the configured site and route
and invalidate it on ETag change. A redirect to `rankwin.co` is not same-origin
delivery and must not be the final public article URL.

For a custom renderer, follow `references/api-contract.md`. Server-render the
list/detail and expose customer canonical, sitemap, and crawlable links in the
initial HTML.
