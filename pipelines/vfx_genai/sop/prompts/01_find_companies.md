# Stage 1: Find companies

**Goal:** add at least `<N>` new, de-duplicated companies to `company_master.csv`, each tiered by strength of generative-AI evidence. Companies only: no people yet.

## What counts as a company

A real, active production business (studio, production house, VFX, animation, virtual production, dubbing, creative or ad studio that makes video/film/imagery) that shows generative-AI use in its own work. Located in an approved country. Not India.

Reject: AI tool/SaaS platforms, marketing/SEO/PR/web/branding/consulting agencies, publishers, broadcasters/TV stations, educators, research bodies, investors, marketplaces, large agency networks and brand groups.

## Step 1: Discover (best actors first)

Use the cheapest source that gives a **website** per company.

1. **Google Maps scraper** (`compass/crawler-google-places`, about $0.004 per business). Run **AI-worded** searches per city, not generic ones. Pilot result: AI-worded searches gave about 3x more AI companies per dollar and much stronger evidence than "video production company".
   - English phrases: `AI video production studio`, `generative AI creative studio`, `AI animation studio`, `AI film production company`, `AI advertising studio`.
   - Add the local-language phrase per country (for example `KI Videoproduktion`, `production vidéo IA`, `producción audiovisual IA`, `produtora de vídeo IA`, `生成AI 映像制作`).
   - One run per city, with all phrases in `searchStringsArray`, `maxCrawledPlacesPerSearch` about 30, `scrapeContacts` off.
   - Cover every approved country; use the major 150 cities, then smaller cities.
2. **Apify lead finder** (`microworlds/leads-finder`): returns the company website *and* a decision-maker together. Use only when you also want people. It is about 20x worse per strong AI company than Maps for discovery alone.
3. **Tavily web search** is free but only when keys have credit. Use AI-worded queries by city. Expect about 25% new domains per query.
4. **Directories / award lists** (AI film festival finalists, studio partner programs): fetch the public pages and extract company sites.

Do not use: LinkedIn company search actors that only return LinkedIn pages without a website, or profile-search actors filtered by company page (both returned irrelevant companies).

## Step 2: Dedupe

Remove any domain already in `company_universe.json`, the crawl results, any company already on the Linkedin/X/Stage 32 tabs, and any domain in a rejected log. Blocklist social, news, directories, big tech, `.edu`, `.gov`.

## Step 3: Crawl and tier

Run `pipeline/company_crawl.py` (home, /about, /work, /portfolio, /ai, /services, /projects). It records country, what the site does and AI signals.

Tier rules:
- **A+**: strong AI signal 3 or more times (named tools such as Midjourney, Runway, Sora, Veo, Kling, ComfyUI, Stable Diffusion, or "made with AI", "AI-generated film/video/ad") and production score 2 or more and not SEO/software.
- **A**: strong AI signal at least once, same conditions.
- **B**: loose AI mention 3 or more times, production score 2 or more, not SEO/software.
- **C**: one loose mention. Keep, but lowest priority.
- Drop: SEO/software-looking sites (3 or more SEO/software keywords on home/about), non-production sites, unreachable sites.
- Watch for false positives: "runway" (fashion/airport), "flux", "veo", a company named Firefly.

## Step 4: Output

Append to `company_master.csv`: tier, domain, company, website, country, city, LinkedIn company URL, Twitter, AI evidence snippet, hit counts, site title and description. Report counts per tier and the cost per qualifying company.

## Budget

Pilot 25 places first. Typical target: under $0.10 per A/A+ company. Cap spend per run and stop at the cap.
