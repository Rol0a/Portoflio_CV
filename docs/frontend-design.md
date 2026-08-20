# Frontend Design System

This document is the source of truth for how the portfolio's frontend should
look, feel, and behave, and for the order new work gets built in. It exists
so that future changes — new pages, new components, a redesigned section —
stay consistent with the direction set here instead of drifting page by
page. If you're adding UI and unsure what it should look like, or what order
to build it in, this is where to check first; if a rule here no longer fits,
update this file in the same change that breaks it.

## 1. Direction

**The brief:** personal, cozy, familiar, easy to navigate. Not a SaaS
dashboard, not a stark minimalist gallery — a warm, individual space that
happens to also demonstrate engineering competence. The engineering rigor
lives in the architecture (see `architecture.md`); the frontend's job is to
make a visitor feel like they've landed somewhere considered and human.

**What that rules out:**
- Cold, high-contrast "tech startup" blue-on-white — too impersonal for a
  personal portfolio.
- Dense, information-heavy layouts — cozy means breathing room, not more
  content per screen.
- Motion for its own sake — every animation here earns its place by
  revealing content as the visitor scrolls to it, never decorating for
  decoration's sake.

**What that calls for:**
- A warm, specific palette (below) used with intention, not just swapped in
  for the old blue-on-white scheme.
- A serif display face for headings, paired with a humanist sans for body
  text — the pairing itself should feel like a considered choice, not a
  default.
- Soft, rounded shapes; warm-tinted shadows (never pure black); generous
  spacing.
- A Home page that unfolds as the visitor scrolls, rather than dumping
  everything above the fold or requiring immediate navigation.

**Provenance:** the palette direction was cross-checked against the
`ui-ux-pro-max` design-intelligence skill's style database
(github.com/nextlevelbuilder/ui-ux-pro-max-skill) — its "Nature Distilled"
style entry (terracotta/sand/cream/warmth, humanist sans, organic softness)
independently validated this direction as a real, named style rather than an
improvised one. Its first broad query match ("Brutalism," monochrome +
sharp corners) was a poor fit for "cozy" and was discarded — a reminder that
this tool's output needs the same verification-before-applying judgment as
any other search result, not blind application of the top hit. A later
full-system audit against the same database (color, typography, motion,
react-stack domains) confirmed the rest of this document's decisions and is
the source of the three follow-ups folded into §8 and §10 below.

## 2. Workflow: building new UI, in order

New UI on this site gets built in this order, every time — a new page, a new
showcase section (the doc's own example: a future "Talks" or "Writing"
section), or a redesign of an existing one. Skipping ahead to motion or
visual polish before the data and layout underneath it are solid is the most
common way a change ends up inconsistent with the rest of the site.

1. **Confirm against the tokens, not a blank page.** Before writing any CSS,
   check §3–§5 below for an existing `--color-*`, `--space-*`, `--font-*`,
   or radius token that fits. Reaching for a new hex value or a one-off
   spacing value is the signal to stop and re-check the token list, not to
   add one.
2. **Data hook before component.** A `use*` hook in `hooks/`, wired to
   `services/api.ts`, built and verified against real fetched data before
   any layout or motion exists — the way `useProjects`/`useCertifications`
   already work, and the way Home derives its stats row from the real
   fetched list rather than issuing a second filtered request.
3. **Static layout inside the standard container first.** Build the page or
   section as a plain, motionless component inside `.container`. Full-bleed
   and alternating-background treatment stay Home-only (§7) unless there's a
   specific reason to extend them — that's a deliberate decision to make at
   this step, not a default to reach for.
4. **Presentation component, real content only.** A new `*Card` (or
   equivalent) in `components/`, built against the actual data shape from
   step 2 — never lorem ipsum or a placeholder number. `StatCounter`'s
   figures are real, derived data for the same reason (§6).
5. **Motion layer last, and only what earns its place.** Wrap the finished,
   working layout in `InView`/`AnimatedGroup` as appropriate (§6). Reach for
   a bespoke primitive only if the existing five don't fit — and if a
   signature moment like `TextEffect` or `useMagnetic` seems tempting for a
   second spot, treat that temptation as a warning sign, not a green light
   (§6 explains why).
6. **Accessibility and reduced-motion pass, per primitive.** Confirm every
   new motion primitive or ref-based hook has its own reduced-motion check —
   the global CSS override doesn't reach a ref-write loop or a
   `useTransform` pipeline (§6, §9). Spot-check contrast on any new colored
   surface against whatever text sits on it (§3). If the change touches
   layout, walk it through the breakpoint checklist in §8.
