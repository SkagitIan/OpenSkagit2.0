# OpenSkagit Frontend Design Guide

This guide keeps new OpenSkagit interfaces visually consistent with the current homepage, city pages, and tax tool. Use it before adding or restyling any frontend view.

## Design Direction

OpenSkagit should feel clear, civic, local, and trustworthy. The interface should make public data easier to understand, not feel like a marketing site or a generic dashboard.

Favor:

- Plain-language headings
- Calm layouts with obvious hierarchy
- Tight, useful navigation
- Data-first tools that feel grounded and inspectable
- Moderate use of brand color as accents
- Responsive grids that collapse predictably
- Premium SaaS-style tool pages for logged-in workflows: crisp widgets, strong metric hierarchy, compact activity feeds, and obvious next actions

Avoid:

- Decorative blobs, orbs, heavy gradients, and ornamental illustrations
- Oversized cards nested inside other cards
- One-hue pages where everything is blue, teal, or beige
- Marketing hero layouts that delay the actual product
- Rounded pill buttons everywhere
- Hard-coded links when a Django route exists
- Report-like walls of facts where a dashboard summary, tabs, disclosures, or compact scroll areas would scan better

## Brand Tokens

Use these colors as the default palette. Define them as CSS custom properties on the top-level page wrapper when building a new section.

```css
--os-navy: #042C53;
--os-current: #0A2E38;
--os-teal: #00828A;
--os-teal-bright: #1AACB0;
--os-green: #7DB61C;
--os-blue: #0071BC;
--os-gold: #FDB913;
--os-slate: #3D4D5C;
--os-ink: #1f2937;
--os-muted: #617082;
--os-border: #dfe7ee;
--os-surface: #ffffff;
--os-soft: #f6f8f8;
```

Use color this way:

- Navy: primary app shell, dark tool pages, sticky nav.
- Teal: primary action, focus state, live/data signal. Primary action text on teal must be white.
- Green: OpenSkagit brand emphasis, success, active signal. Primary action text on green must be white.
- Blue: map/GIS/tax secondary accent.
- Gold: finance, caution, tax highlights.
- City accent: use `--city-accent` for place-specific pages and city cards.

## Typography

The base template loads `DM Sans`, `Inter`, and `JetBrains Mono`.

- Use `DM Sans` for major headings and important display text.
- Use system sans or `Inter` for body text and operational UI.
- Use `JetBrains Mono` only for code, IDs, parcel numbers when a technical feel helps.
- Keep letter spacing at `0` for normal text. Uppercase eyebrow labels may use positive spacing.
- Do not scale text directly with viewport width. Use `clamp()` with clear min and max values.

Recommended scale:

```css
h1: clamp(38px, 7vw, 68px);
h2: clamp(27px, 4vw, 36px);
h3: 20px to 24px;
body: 14px to 16px;
small labels: 11px to 13px;
```

## Layout

Use a single constrained inner container for most public pages:

```css
.os-page__container {
  width: min(100% - 32px, 1120px);
  margin: 0 auto;
}
```

For older full-width sections that use max padding, follow the existing pattern:

```css
padding-left: max(24px, calc((100vw - 1100px) / 2));
padding-right: max(24px, calc((100vw - 1100px) / 2));
```

Responsive grid defaults:

```css
.os-page__grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}

@media (max-width: 880px) {
  .os-page__grid-3 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 560px) {
  .os-page__grid-3 { grid-template-columns: 1fr; }
}
```

## Navigation

Use the shared visual language of `os-nav-v2` on public-facing pages. Keep it sticky, compact, and route-aware.

```html
<header class="os-nav-v2">
  <a href="/" class="os-nav-v2__logo">
    <img src="https://res.cloudinary.com/dfz4bhlzs/image/upload/v1768253765/logoicon_c_crop_w_480_h_467_x_0_y_0-Picsart-BackgroundRemover_uklqfi.png" alt="" width="26" height="26" class="os-nav-v2__logo-img">
    OpenSkagit
  </a>
  <nav class="os-nav-v2__links" aria-label="Site navigation">
    <details class="os-nav-v2__menu">
      <summary>Cities</summary>
      <div class="os-nav-v2__dropdown">
        {% for item in city_pages %}
          <a href="{% url 'city' item.slug %}">{{ item.name }}</a>
        {% endfor %}
      </div>
    </details>
    <a href="{% url 'tax_home' %}">Taxes</a>
  </nav>
</header>
```

