# TaxShift Design Guide

TaxShift.co is the public-facing property tax snapshot tool inside OpenSkagit. It should feel like a real civic utility: immediate, calm, trustworthy, and centered on the search form.

## Product Feel

TaxShift should read as the tool itself, not a preview of a tool. The first viewport should expose the live property search and enough context to make people comfortable using it.

Favor:

- A direct, working search form in the hero
- Plain explanations of tax shifts and data sources
- White surfaces over a cool civic background
- Teal for primary actions, focus, and live-data emphasis
- Navy for headings, numbers, and structural contrast
- Compact sections that keep the search task prominent

Avoid:

- Fake browser chrome, screenshot frames, device mockups, or thick black preview borders
- Marketing-only hero sections that push the form below the fold
- Decorative blobs, heavy gradients, or purely ornamental illustrations
- Nested cards and large floating card stacks
- Overly playful language for tax, levy, or public-record concepts

## Core Tokens

Current CSS lives in `static/app.css` under `/* TAXSHIFT HOME */`.

```css
--taxshift-ink: #081a35;
--taxshift-text: #20334f;
--taxshift-muted: #526173;
--taxshift-soft: #eef6f7;
--taxshift-surface: #ffffff;
--taxshift-teal: #18b7ca;
--taxshift-teal-dark: #0e9aa4;
--taxshift-border: rgba(8, 26, 53, 0.1);
```

Use teal sparingly for actions and active/focus states. Use navy for the brand, headings, step markers, and high-confidence UI. Keep backgrounds light and quiet.

## Typography

The shared base template loads `DM Sans`, `Inter`, and `JetBrains Mono`.

- Use `DM Sans` for the logo, hero heading, section headings, and step labels.
- Use `Inter` or system sans for body copy, forms, navigation, and operational UI.
- Use uppercase eyebrow labels only for compact metadata such as `Property tax snapshots`.
- Keep normal text letter spacing at `0`; uppercase eyebrow labels may use positive spacing.

Current scale:

```css
hero h1: clamp(42px, 6vw, 68px);
hero subcopy: clamp(16px, 2vw, 19px);
section h2: clamp(28px, 4vw, 42px);
body: 14px to 16px;
small labels: 12px to 13px;
```

## Layout

Use constrained, centered containers:

```css
.taxshift-nav { width: min(100% - 40px, 1100px); }
.taxshift-hero,
.taxshift-signup,
.taxshift-data { width: min(100% - 40px, 1040px); }
```

The hero is the main tool area. It may use a single white panel with a subtle border and shadow, but it should not look like a screenshot, browser window, app preview, or device frame.

Responsive behavior:

- At tablet width, allow nav links and form controls to wrap.
- At mobile width, hide secondary nav links and keep the primary `Free search` CTA visible.
- Collapse the three-step explanation to one column under the search form.

## Hero

The hero should include, in order:

1. Eyebrow: county and product scope
2. H1: direct user outcome
3. Short explanation
4. Live address/parcel search form
5. Data confidence note
6. Three compact steps explaining the workflow

The search field is the product. Give it the strongest affordance on the page with a teal border, visible focus treatment, and a clear CTA.

## Components

Navigation:

- Brand mark plus `taxshift.co`
- Three short links maximum before the CTA
- Primary nav CTA uses teal background and white text

Search:

- One-line input on desktop
- Full-width button on mobile
- Suggestions appear directly below the input and are left-aligned

Signup:

- Two-column section on desktop
- Single-column on mobile
- Labels are uppercase and compact
- Inputs use a restrained border, not heavy card styling

Footer:

- Dark navy/black footer is acceptable as a hard page stop
- Keep links minimal: TaxShift, Tax tool, OpenSkagit, Contact

## Voice

Write like a civic data tool that respects the user.

- Use: `Track your tax shift`, `Get snapshot`, `Data sources`, `Find your property`
- Avoid: hype, jokes, investor-style SaaS copy, or vague promises
- Explain taxes in plain English, especially when mentioning levies, rates, assessment changes, and agencies

## Implementation Notes

- Keep TaxShift-specific classes prefixed with `taxshift-`.
- Prefer Django `{% url %}` for internal routes.
- Keep htmx attributes on the live search input and signup form.
- When changing the main CSS, update the static query string in `templates/base.html` so browsers fetch the new stylesheet.