7. **Update this document in the same change.** If a rule here no longer
   fits what you just built, fix the rule here, not just the code — an
   out-of-date design doc is worse than no design doc, because it actively
   misleads the next person who checks it first.

## 3. Color

### Source palette

The five anchor colors, as given, with their intended role:

| Hex | Role | Where it's used |
|---|---|---|
| `#EEE4E1` | Base — cream | Page background |
| `#E7D8C9` | Base — tan | Alternating section background, subtle fills |
| `#0A2E36` | Highlight — deep teal | Primary text, dark section backgrounds (footer, closing CTA) |
| `#02C39A` | Highlight — mint | Primary accent: CTAs, active nav state, links |
| `#63474D` | Contrast — mauve | Secondary/muted text, borders, eyebrow labels |

### Design tokens

Every color in the UI is a CSS custom property defined in
`frontend/src/styles/global.css` — **components never hardcode a hex
value.** The tokens:

```css
--color-bg           /* page background */
--color-bg-alt        /* alternating section background */
--color-surface        /* card/panel background, sits above bg */
--color-text          /* primary text */
--color-text-muted      /* secondary text, captions */
--color-primary        /* accent: buttons, links, active states */
--color-primary-dark     /* accent hover/pressed state */
--color-on-primary      /* text color placed on --color-primary */
--color-accent-deep      /* dark chrome: footer, closing band */
--color-on-accent-deep    /* text placed on --color-accent-deep */
--color-contrast        /* secondary accent: eyebrows, tags, borders */
--color-border / --color-border-strong
```

### The contrast rule that actually matters here

**Never place white text on `--color-primary` (`#02C39A`).** Mint at this
lightness measures roughly **2.3:1** against white — it fails WCAG AA even
for large text. Text placed on the mint accent must use `--color-on-primary`
(`#06262C`, a near-black teal), which measures **~6.4:1** — comfortably
passing. This was a real bug caught while building M9/M10's buttons (white
text on the old blue accent) and fixed by introducing the `--color-on-*`
tokens; don't reintroduce it. If you add a new colored surface, check its
contrast against whatever text sits on it before shipping.

### Dark mode

Dark mode is a real, supported reversal of the same five anchors — not a
separate palette. `#0A2E36` and `#EEE4E1` trade roles (deep teal becomes the
background, cream becomes the text), `#02C39A` stays as the accent (it has
enough contrast on both grounds), and `#63474D` lightens so it still reads
against a dark ground. Implementation follows the three-scope pattern:

1. Bare `:root` — the light palette (default, un-stamped state).
2. `@media (prefers-color-scheme: dark)` guarded by
   `:root:not([data-theme="light"])` — OS-level dark mode, unless the user
   explicitly chose light.
3. `:root[data-theme="dark"]` — an explicit in-app dark toggle, if one is
   ever added; wins over OS preference either direction.

If you add a component with its own local color (a chart, a badge), define
its light value in the base rule and its dark value in both of the above
scopes — never only inside a media query, or the un-stamped state (most
visitors) renders wrong.

### What's deliberately excluded from this system

The **admin analytics dashboard's chart colors** (`AdminDashboard.module.css`
— `--series-1`, `--series-2`, `--chart-surface`, etc.) are **not** part of
this palette. They're a separate, functional data-visualization palette,
validated for colorblind-safe categorical separation via the `dataviz`
skill's contrast checker. Don't "fix" them to match the brand palette — they
were chosen for a different reason (accessible data encoding, not brand
warmth) and re-theming them would silently break that validation. The
dashboard's *chrome* (backgrounds, borders, body text) does use the shared
tokens and updates automatically with the rest of the site.

`AdminDashboard.module.css` carries a one-line comment above its
`--series-*` block pointing back to this section, so a contributor who lands
in that file directly — without having read this doc first — sees the
exclusion before "fixing" it.

## 4. Typography

| Role | Face | Fallback stack | Where |
|---|---|---|---|
| Display | **Fraunces** | `Georgia, "Times New Roman", serif` | `h1`, `h2`, `h3` (set globally), hero headline |
| Body | **Karla** | `system-ui, -apple-system, "Segoe UI", sans-serif` | Everything else |

