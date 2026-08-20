/**
 * Admin data palette — mirrored from the `:root[data-admin]` block in
 * styles/global.css.
 *
 * It has to be mirrored rather than read. Recharts writes colors into SVG
 * *presentation attributes* (`stroke="…"`, `fill="…"`), and `var(--token)` is
 * not resolved there — presentation attributes don't run the custom-property
 * cascade. So charts need literal hexes, while the surrounding chrome reads the
 * CSS block. Change one, change both.
 *
 * The values are slots 1-3 of the `dataviz` skill's reference categorical
 * palette plus its fixed status palette, validated all-pairs against a pure
 * white surface: worst CVD dE 9.2 (deutan), worst normal-vision dE 24.0, and
 * aqua at 2.82:1 — under the 3:1 mark bar, which is why every chart that uses
 * DATA_3 also ships a table view. See docs/frontend-design.md §3.
 */
export const DATA_1 = "#2a78d6";
export const DATA_2 = "#eb6834";
export const DATA_3 = "#1baf7a";

export const STATUS_GOOD = "#0ca30c";
export const STATUS_WARNING = "#fab219";
export const STATUS_CRITICAL = "#d03b3b";

export const GRID_LINE = "#e4e4e7";
export const AXIS_LINE = "#a1a1aa";
export const INK_MUTED = "#52525b";
export const SURFACE = "#ffffff";