Rules:

- Prefer `{% url %}` over literal paths for app routes.
- Use `aria-current="page"` on the active nav item.
- Keep labels short: `Cities`, `Taxes`, `Parcels`, `Permits`, `GIS`, `About`.
- Hide secondary nav on small screens unless a view needs mobile navigation.

## Page Types

### Simple Public Page

Use this for the homepage, about pages, static explainers, and lightweight civic pages.

```html
<div class="os-page-simple">
  <header class="os-nav-v2">...</header>
  <main>
    <section class="os-page-simple__hero">
      <div class="os-page-simple__container">
        <h1>Plain-language headline.</h1>
        <p class="os-page-simple__lede">One short paragraph explaining what this page does.</p>
      </div>
    </section>
    <section class="os-page-simple__section">
      <div class="os-page-simple__container">...</div>
    </section>
  </main>
</div>
```

Visual notes:

- Light background: `#ffffff`, `#f6f8f8`, or soft teal tint.
- Use a centered hero only when the page is introductory.
- Keep cards white, 8px radius, light border, subtle shadow.
- Use one primary CTA and one secondary CTA at most.

### Tool Page

Use this for search, parcel, tax, map, and analysis interfaces.

- Start with a useful control or result, not a marketing pitch.
- Dark navy hero/tool shell is acceptable when it frames a primary input.
- Keep tool panels dense and scannable.
- Use sticky side panels only when they materially improve comparison or inspection.
- Keep data sources visible near the relevant report or footer.

### Premium SaaS Dashboard

Use this for logged-in operational tools such as Parcel Book, parcel detail pages, watchlists, sync activity, AI workflows, and admin-style review screens.

The page should feel like a polished product dashboard: colorful but restrained, fast to scan, and clearly action-oriented.

Structure:

- Start with a dashboard hero or command header that identifies the current object or workflow.
- Put the most important metrics in a compact KPI strip directly under or inside the hero.
- Use a primary work column for charts, maps, AI summaries, and decision modules.
- Use a secondary rail for owner/source facts, activity, recent records, and dense dossier details.
- Prefer compact scroll areas, disclosure blocks, tabs, or grouped rows for long lists.
- Keep the first viewport useful: identity, key values, status, and the next likely action should all be visible.

Visual treatment:

- Use white surfaces on `--os-soft` with 8px radius, light borders, and subtle product-style shadows.
- Add color through thin accent bars, status badges, KPI icons, and category chips rather than large tinted panels.
- Use a small set of semantic accents: teal for primary/data, green for success, gold for finance/caution, blue for maps/GIS, red only for real risk or destructive attention.
- Give metric cards a strong number, short label, and tiny source/freshness note.
- Dense side panels can use `max-height` with internal scrolling when the data is secondary.
- For mobile, prefer app-list patterns over report cards: thumbnail or icon, primary label, one timely status, and compact action/status symbols.
- Watchlists should show current state and recent changes only. Avoid explaining why an item was saved on the list page; send deeper reasoning to the detail screen.
- Use real imagery or map/aerial thumbnails for parcel lists when available. It makes repeated parcel review feel inspectable and app-like.
- Use clean icon assets, inline SVG, or an existing icon library for product icons. Avoid hand-drawn CSS icons for inspectable app surfaces.
- Primary buttons must have sufficient contrast: white text on green/teal/dark fills, dark text only on pale or white secondary surfaces.

Avoid:

- Three equal fact columns that force long labels to wrap awkwardly.
- Long unbounded lists inside the main page flow.
- Charts that dominate the page without adjacent interpretation or controls.
- Repeating raw database labels as headings when a plain-language label exists.
- Dark text on saturated green or teal primary buttons.

Suggested layout:

```css
.os-dashboard {
  display: grid;
  gap: 18px;
}

.os-dashboard__hero {
  padding: 24px;
  border: 1px solid var(--os-border);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 18px 45px rgba(15, 23, 42, 0.07);
}

.os-dashboard__metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.os-dashboard__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 18px;
  align-items: start;
}
```

### City Page

Use `--city-accent` on the wrapper and propagate it through stats, links, and active states.

```html
<div class="os-city-page" style="--city-accent: {{ city.accent }};">
```

City pages should include:

- Place name and one local tagline
- A few concise stats
- Current questions or local activity when available
- A switcher to other cities