Both load from Google Fonts (the only external font host the project's CSP
allows). Fraunces is a soft, warm variable serif — it carries the "personal"
half of the brief without tipping into formal/corporate. Karla is a rounded
humanist sans that stays legible at small sizes and doesn't fight the serif
for attention. The design-intelligence database's font-pairing table has no
exact entry for this combination — its closest neighbors (a warm variable
serif with a rounded sans, used for personal/hospitality contexts) support
the general direction without confirming this specific pairing. That's
stated plainly rather than implied as a database match: this pairing is a
designer's choice, not a lookup result.

**Rules:**
- Headings (`h1`–`h3`) get the display face automatically — don't override
  `font-family` per-component for a heading.
- Body copy, form fields, nav, buttons: body face.
- Don't introduce a third face. If a component needs a monospace treatment
  (a code snippet, a tabular number), fall back to the system monospace
  stack rather than loading a fourth font.
- `text-wrap: balance` on headings, `text-wrap: pretty` on paragraphs are
  set globally — don't fight them with manual `<br>` line breaks.

## 5. Spacing, radius, shadow

Spacing is an 8-step scale (`--space-1` through `--space-7`, roughly
0.25rem → 6rem) — pick from the scale, don't hand-write arbitrary margins.

Radius: `--radius` (0.75rem) for form controls and small elements,
`--radius-lg` (1.5rem) for cards and images. The larger radius is part of
the "cozy" read — sharp corners feel clinical.

Shadows are warm-tinted, never pure black:
`rgba(var(--shadow-color), <alpha>)`, where `--shadow-color` is the deep
teal's RGB triplet (or pure black in dark mode, where a warm shadow would
just look muddy). Use a soft, low-alpha shadow at rest and a slightly
stronger one on hover — see `ProjectCard.module.css` /
`CertificationCard.module.css` for the reference values.

## 6. Motion

Motion here follows the **Motion Primitives** pattern (motion-primitives.com)
— that library ships as copy-in source rather than an npm package, so its
patterns live locally in `frontend/src/components/motion/`, built on the
`motion` package (the renamed Framer Motion):

- **`InView`** — fades and rises a block into view the first time it's
  scrolled to. Used for section headings and, on `ProjectDetail`, each
  case-study section.
- **`AnimatedGroup`** — staggers a grid of children into view as a wave
  rather than a flat fade. Used for every card grid (projects, certifications,
  skills).
- **`TextEffect`** — word-by-word blur+rise reveal. Used **once**, on the
  Home hero headline — this effect is a signature moment, not a default;
  don't sprinkle it on every heading.
- **`ParallaxBlob`** — a soft blurred decorative shape that drifts vertically
  as its section scrolls through the viewport (`useScroll` + `useTransform`,
  scoped to the element via `{ target: ref }`). Home-only, one per section,
  colored from `--glow-mint` / `--glow-mauve` / `--glow-tan` (low-opacity
  tints of the existing accent hues — never a new color). Pair every usage
  with the `.decor` wrapper class (§7) so the real content stacks above it
  correctly.
- **`ScrollProgress`** — a thin bar tracking overall scroll position
  (`useScroll` + `useSpring`), mounted once globally in `Layout.tsx`.

Two custom hooks apply the same philosophy without going through `motion`
directly — both write to CSS custom properties via a ref instead of React
state, so neither one re-renders the component on every `mousemove`. Both
return a plain `ref` object (from `useRef`) that the consumer attaches
directly to a host DOM element (e.g. `<Link ref={tilt.ref}>` in
`ProjectCard`) — neither hook, nor any component in this codebase, wraps a
component in `forwardRef` today, so there's nothing to migrate. The one
place this matters going forward: **if a future component needs to accept
and forward a ref from its parent** (not the current hooks' pattern, which
apply directly to a host element they already render), reach for React 19's
"accept `ref` as a plain prop" instead of `forwardRef` — but only once the
project is actually on React 19; it's pinned to `^18.3.1` today, where
`forwardRef` is still the correct tool if that need ever comes up first.

- **`useTilt`** (`hooks/useTilt.ts`) — 3D mouse-follow tilt + sheen highlight
  on `ProjectCard` and `CertificationCard`. Sets `--tilt-x`/`--tilt-y`/
  `--glow-x`/`--glow-y`; the card's own CSS reads them via
  `transform: rotateX(var(--tilt-x, 0deg)) ...`.
