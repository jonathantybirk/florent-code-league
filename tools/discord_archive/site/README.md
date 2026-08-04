# The feed page

`index.astro` is the page that renders `feed.json`. It lives here rather than in
the site repo because the feed is not currently in use — keeping it here means
the site carries no dead route, while the page itself stays in version control
and ready to reinstall.

To put it back:

    cp tools/discord_archive/site/index.astro \
       ../portfolio/src/pages/discord/index.astro

and add `"/discord"` back to the `UNLISTED` array in `portfolio/astro.config.mjs`
so it stays out of the sitemap. The page already passes `noindex` to
`PageLayout`, which is the half that actually keeps it out of a search index —
the sitemap entry only controls whether the URL is volunteered.

The page fetches `/discord/data/feed.json` at runtime and re-polls it every 60
seconds, so it picks up a new bundle without a rebuild. It renders threads
newest first, with topic filter chips, and each message carries a deep link back
to the original in Discord alongside its text.

Note that `PageLayout` and `BaseHead` in the site repo gained a `noindex` prop to
support this; that change is already committed there and is independent of
whether this page is installed.
