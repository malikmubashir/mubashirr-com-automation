# SEO and AEO setup before the first post ships

## One-time site setup

Do these once, in this order. Two to three hours total.

### 1. WordPress hardening and SEO foundation

Install RankMath (free tier is enough; Yoast also fine, RankMath has better schema controls). Configure:
- Site title and tagline (drop "Love for food :)" — too informal for SEO). Use something like "Mubashir's Kitchen — halal recipes with French technique".
- Set the homepage to a static page (currently it is the post feed; that limits keyword targeting on the homepage).
- Enable XML sitemaps. Submit to Google Search Console and Bing Webmaster Tools.
- Enable Open Graph and Twitter Card metadata generation.
- Set focus keyword reminders on for every new post.

### 2. Schema.org Recipe markup

This is non-negotiable for food blogs. Google's recipe rich results require it. The Writer agent generates JSON-LD per post; RankMath also handles it but the agent's version is more controlled. Ensure both do not double-emit (set RankMath recipe schema to "off" if Writer is handling it).

Test every post in [Google's Rich Results Test](https://search.google.com/test/rich-results) before publishing. The agent fails the build if schema is invalid.

### 3. Google Search Console + Analytics 4

Verify the domain. Submit the sitemap. Add Google Analytics 4 via GTM (not the legacy WP plugin; GTM gives you cleaner control). Set up conversion events for newsletter signup, recipe save, and external recipe-app click-through.

### 4. Author bio with E-E-A-T

Google's Helpful Content system heavily weights author signals. Create an `/about` page with:
- Your real name and credentials (the PhD signals expertise even outside CS, oddly)
- Where you cook (Paris/wherever) and for whom
- Why this site exists (the story — diaspora, family, French technique meets heritage)
- Photo (real, not stock)
- Link to LinkedIn or other public profile

Every post byline links to this. Schema.org Author markup points to it.

### 5. Internal linking rules

The Writer agent inserts three internal links per post: one to a related recipe, one to a technique post (e.g., "how to temper spices"), one to a category page. This is how a new site builds topical authority. The first 5 posts will not have related content; backlink them retroactively after week 6.

### 6. Pinterest business account + Rich Pins

Pinterest sends 60%+ of traffic to most food blogs once it kicks in. Set up:
- Pinterest business account
- Claim your domain
- Enable Rich Pins (uses your Recipe schema; auto-populates ingredients on pin)
- Create 5 starter boards: Halal Recipes, Healthy Weeknight, Pakistani Heritage, French Technique, Quick Dinners

### 7. AEO: prepare for LLM answer engines

Answer Engine Optimization is the new frontier. ChatGPT, Perplexity, Claude, and Google AI Overviews are increasingly the search frontend. To be cited:

Create `/llms.txt` at the site root. This file tells LLMs what your site is and which pages to prefer. Template:

```
# mubashirr.com
> Halal recipes with French technique, by Dr Mubashir.

## Recipes
- /recipes/<slug>: <title> — <one-line summary>

## About
- /about: Author bio and editorial standards.
```

The Archivist agent rebuilds this file every Sunday from the published posts.

Structure every post for extraction:
- Lead with a one-paragraph direct answer (LLMs lift these).
- Use Q&A format for the FAQ block at the end.
- Define ingredient substitutions explicitly ("instead of X you can use Y because Z").
- Use specific numbers and measures, not "a bit" or "to taste" alone.

This is exactly what the Writer prompt enforces.

## Per-post checklist (the Writer agent enforces these automatically)

Every published post must have:

- Focus keyword in title, slug, first paragraph, H2, image alt, and meta description
- 1,400–1,800 words
- 4 images with descriptive alt text
- Schema.org Recipe JSON-LD that passes Google's Rich Results Test
- At least 3 internal links
- At least 2 external authoritative links (cooking science, ingredient sources)
- FAQ section with at least 5 Q&As
- Meta description 140–155 characters
- Open Graph image set
- Pinterest-friendly vertical image with text overlay (1000x1500)

## What I am explicitly not doing

- Buying backlinks. Black-hat SEO is dead and dangerous.
- Stuffing keywords. The Writer agent's prompt blocks this.
- Spinning content. Every post is original.
- Mass-producing thin posts. One per week, well-built.

## What I am measuring

Weekly digest from the Archivist includes:

- Search Console: impressions, clicks, average position by query
- GA4: sessions, source/medium breakdown, top pages
- Pinterest: impressions, saves, outbound clicks per pin
- Email: subscribers, open rate, click rate
- Domain Rating from Ahrefs free tier or Moz DA

At 12 weeks, audit which posts ranked, which got pinned, which got social engagement. The next quarter's theme rotation favors what worked.