- **`useMagnetic`** (`hooks/useMagnetic.ts`) — cursor-attraction pull.
  Deliberately used on **one** element only (the Home hero's primary CTA) —
  a magnetic pull on every button reads as gimmicky, not considered.
- **`useCountUp`** (`hooks/useCountUp.ts`) — not a CSS effect at all: an
  IntersectionObserver-triggered `requestAnimationFrame` loop that ticks a
  displayed number up to its target with an ease-out-cubic curve. Backs the
  `StatCounter` component in Home's stats row. The numbers themselves are
  real, derived data (`projects.length`, distinct technology count,
  `certifications.length`) — never hardcode a stat that isn't computed from
  the actual fetched data.

**Rules:**
- Every motion primitive/hook checks reduced-motion (`useReducedMotion()` for
  `motion`-based ones, `window.matchMedia("(prefers-reduced-motion: reduce)")`
  for the ref-based hooks) and renders/behaves inertly when the visitor has
  requested it. This isn't optional — verify it when adding a new primitive.
  These checks are deliberately redundant (five separate checks, not one
  global kill switch): the global CSS `prefers-reduced-motion` override in
  `global.css` catches transition/animation-duration, but can't reach into a
  `useTilt` ref-write loop or a `ParallaxBlob`'s `useTransform` pipeline —
  those need their own check or they keep moving under the CSS override.
- Reveals trigger once (`viewport={{ once: true }}`), not on every scroll
  past — re-animating content the visitor has already seen reads as
  glitchy, not delightful.
- Easing is `cubic-bezier(0.22, 1, 0.36, 1)` everywhere (`--ease-cozy`) —
  **one deliberate exception**: the magnetic CTA uses a bouncy overshoot
  curve (`cubic-bezier(0.34, 1.56, 0.64, 1)`) to stand in for spring physics,
  scoped to that one button only. Don't introduce a third easing curve, and
  don't let the exception spread — if a second element wants spring-like
  motion, that's a sign to reconsider rather than copy the override.
- Prefer animating `transform`/`opacity` over layout properties. The skill
  proficiency bars are the reference example: the bar's *final* width is set
  once via plain CSS (`style={{ width: "...%" }}`), and the *reveal* animates
  `scaleX` from 0→1 with `transform-origin: left` — never animate `width`
  itself for a repeated/scroll-triggered effect.

**Two pitfalls worth knowing before touching this code:**
1. **A `motion.div` driven by a style value (`x`, `y`, `scale`, ...) sets its
   own inline `transform` on every frame, which silently overrides any
   `transform` your CSS class tries to set on that same element** (inline
   style wins the cascade). `ParallaxBlob`'s horizontal centering learned
   this the hard way — it uses `margin-left` instead of
   `left: 50%; transform: translateX(-50%)` for exactly this reason. If an
   element needs both a `motion`-driven transform and CSS-only positioning,
   do the positioning with a non-transform property.
2. **A bare class selector inside a `*.module.css` file gets scoped/hashed**,
   even if the class name (like `.container`) is meant to reference the
   *global* class from `global.css`. `.decor > .container { ... }` in a CSS
   Module compiles to a selector that matches nothing real — it has to be
   `.decor > :global(.container) { ... }`. Search for this pattern
   (`> .container`, `.container >`, etc.) inside any `*.module.css` file
   before assuming it works.

## 7. Layout patterns

**Container:** `.container` (global, `max-width: 72rem`, centered,
horizontal padding) wraps content on every page via `Layout.tsx`'s `<main>`.

**Full-bleed sections (Home only):** the Home page breaks individual
sections out to full viewport width for alternating backgrounds (the
`.fullBleed` pattern — `width: 100vw; margin-inline: calc(50% - 50vw)`),
with an inner `.container` for the actual content width. This is scoped to
Home; other pages stay within the standard container. If another page ever
needs a full-bleed section, reuse this exact pattern rather than inventing
a new one.

**Alternating section backgrounds:** Home alternates `--color-bg` and
`--color-bg-alt` section by section, which is what gives the scroll its
rhythm without needing dividers or heavy borders.

**Decorative depth (`.decor` + `.grain`, Home only):** any section that
places a `ParallaxBlob` pairs its full-bleed wrapper with the `.decor` class
(`Home.module.css`) — it establishes a stacking context and lifts the real
`.container` content above the blob regardless of DOM order. Sections that
also want the paper-grain texture (§6's "Nature Distilled" warmth) add the
global `.grain` utility class from `global.css` alongside it. Both are
additive — `.decor` handles stacking, `.grain` handles the visible texture —
so a section can use either alone or both together.

**Page-section spacing (non-Home pages):** every page other than Home wraps
its content in `<section className="page-section">` (a global utility in
`global.css`, bottom `padding-bottom` only) plus a `PageHeader` component at
the top (§10) for the top-side breathing room under the sticky header. Don't
add `padding-block` to `.container` itself to solve this — that would also
push down Home's full-bleed bands, which already carry their own padding and
are tuned to butt directly against the footer (§9's closing band).

**Header navigation:** the inline nav (`Header.tsx`) collapses to a toggled
dropdown panel below 720px, rather than wrapping onto multiple lines — the
`.menuToggle` button is hidden above that width and `.nav` reverts to its
normal inline flex layout. This threshold was set by the §8 breakpoint
check, not picked in the abstract — verify it still holds after any nav
content change (a longer name, a new nav item).

## 8. Responsive breakpoints

The site is checked at four widths — **375px, 768px, 1024px, 1440px** —
before any layout change ships. This isn't a set of CSS breakpoints defined
anywhere in the codebase (the layout is fluid/container-based, not
breakpoint-driven); it's the fixed set of viewport widths to actually resize
the browser to and look at, so "the container-based layout should just
work" stays a verified claim instead of an assumption.

Three areas get specific attention at 375px, because they're the most likely
to surprise:

- **Home's full-bleed hero and section bands** (§7) — confirm the
  `ParallaxBlob` decorative shapes don't overflow or force horizontal
  scroll, and that the stats row (`StatCounter` × 3) wraps or stacks
  legibly rather than compressing.
- **The `AnimatedGroup` card grid stagger** (§6) — `ProjectCard` and
  `CertificationCard` at a single-column width, including the `useTilt`
  sheen/tilt effect, which is a mouse-only interaction and should degrade to
  simply inert (not broken) on the touch-first viewport where it's tested.
- **The header nav** (§7) — confirm it's showing the toggled dropdown, not a
  wrapped multi-line inline nav. This is exactly what the first full pass of
  this checklist caught: at 375px the inline nav wrapped onto four cramped
  lines before the `.menuToggle` breakpoint was introduced. Any two-column
  page layout (About's info card, Contact's form + "elsewhere" panel, both
  §9) should also be re-checked here — they collapse to one column via their
  own `max-width` media queries, not this global breakpoint list.

Run this check whenever a layout or motion change lands, not just on new
pages — it's a five-minute pass, and it's the cheapest place to catch a
`.fullBleed` or grid change that only looks right at desktop width.

## 9. Page structure

**Home is a scrolling showcase, not a hub.** Structure, top to bottom:

1. **Hero** — name, tagline, intro, two CTAs (view projects / download CV),
   a real-data stats row (projects shipped / technologies used /
   certifications earned — `StatCounter`, §6), and a scroll cue that
   smooth-scrolls to the next section.
2. **Projects showcase** — Home fetches *all* projects/certifications once
   (`useProjects()` / `useCertifications()`, no server-side `featured`
   filter) and derives the featured subset client-side with `useMemo`,
   rather than issuing a second filtered request — the full list is what the
   stats row needs anyway (project count, distinct technology count), so one
   fetch serves both. The showcase itself is `ProjectShowcase` (§10) — a
   pinned two-column row per featured project, not a card grid — with a
   "view all" link to the full `/projects` list underneath. `/projects`
   itself still renders the plain `ProjectCard` grid (§7's standard
   container, no full-bleed/sticky treatment) — the pinned showcase is a
   Home-only moment, same as `.fullBleed`/`.decor`.
3. **Certifications showcase** — same data-flow pattern, linking to
   `/certifications`.
4. **Closing CTA** — a dark band (`--color-accent-deep`) inviting contact,
   linking to `/contact`.

Every other page (`/projects`, `/certifications`, `/skills`, `/about`,
`/contact`) is a conventional single-purpose page inside the standard
container — Home is the only page that gets the full-bleed scroll treatment.
`/projects` and `/certifications` both exist as dedicated full-list pages
*and* as featured showcases on Home — don't remove either; they serve
different visitors (browsing everything vs. skimming the highlights).

**Every non-Home page opens with `PageHeader`** (§10: eyebrow + `h1` +
optional intro, InView-revealed) — this is what gives `/about`, `/skills`,
`/projects`, `/certifications`, and `/contact` the same considered opening
beat Home's section heads have, instead of a bare `<h1>` sitting flush under
the sticky header. Two of these pages pair it with a secondary content panel
on wide viewports rather than leaving the page lopsided next to a short form
or a couple of paragraphs:

- **About** — bio paragraph beside a "Quick facts" card (location, email).
- **Contact** — the form beside a "Find me elsewhere" card, reusing the same
  location/email strings as About plus the footer's GitHub link, so nothing
  in that panel is invented content specific to the Contact page.

Both collapse to a single column under `max-width: 640px` /
`max-width: 720px` respectively (their own module CSS, not the global
breakpoint list) — verify at 375px per §8 whenever either changes.

**`ProjectShowcase`'s pinned row (Home only, §10):** each featured project is
a tall (`min-height: 80vh`) grid row — a sticky text column (title,
description, tech chips, "View details" + GitHub CTAs, a large low-opacity
Fraunces numeral) beside a visual column, alternating sides by index for
rhythm. `position: sticky` is pure CSS, not a `motion`/GSAP scroll-linked
system — deliberately, so it degrades to normal static flow for free under
`prefers-reduced-motion` and on narrow viewports (`max-width: 768px`),
without a bespoke JS pinning implementation to make accessible. This pattern
was adapted from a reference site's multi-screenshot stacking gallery; this
data model has one hero image per project, not a gallery, so the visual side
stays honest about that — a single image (or the same "coming soon"
placeholder `ProjectDetail` uses, see the missing-image fallback note in
§10) with a CSS-only rotated "ghost card" behind it, rather than fabricating
a deck of screenshots that don't exist. Getting the hero image onto the *list*
endpoint (rather than only `ProjectDetail`) required adding
`hero_image_url` to the backend's `ProjectListItem` schema and eager-loading
`Project.images` in `list_projects` — a small, honest plumbing change, not
new content.

## 10. Components

| Component | Purpose |
|---|---|
| `PageHeader` | Eyebrow + `h1` + optional intro, InView-revealed — the shared opening for every non-Home page (§9) |
| `ProjectShowcase` | Home-only pinned two-column project story per featured project — sticky text + numeral beside a visual (§9) |
| `ProjectCard` | Summary card — category, title, description, tech chips; `useTilt` mouse-follow tilt + sheen |
| `CertificationCard` | Summary card — issuer badge/initials, title, issue date, credential link; same `useTilt` treatment |
| `SkillCategory` | Category heading + skill list with `scaleX`-animated proficiency bars |
| `StatCounter` | One `useCountUp` figure + label — the Home stats row is three of these |
| `LanguageSwitcher` | EN/ES toggle — active state uses `--color-accent-deep`, not the mint accent, to keep the mint reserved for primary calls to action |

New showcase-style content (a new "Talks" or "Writing" section, say) should
follow the same shape: a `*Card` component in `components/`, a `use*` data
hook in `hooks/`, wired into both a Home showcase section and its own
`/route` list page — that's the established pattern end to end, and it's
step 2–4 of the workflow in §2.

**Missing-image fallback:** any `<img>` sourced from user-editable data
(a project's hero image, a certification's badge) gets an `onError` handler
that swaps to an on-brand placeholder — a dashed/soft box with a muted icon
and "Image coming soon" copy for `ProjectDetail`'s hero and `ProjectShowcase`'s
visual column, the existing initials badge for `CertificationCard`. The
error state resets per-item (keyed off the item's own id/slug/url) so a
broken image on one project or certification never carries over and hides a
working image on the next. This exists because the seed data references
upload paths with no file behind them yet — a broken native image icon is
the opposite of "considered," so every place that renders a data-driven
image needs this, not just the one that happened to be built first.

## 11. Accessibility

- Every interactive element has a visible `:focus-visible` state (global,
  2px accent outline) — don't remove it for aesthetics.
- Color is never the only signal: nav's active state uses both a filled
  background and `aria-current="page"`; the language switcher uses
  `aria-pressed`.
- `prefers-reduced-motion: reduce` disables scroll-reveal animation and the
  hero's bobbing scroll-cue icon globally (`global.css`) — confirmed by
  every motion primitive independently, not relied on as a single global
  kill switch (§6).
- Decorative SVGs (the scroll-cue chevron, certification badge
  placeholders) carry `aria-hidden="true"`.
- Layout changes get the breakpoint pass in §8 before shipping.

## 12. What's out of scope here

- The admin dashboard's data-visualization palette and chart components
  (see §3's exclusion note) — governed by the `dataviz` skill, not this doc.
- Backend/API/data-model documentation — see `architecture.md`.
- This system is light-mode-first with dark mode as a real but secondary
  concern; no additional visual themes (high-contrast mode, print
  stylesheet) are defined yet.