## Components

### Buttons

Buttons use 8px radius, strong text, and clear states.

```css
.os-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 46px;
  padding: 0 22px;
  border: 1px solid rgba(0, 130, 138, 0.25);
  border-radius: 8px;
  background: #ffffff;
  color: var(--os-teal);
  font-weight: 700;
  text-decoration: none;
}

.os-button--primary {
  border-color: var(--os-teal);
  background: var(--os-teal);
  color: #ffffff;
}
```

Use buttons for commands and primary links. Use plain text links inside dense reports.

### Cards

Cards should frame repeated items or compact tools.

```css
.os-card {
  min-width: 0;
  padding: 24px;
  border: 1px solid rgba(0, 130, 138, 0.18);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
}
```

Rules:

- Do not put cards inside cards.
- Keep card radius at 8px unless matching an existing older component.
- Use `min-width: 0` on grid children to prevent overflow.
- Use border-top or border-left accent bars for categories and city accents.

### Section Heads

```html
<div class="os-section-head">
  <p>Eyebrow</p>
  <h2>Section heading</h2>
  <span>Short supporting text.</span>
</div>
```

Use uppercase eyebrow text sparingly. It should label the section, not repeat the heading.

### Icons

Prefer simple line icons in a fixed square container:

```css
.os-icon-box {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid rgba(0, 130, 138, 0.18);
  border-radius: 8px;
  background: rgba(0, 130, 138, 0.08);
  color: var(--os-teal);
}
```

Use icons to orient the user, not to decorate the page.

### Inputs

Search and form inputs should be large enough to use comfortably and should not shift layout as suggestions load.

```css
.os-search-wrap {
  display: flex;
  align-items: center;
  border: 1.5px solid rgba(26, 172, 176, 0.4);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.07);
}
```

Always include:

- `autocomplete="off"` for parcel/address search when suggestions are custom.
- A stable suggestions container, even when empty.
- A visible focus state through border or shadow.

## Naming CSS

Use page-scoped BEM-style classes:

```css
.os-feature-page {}
.os-feature-page__hero {}
.os-feature-page__card {}
.os-feature-page__card--active {}
```

Guidelines:

- Prefix all custom classes with `os-`.
- Scope new classes to the page or app section.
- Reuse `os-nav-v2` for navigation.
- Prefer adding a new page block over changing broad global selectors.
- Keep CSS in `static/app.css` unless the app already owns a dedicated stylesheet.
- After CSS edits, bump the cache-bust query in `templates/base.html` if the changed styles affect shared pages.

## Django Template Rules

- Extend `base.html` unless the app has a strong reason for its own base.
- Use `{% url %}` for internal links.
- Pass route-driven lists like `city_pages` from views instead of hard-coding repeated navigation.
- Use `aria-label` for navs, maps, icon-only controls, and data regions.
- Use `aria-current="page"` for active nav states.
- Do not inline large scripts. Small page-only behavior is acceptable at the bottom of the template; shared behavior belongs in `static/js/`.

## Content Voice

OpenSkagit copy should be direct and useful.

Good:

- `Where did my property taxes go?`
- `Built from public data. Organized by place.`
- `Follow the Valley city by city.`
- `Click any parcel to see what it contributes to the city today.`

Avoid:

- Vague slogans without a local noun
- Overexplaining how to use obvious controls
- Internal database terms in headings
- Long paragraphs in cards

## Accessibility And Responsiveness

Before finishing a frontend change:

- Check desktop and mobile widths.
- Confirm no text overlaps or escapes its container.
- Confirm nav and primary actions are keyboard reachable.
- Confirm `alt=""` is used for decorative logo images inside already-labeled links.
- Confirm data visualizations have labels or surrounding explanatory text.
- Keep tap targets at least 40px high where practical.

## Implementation Checklist

Use this checklist for every new frontend view:

- Page has a top-level `os-*` wrapper.
- Palette uses the approved tokens.
- Navigation uses current Django routes.
- Layout uses a constrained container or established full-width app shell.
- Cards/buttons use 8px radius.
- Text scale is bounded with `clamp()` or fixed sizes.
- Repeated items use responsive grids with `minmax(0, 1fr)`.
- Mobile layout has been considered explicitly.
- Cache-bust string is updated when shared CSS changes.
- `python manage.py check` passes in the project virtualenv.
