/**
 * Single source of truth for the owner's public links.
 *
 * These live here rather than in the i18n bundles because they're identical in
 * every locale — duplicating them per language just invites the two copies to
 * drift. Display strings that *do* differ by locale (the "Email: …" and
 * "Location: …" lines) stay in `i18n/*.json` under `about`.
 */
export const GITHUB_URL = "https://github.com/Rol0a";

// Percent-encoded: the vanity slug contains "ó", and encoding it keeps the
// href valid everywhere rather than relying on browser normalisation.
export const LINKEDIN_URL = "https://www.linkedin.com/in/rodrigo-l%C3%B3pez-a9a696222/";

export const EMAIL = "mlopez2018ig@gmail.com";
