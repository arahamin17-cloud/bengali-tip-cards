#!/usr/bin/env node
/**
 * generate-tip-cards.mjs — social-media "photo cards" built from CSV rows.
 *
 * Text comes from CSV rows (columns: category, title, tip) — typically the
 * output of scripts/clean_text_to_csv.py — and the card is rendered as SVG and
 * rasterised with sharp. Derived from the OG image generator used on
 * techtips.fun (scripts/generate-social-assets.mjs); the difference is that the
 * text is read from a CSV instead of blog frontmatter.
 *
 * Usage
 *   node scripts/generate-tip-cards.mjs                          # defaults
 *   node scripts/generate-tip-cards.mjs --csv tips.csv --out-dir cards
 *   node scripts/generate-tip-cards.mjs --template og --photo assets/portrait.webp
 *   node scripts/generate-tip-cards.mjs --limit 5 --captions
 *
 * Run `node scripts/generate-tip-cards.mjs --help` for every option.
 */

import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '..');
const bundledFontDir = path.join(scriptDir, 'assets', 'fonts');

// ---------------------------------------------------------------------------
// Brand tokens — kept identical to generate-social-assets.mjs so tip cards and
// OG cards look like they came from the same brand kit.
// ---------------------------------------------------------------------------
const colors = {
  background: '#101214',
  grid: '#262a2b',
  white: '#f7f8f6',
  muted: '#919594',
  lime: '#b6ff2b',
  ink: '#0a0c0c',
};

// Noto Sans Bengali first so Bengali glyphs render, Noto Sans as the Latin
// fallback. Both ship in scripts/assets/fonts.
const fontFamily = "'Noto Sans Bengali', 'Noto Sans', 'DejaVu Sans', Arial, sans-serif";
const fontFamilyBold = fontFamily;

// Brand strings shown on the cards. Override any of them from the CLI with
// --brand, --initials, --handle, --author and --tagline.
const brand = {
  name: 'Face By Sumona',
  initials: 'FS',
  handle: '@facebysumona',
  author: 'Face By Sumona',
  tagline: 'Skin · Hair · Makeup',
  website: 'www.trueface.bond',
  phone: '01933211642',
};

// ---------------------------------------------------------------------------
// Font bootstrap
//
// sharp renders SVG text through fontconfig, so a machine with no Bengali font
// installed would draw tofu boxes. We point fontconfig at the fonts bundled in
// scripts/assets/fonts (keeping the usual system font dirs as well) by writing
// a temporary fonts.conf and exporting FONTCONFIG_FILE. This must happen before
// sharp is imported, hence the dynamic import below.
// ---------------------------------------------------------------------------
async function bootstrapFonts() {
  if (process.env.FONTCONFIG_FILE) return { source: 'env', file: process.env.FONTCONFIG_FILE };

  let bundled = [];
  try {
    bundled = (await fs.readdir(bundledFontDir)).filter((f) => /\.(ttf|otf|ttc)$/i.test(f));
  } catch {
    bundled = [];
  }

  const dirs = [
    bundled.length ? bundledFontDir : null,
    '/usr/share/fonts',
    '/usr/local/share/fonts',
    path.join(os.homedir(), '.fonts'),
    path.join(os.homedir(), '.local', 'share', 'fonts'),
  ].filter(Boolean);

  const confDir = await fs.mkdtemp(path.join(os.tmpdir(), 'tip-cards-fc-'));
  const cacheDir = path.join(confDir, 'cache');
  await fs.mkdir(cacheDir, { recursive: true });
  const confPath = path.join(confDir, 'fonts.conf');
  await fs.writeFile(
    confPath,
    `<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
${dirs.map((dir) => `  <dir>${dir}</dir>`).join('\n')}
  <cachedir>${cacheDir}</cachedir>
</fontconfig>
`,
    'utf8',
  );
  process.env.FONTCONFIG_FILE = confPath;
  return { source: bundled.length ? 'bundled' : 'system', file: confPath };
}

const fontInfo = await bootstrapFonts();
const sharp = (await import('sharp')).default;
// ---------------------------------------------------------------------------
// CSV reading — the one real change vs. the OG generator, which read markdown
// frontmatter. Handles BOM, CRLF, quoted fields and embedded commas/newlines.
// ---------------------------------------------------------------------------
function parseCsv(source) {
  const text = source.replace(/^\uFEFF/, '');
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += char;
      }
      continue;
    }
    if (char === '"') quoted = true;
    else if (char === ',') {
      row.push(field);
      field = '';
    } else if (char === '\r') {
      // ignore, \n handles the row break
    } else if (char === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else field += char;
  }
  if (field !== '' || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((cells) => cells.some((cell) => cell.trim() !== ''));
}

async function readTips(csvPath) {
  const table = parseCsv(await fs.readFile(csvPath, 'utf8'));
  if (!table.length) return [];

  const header = table[0].map((cell) => cell.trim().toLowerCase());
  const known = ['category', 'title', 'tip'];
  const isHeader = known.some((name) => header.includes(name));
  const index = (name, fallback) => {
    const at = header.indexOf(name);
    return at === -1 ? fallback : at;
  };
  const cols = isHeader
    ? { category: index('category', 0), title: index('title', 1), tip: index('tip', 2) }
    : { category: 0, title: 1, tip: 2 };

  return table
    .slice(isHeader ? 1 : 0)
    .map((cells) => ({
      category: (cells[cols.category] ?? '').trim(),
      title: (cells[cols.title] ?? '').trim(),
      tip: (cells[cols.tip] ?? '').trim(),
    }))
    .filter((tip) => tip.title || tip.tip);
}

// ---------------------------------------------------------------------------
// Text helpers (same spirit as the OG generator's wrapTitle, but width-aware
// so long Bengali sentences wrap sensibly).
// ---------------------------------------------------------------------------
function escapeXml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

// Rough advance-width model. Bengali/Devanagari clusters are wider than Latin.
function estimateWidth(text, fontSize) {
  let units = 0;
  for (const char of String(text)) {
    const code = char.codePointAt(0);
    if (char === ' ') units += 0.28;
    else if (code >= 0x0980 && code <= 0x0dff) units += 0.6;
    else if (code >= 0x2e80) units += 1;
    else if (/[iljtf.,;:!'|]/.test(char)) units += 0.3;
    else if (/[A-Z0-9]/.test(char)) units += 0.62;
    else units += 0.53;
  }
  return units * fontSize;
}

function wrapToWidth(text, { fontSize, maxWidth, maxLines = Infinity }) {
  const words = String(text).trim().split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && estimateWidth(candidate, fontSize) > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);

  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    let last = kept[kept.length - 1];
    while (last.length > 1 && estimateWidth(`${last}…`, fontSize) > maxWidth) {
      last = last.slice(0, -1).trimEnd();
    }
    kept[kept.length - 1] = `${last}…`;
    return kept;
  }
  return lines;
}

// Filenames stay ASCII and URL-safe: prefer the latin part of the category
// (e.g. "ত্বকের যত্ন (Skincare)" -> "skincare"), then the headline, then "tip".
function asciiSlug(...values) {
  for (const value of values) {
    const slug = String(value ?? '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 40);
    if (slug) return slug;
  }
  return 'tip';
}

function textLines(lines, { x, startY, lineHeight, size, fill, weight = 400, family = fontFamily }) {
  return lines
    .map(
      (line, i) =>
        `<text x="${x}" y="${Math.round(startY + i * lineHeight)}" fill="${fill}" font-family="${family}" font-size="${size}" font-weight="${weight}">${escapeXml(line)}</text>`,
    )
    .join('\n  ');
}

function imageDataUri(buffer, mime = 'image/png') {
  return `data:${mime};base64,${buffer.toString('base64')}`;
}
// ---------------------------------------------------------------------------
// Card templates
// ---------------------------------------------------------------------------

function brandBadge(x, y) {
  const width = Math.round(estimateWidth(brand.name, 20) + 44);
  return `<rect x="${x}" y="${y}" width="${width}" height="40" rx="20" fill="${colors.lime}"/>
  <text x="${x + 22}" y="${y + 27}" fill="${colors.ink}" font-family="${fontFamilyBold}" font-size="20" font-weight="700" letter-spacing="0.3">${escapeXml(brand.name)}</text>`;
}

function avatarBadge(cx, cy, r) {
  return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${colors.lime}" stroke-width="2"/>
  <text x="${cx - Math.round(r * 0.6)}" y="${cy + Math.round(r * 0.26)}" fill="${colors.lime}" font-family="${fontFamilyBold}" font-size="17" font-weight="700">${escapeXml(brand.initials)}</text>`;
}

function gridOverlay(width, height, step = 90) {
  const rows = [];
  for (let y = step; y < height; y += step) rows.push(`M0 ${y}H${width}`);
  const cols = [];
  for (let x = step; x < width; x += step) cols.push(`M${x} 0V${height}`);
  return `<g stroke="${colors.grid}" stroke-width="1" opacity="0.8"><path d="${rows.join(' ')}"/><path d="${cols.join(' ')}"/></g>`;
}

/**
 * Photo card: full-bleed background photo (or brand grid), bottom-anchored
 * text stack. Layout is anchored to the bottom and scaled off the width, so it
 * works for 1080x1080, 1080x1350 and 1200x630 alike.
 */
function buildPhotoCardSvg({ width, height, category, title, tip, backgroundUri }) {
  const pad = Math.round(width * 0.062);
  const titleSize = Math.round(width * 0.058);
  const tipSize = Math.round(width * 0.033);
  const catSize = Math.round(width * 0.023);
  const titleLineHeight = Math.round(titleSize * 1.3);
  const tipLineHeight = Math.round(tipSize * 1.6);
  const maxTextWidth = width - pad * 2;

  const tipLines = wrapToWidth(tip, {
    fontSize: tipSize,
    maxWidth: maxTextWidth,
    maxLines: Math.max(2, Math.min(6, Math.floor((height * 0.34) / tipLineHeight))),
  });
  const titleLines = wrapToWidth(title, {
    fontSize: titleSize,
    maxWidth: maxTextWidth,
    maxLines: 3,
  });

  const footerBaseline = height - pad;
  const chipHeight = Math.round(catSize * 1.9);

  // Lay the text block out as one unit and place it in the free space between
  // the brand row and the footer, slightly above centre. This keeps short tips
  // from leaving a huge hole at the top of the card.
  const gapChipTitle = Math.round(titleLineHeight * 0.75);
  const gapTitleAccent = Math.round(tipLineHeight * 0.55);
  const gapAccentTip = Math.round(tipLineHeight * 0.95);
  const titleBlockHeight = Math.max(0, titleLines.length - 1) * titleLineHeight;
  const tipBlockHeight = Math.max(0, tipLines.length - 1) * tipLineHeight;
  const blockHeight =
    chipHeight + gapChipTitle + titleBlockHeight + gapTitleAccent + gapAccentTip + tipBlockHeight;

  const topLimit = pad + 40 + Math.round(height * 0.06);
  const bottomLimit = footerBaseline - Math.round(height * 0.075);
  const freeSpace = bottomLimit - topLimit;
  const blockTop =
    freeSpace > blockHeight ? topLimit + Math.round((freeSpace - blockHeight) * 0.5) : topLimit;

  const chipY = blockTop;
  const titleStartY = chipY + chipHeight + gapChipTitle;
  const accentY = titleStartY + titleBlockHeight + gapTitleAccent;
  const tipStartY = accentY + gapAccentTip;

  const background = backgroundUri
    ? `<image href="${backgroundUri}" x="0" y="0" width="${width}" height="${height}" preserveAspectRatio="xMidYMid slice"/>`
    : `<rect width="${width}" height="${height}" fill="${colors.background}"/>\n  ${gridOverlay(width, height)}`;

  const chipText = category || 'Beauty tips';
  const chipWidth = Math.min(
    maxTextWidth,
    Math.round(estimateWidth(chipText, catSize) + catSize * 2.2),
  );

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <linearGradient id="scrim" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0a0c0c" stop-opacity="0.55"/>
      <stop offset="0.45" stop-color="#0a0c0c" stop-opacity="0.72"/>
      <stop offset="1" stop-color="#0a0c0c" stop-opacity="0.95"/>
    </linearGradient>
    <linearGradient id="accentFade" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="${colors.lime}"/>
      <stop offset="1" stop-color="${colors.lime}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  ${background}
  <rect width="${width}" height="${height}" fill="url(#scrim)"/>
  ${brandBadge(pad, pad)}
  ${avatarBadge(width - pad - 27, pad + 20, 27)}
  <rect x="${pad}" y="${chipY}" width="${chipWidth}" height="${chipHeight}" rx="${Math.round(chipHeight / 2)}" fill="none" stroke="${colors.lime}" stroke-width="2"/>
  <text x="${pad + Math.round(catSize)}" y="${chipY + Math.round(chipHeight * 0.68)}" fill="${colors.lime}" font-family="${fontFamily}" font-size="${catSize}" font-weight="600">${escapeXml(chipText)}</text>
  ${textLines(titleLines, { x: pad, startY: titleStartY, lineHeight: titleLineHeight, size: titleSize, fill: colors.white, weight: 700 })}
  <line x1="${pad}" y1="${accentY}" x2="${pad + Math.round(width * 0.4)}" y2="${accentY}" stroke="url(#accentFade)" stroke-width="3"/>
  ${textLines(tipLines, { x: pad, startY: tipStartY, lineHeight: tipLineHeight, size: tipSize, fill: colors.white, weight: 400 })}
  <text x="${pad}" y="${footerBaseline}" fill="${colors.lime}" font-family="${fontFamilyBold}" font-size="${Math.round(width * 0.026)}" font-weight="700">${escapeXml(brand.handle)}</text>
  <text x="${width - pad}" y="${footerBaseline}" text-anchor="end" fill="${colors.muted}" font-family="${fontFamily}" font-size="${Math.round(width * 0.024)}">${escapeXml(brand.tagline)}</text>
</svg>`;
}
/**
 * OG card: the original generate-social-assets.mjs geometry (1200x630, grid,
 * circular featured image) but the headline and body come from a CSV row.
 */
function buildOgCardSvg({ category, title, tip, featuredImageUri, authorImageUri }) {
  const width = 1200;
  const height = 630;
  const titleSize = 52;
  const titleLineHeight = titleSize + 17;
  const titleLines = wrapToWidth(title, { fontSize: titleSize, maxWidth: 700, maxLines: 3 });
  const bodyLines = wrapToWidth(tip, {
    fontSize: 24,
    maxWidth: 700,
    maxLines: Math.max(2, 6 - titleLines.length),
  });
  const chipY = 96;
  const chipHeight = 46;
  const titleStartY = chipY + chipHeight + 26;
  const bodyStartY = titleStartY + titleLines.length * titleLineHeight + 22;
  const chipWidth = Math.min(700, Math.round(estimateWidth(category, 20) + 44));

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <clipPath id="postImageClip"><circle cx="1023" cy="330" r="165" /></clipPath>
    <clipPath id="authorImageClip"><circle cx="105" cy="528" r="38" /></clipPath>
    <linearGradient id="accentFade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${colors.lime}"/><stop offset="1" stop-color="${colors.lime}" stop-opacity="0"/></linearGradient>
  </defs>
  <rect width="1200" height="630" fill="${colors.background}"/>
  ${gridOverlay(1200, 630, 90)}
  <path d="M963 -22 C1040 102 1150 198 1095 338 C1050 451 1020 532 967 658" fill="none" stroke="${colors.lime}" stroke-width="3"/>
  <path d="M860 153 C930 95 1035 108 1113 162" fill="none" stroke="#4d6847" stroke-width="1" opacity="0.8"/>
  ${brandBadge(66, 38)}
  ${avatarBadge(1123, 69, 27)}
  <rect x="66" y="${chipY}" width="${chipWidth}" height="${chipHeight}" rx="18" fill="none" stroke="${colors.lime}" stroke-width="2"/>
  <text x="${66 + 20}" y="${chipY + 30}" fill="${colors.lime}" font-family="${fontFamily}" font-size="20" font-weight="600">${escapeXml(category)}</text>
  ${textLines(titleLines, { x: 66, startY: titleStartY, lineHeight: titleLineHeight, size: titleSize, fill: colors.white, weight: 700 })}
  <line x1="66" y1="${bodyStartY - 24}" x2="506" y2="${bodyStartY - 24}" stroke="url(#accentFade)" stroke-width="3"/>
  ${textLines(bodyLines, { x: 66, startY: bodyStartY, lineHeight: 34, size: 24, fill: colors.muted, weight: 400 })}
  <circle cx="105" cy="528" r="38" fill="${colors.background}"/>
  <image href="${authorImageUri}" x="67" y="490" width="76" height="76" preserveAspectRatio="xMidYMid slice" clip-path="url(#authorImageClip)"/>
  <circle cx="105" cy="528" r="42" fill="none" stroke="${colors.lime}" stroke-width="3"/>
  <text x="171" y="526" fill="${colors.white}" font-family="${fontFamilyBold}" font-size="30" font-weight="700">${escapeXml(brand.author)}</text>
  <text x="171" y="569" fill="${colors.muted}" font-family="${fontFamily}" font-size="18">${escapeXml(brand.tagline)}</text>
  ${featuredImageUri
    ? `<image href="${featuredImageUri}" x="858" y="165" width="330" height="330" preserveAspectRatio="xMidYMid slice" clip-path="url(#postImageClip)"/>`
    : `<circle cx="1023" cy="330" r="165" fill="#161a1a"/>
  <text x="1023" y="330" text-anchor="middle" dominant-baseline="central" fill="${colors.lime}" font-family="${fontFamilyBold}" font-size="96" font-weight="700">${escapeXml(brand.initials)}</text>`}
  <circle cx="1023" cy="330" r="175" fill="none" stroke="${colors.lime}" stroke-width="3"/>
  <circle cx="1023" cy="330" r="195" fill="none" stroke="#486144" stroke-width="1" opacity="0.85"/>
</svg>`;
}
// ---------------------------------------------------------------------------
// "royal" template — dark navy velvet card with gold accents, a circular
// portrait frame, a gold Bengali heading and numbered steps. Adapted from a
// reference poster design; portrait 1080x1350 by default.
// ---------------------------------------------------------------------------
const royal = {
  bg0: '#04101e',
  bg1: '#0b2740',
  bg2: '#050c17',
  navy: '#0a2036',
  gold: '#e6c877',
  goldBright: '#f8eec6',
  goldDeep: '#a47e2c',
  cyan: '#4fc3e0',
  white: '#f5f8fc',
  muted: '#a9bed3',
};

// Colour themes for the royal layout — each swaps the background, glow, glass
// and banner tints while keeping the gold accents.
const ROYAL_THEMES = {
  navy: { bg0: '#04101e', bg1: '#0b2740', bg2: '#050c17', glow: '#3f9fd0', glass0: '#1c4a6d', glass1: '#08192b', ban0: '#123554', ban1: '#1b4a70' },
  rose: { bg0: '#28040f', bg1: '#5c1130', bg2: '#180309', glow: '#e0559a', glass0: '#5c1a38', glass1: '#1c0510', ban0: '#5a1030', ban1: '#8a1b4a' },
  emerald: { bg0: '#032017', bg1: '#0b3d2e', bg2: '#02140f', glow: '#3fd0a8', glass0: '#155c46', glass1: '#04160f', ban0: '#0b3d2c', ban1: '#12634a' },
  plum: { bg0: '#180428', bg1: '#3d1266', bg2: '#0e0219', glow: '#a05ce0', glass0: '#4a1a75', glass1: '#140421', ban0: '#3d1263', ban1: '#5c1e93' },
};

// Pick the theme for a row; pass a fixed name through unchanged.
//
// "random" is deterministic on purpose - it is derived from the row's text, so
// re-rendering the same CSV always reproduces the same images. With Math.random
// the same tip produced different bytes every run, which made it impossible for
// the uploader to tell "already queued" from "new": it could only re-post the
// same tips or skip genuinely new cards.
function resolveTheme(name, seed = '') {
  if (name === 'random') {
    const keys = Object.keys(ROYAL_THEMES);
    let h = 2166136261; // FNV-1a, so the choice is stable across runs
    for (const ch of String(seed)) {
      h ^= ch.codePointAt(0);
      h = Math.imul(h, 16777619);
    }
    return keys[(h >>> 0) % keys.length];
  }
  return name;
}

function sparklePath(x, y, r, fill, opacity = 0.9) {
  const t = r * 0.22;
  return (
    `<path d="M${x} ${y - r} L${x + t} ${y - t} L${x + r} ${y} L${x + t} ${y + t} ` +
    `L${x} ${y + r} L${x - t} ${y + t} L${x - r} ${y} L${x - t} ${y - t} Z" ` +
    `fill="${fill}" opacity="${opacity}"/>`
  );
}

// Deterministic sparkle field so a given card always looks the same.
function sparkleField(width, height, count, seedStart = 912031) {
  let seed = seedStart;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const out = [];
  for (let i = 0; i < count; i += 1) {
    const x = Math.round(width * (0.03 + rnd() * 0.94));
    const y = Math.round(height * (0.02 + rnd() * 0.96));
    const r = 3 + rnd() * 10;
    const o = (0.2 + rnd() * 0.6).toFixed(2);
    const c = rnd() > 0.45 ? royal.goldBright : '#e2f4fb';
    out.push(sparklePath(x, y, r, c, o));
    if (rnd() > 0.55) {
      out.push(
        `<circle cx="${x + 14}" cy="${y + 9}" r="${(1.5 + rnd() * 2).toFixed(1)}" fill="${c}" opacity="${o}"/>`,
      );
    }
  }
  return out.join('\n  ');
}

// Split a tip into up to `max` numbered points. Prefers sentence breaks, then
// commas, and finally keeps the whole tip as a single point.
function splitPoints(text, max = 3) {
  const clean = String(text || '').trim();
  if (!clean) return [];
  const sentences = clean.split(/(?<=[।.!?])\s+/).map((p) => p.trim()).filter(Boolean);
  if (sentences.length > 1) return sentences.slice(0, max);
  const byComma = clean.split(/\s*[,;]\s*/).map((p) => p.trim()).filter(Boolean);
  if (byComma.length > 1 && byComma.length <= max) return byComma;
  return [clean];
}

function royalStepIcon(kind, cx, cy, r) {
  const stroke = `fill="none" stroke="${royal.goldBright}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"`;
  const f = (n) => Number(n).toFixed(1);
  if (kind === 'drop') {
    return `<path d="M${cx} ${cy - r * 0.52} C ${cx + r * 0.5} ${cy + r * 0.06}, ${cx + r * 0.42} ${cy + r * 0.5}, ${cx} ${cy + r * 0.5} C ${cx - r * 0.42} ${cy + r * 0.5}, ${cx - r * 0.5} ${cy + r * 0.06}, ${cx} ${cy - r * 0.52} Z" ${stroke}/>`;
  }
  if (kind === 'sun') {
    const rays = Array.from({ length: 8 }, (_, i) => {
      const a = (Math.PI / 4) * i;
      return `<path d="M${f(cx + Math.cos(a) * r * 0.5)} ${f(cy + Math.sin(a) * r * 0.5)} L${f(cx + Math.cos(a) * r * 0.72)} ${f(cy + Math.sin(a) * r * 0.72)}" ${stroke}/>`;
    }).join('');
    return `<circle cx="${cx}" cy="${cy}" r="${f(r * 0.34)}" ${stroke}/>${rays}`;
  }
  if (kind === 'leaf') {
    return (
      `<path d="M${cx - r * 0.5} ${cy + r * 0.5} C ${cx - r * 0.5} ${cy - r * 0.42}, ${cx + r * 0.2} ${cy - r * 0.62}, ${cx + r * 0.56} ${cy - r * 0.56} C ${cx + r * 0.5} ${cy + r * 0.1}, ${cx - r * 0.1} ${cy + r * 0.5}, ${cx - r * 0.5} ${cy + r * 0.5} Z" ${stroke}/>` +
      `<path d="M${f(cx - r * 0.42)} ${f(cy + r * 0.42)} L${f(cx + r * 0.42)} ${f(cy - r * 0.42)}" ${stroke}/>`
    );
  }
  // cleanse / bottle
  return (
    `<rect x="${f(cx - r * 0.32)}" y="${f(cy - r * 0.32)}" width="${f(r * 0.64)}" height="${f(r * 0.82)}" rx="${f(r * 0.12)}" ${stroke}/>` +
    `<path d="M${f(cx - r * 0.16)} ${f(cy - r * 0.32)} L${f(cx - r * 0.16)} ${f(cy - r * 0.58)} L${f(cx + r * 0.24)} ${f(cy - r * 0.58)}" ${stroke}/>`
  );
}

function royalShield(x, y, size) {
  const w = size;
  const h = size * 1.18;
  const cx = x + w / 2;
  const outer =
    `M${cx} ${y} L${x + w} ${y + h * 0.26} L${x + w * 0.82} ${y + h * 0.74} ` +
    `Q ${cx} ${y + h * 1.02}, ${x + w * 0.18} ${y + h * 0.74} L${x} ${y + h * 0.26} Z`;
  const inner =
    `M${cx} ${y + h * 0.13} L${x + w * 0.79} ${y + h * 0.34} L${x + w * 0.68} ${y + h * 0.68} ` +
    `Q ${cx} ${y + h * 0.87}, ${x + w * 0.32} ${y + h * 0.68} L${x + w * 0.21} ${y + h * 0.34} Z`;
  // Emblem drawn in a 100x120 space, scaled into the inner shield: a stylised
  // face profile with botanical leaves and a pearl "eye".
  const ms = (w * 0.6) / 100;
  const mx = cx - 50 * ms;
  const my = y + h * 0.16;
  const face =
    'M54 12 C42 14, 34 23, 34 32 C34 37, 30 41, 29 44 C28 47, 31 48, 35 48 ' +
    'C32 51, 35 53, 34 56 C33 58, 37 58, 36 61 C35 64, 37 68, 42 71 C48 75, 54 79, 53 90';
  const leaf = (d) =>
    `<path d="${d}" fill="url(#royalGold)" opacity="0.16" stroke="url(#royalGold)" stroke-width="2.2" stroke-linejoin="round"/>`;
  const leaves = [
    'M56 18 C58 6, 70 2, 78 8 C74 20, 62 24, 56 18 Z',
    'M62 32 C66 22, 78 20, 86 26 C82 38, 68 40, 62 32 Z',
    'M48 26 C44 17, 46 9, 54 5 C58 13, 56 21, 48 26 Z',
    'M58 50 C62 43, 72 43, 78 49 C74 57, 62 57, 58 50 Z',
    'M52 66 C56 61, 66 63, 70 69 C66 77, 54 75, 52 66 Z',
  ]
    .map(leaf)
    .join('');
  return `<g>
    <path d="${outer}" fill="url(#royalGold)" opacity="0.12"/>
    <path d="${outer}" fill="none" stroke="url(#royalGold)" stroke-width="3.5" stroke-linejoin="round"/>
    <path d="${inner}" fill="none" stroke="${royal.gold}" stroke-width="1.1" opacity="0.5"/>
    <g transform="translate(${mx} ${my}) scale(${ms})">
      ${leaves}
      <path d="M46 100 C43 72, 48 40, 60 14" fill="none" stroke="url(#royalGold)" stroke-width="2" opacity="0.7" stroke-linecap="round"/>
      <path d="${face}" fill="none" stroke="url(#royalGold)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="45" cy="42" r="7.5" fill="url(#royalPearl)"/>
    </g>
  </g>`;
}

function centeredLines(lines, { cx, startY, lineHeight, size, fill, weight = 700, family = fontFamilyBold, letterSpacing = 0 }) {
  const ls = letterSpacing ? ` letter-spacing="${letterSpacing}"` : '';
  return lines
    .map(
      (line, i) =>
        `<text x="${cx}" y="${Math.round(startY + i * lineHeight)}" text-anchor="middle" fill="${fill}" font-family="${family}" font-size="${size}" font-weight="${weight}"${ls}>${escapeXml(line)}</text>`,
    )
    .join('\n  ');
}

function buildRoyalCardSvg({ width, height, category, title, tip, imageUri, panelImageUri, heading, banner, logoUri, tipOnly = false, theme = 'navy' }) {
  const th = ROYAL_THEMES[theme] || ROYAL_THEMES.navy;
  const sx = width / 1080;
  const sy = height / 1350;
  const fsc = width / 1080;
  const X = (v) => Math.round(v * sx);
  const Y = (v) => Math.round(v * sy);
  const S = (v) => Math.round(v * fsc);

  const pad = X(60);
  const headingSize = S(50);
  const titleSize = S(56);
  const titleLH = S(72);
  const stepSize = S(32);
  const stepLH = S(42);
  const chipSize = S(23);

  const heroSize = tipOnly ? S(60) : titleSize;
  const heroLines = wrapToWidth(tipOnly ? tip || title : title || heading, {
    fontSize: heroSize,
    maxWidth: tipOnly ? width - pad * 2 : width - X(300),
    maxLines: tipOnly ? 4 : 2,
  });
  const points = tipOnly ? [] : splitPoints(tip, 3);
  const iconKinds = ['bottle', 'drop', 'sun'];
  const numerals = ['১', '২', '৩'];

  // ---- layout anchors (designed on a 1080x1350 grid) ----
  const circleCx = X(828);
  const circleCy = Y(198);
  const circleR = S(114);
  const headingY = Y(392);
  const titleStart = headingY + Y(78);
  const heroLH = S(88);
  const heroCenterY = Y(690);
  const heroStart = Math.round(heroCenterY - ((heroLines.length - 1) * heroLH) / 2 + heroSize * 0.34);
  const miniCy = Y(600);
  const miniR = S(40);
  const bannerY = tipOnly ? Y(946) : Y(668);
  const bannerH = Y(58);
  const panelX = pad;
  const panelY = Y(764);
  const panelW = X(300);
  const panelH = Y(388);
  const stepIconCx = X(426);
  const stepTextX = X(490);
  const stepTextW = width - stepTextX - pad;
  const stepCenter = panelY + panelH / 2;
  const stepSpacing = Y(132);
  const chipCenters = [width * 0.203, width * 0.5, width * 0.797];
  const chipIconCy = Y(1242);
  const chipIconR = S(27);
  const pillY = Y(1266);
  const pillH = Y(46);
  const pillW = X(252);

  const circleFill = imageUri
    ? `<image href="${imageUri}" x="${circleCx - circleR}" y="${circleCy - circleR}" width="${circleR * 2}" height="${circleR * 2}" preserveAspectRatio="xMidYMid slice" clip-path="url(#royalClipCircle)"/>`
    : `<circle cx="${circleCx}" cy="${circleCy}" r="${circleR}" fill="url(#royalGlass)"/>
  <text x="${circleCx}" y="${circleCy}" text-anchor="middle" dominant-baseline="central" fill="url(#royalGold)" font-family="${fontFamilyBold}" font-size="${S(96)}" font-weight="700">${escapeXml(brand.initials)}</text>`;

  const panelFill = panelImageUri
    ? `<image href="${panelImageUri}" x="${panelX}" y="${panelY}" width="${panelW}" height="${panelH}" preserveAspectRatio="xMidYMid slice" clip-path="url(#royalClipPanel)"/>`
    : `<rect x="${panelX}" y="${panelY}" width="${panelW}" height="${panelH}" fill="url(#royalGlass)"/>
  ${sparklePath(panelX + panelW / 2, panelY + panelH / 2, S(34), royal.goldBright, 0.5)}
  <text x="${panelX + panelW / 2}" y="${panelY + panelH * 0.62}" text-anchor="middle" fill="url(#royalGold)" font-family="${fontFamilyBold}" font-size="${S(64)}" font-weight="700">${escapeXml(brand.initials)}</text>`;
  const steps = points
    .map((point, i) => {
      const rowY = Math.round(stepCenter + (i - (points.length - 1) / 2) * stepSpacing);
      const label = `${numerals[i % 3]}. ${point}`;
      const lines = wrapToWidth(label, { fontSize: stepSize, maxWidth: stepTextW, maxLines: 3 });
      const startY = rowY - Math.round(((lines.length - 1) * stepLH) / 2) + Math.round(stepSize * 0.34);
      return `<g>
    <circle cx="${stepIconCx}" cy="${rowY}" r="${S(34)}" fill="url(#royalGlass)" stroke="url(#royalGold)" stroke-width="2.5"/>
    ${royalStepIcon(iconKinds[i % iconKinds.length], stepIconCx, rowY, S(20))}
    ${textLines(lines, { x: stepTextX, startY, lineHeight: stepLH, size: stepSize, fill: royal.white, weight: 600 })}
  </g>`;
    })
    .join('\n  ');

  const phoneGlyph = 'M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z';
  const globeGlyph = 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm6.93 6h-2.95c-.32-1.25-.78-2.45-1.38-3.56 1.85.63 3.37 1.96 4.33 3.56zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56-1.85-.63-3.37-1.96-4.33-3.56zm2.95-8H5.08c.96-1.6 2.48-2.93 4.33-3.56C8.81 5.55 8.35 6.75 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95c-.96 1.6-2.48 2.93-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z';
  const pinGlyph = 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5S10.62 6.5 12 6.5s2.5 1.12 2.5 2.5S13.38 11.5 12 11.5z';
  const chipGlyphs = [phoneGlyph, globeGlyph, pinGlyph];
  const chipLabels = [brand.phone || 'কল করুন', brand.website || 'ওয়েবসাইট', brand.handle || 'ফলো করুন'];
  const glyphScale = (chipIconR * 1.5) / 24;
  const chips = chipCenters
    .map((cx, i) => {
      const k = glyphScale;
      return `<g>
    <circle cx="${Math.round(cx)}" cy="${chipIconCy}" r="${chipIconR}" fill="url(#royalGold)"/>
    <g transform="translate(${Math.round(cx - 12 * k)} ${Math.round(chipIconCy - 12 * k)}) scale(${k.toFixed(3)})">
      <path d="${chipGlyphs[i]}" fill="${royal.ink}"/>
    </g>
    <rect x="${Math.round(cx - pillW / 2)}" y="${pillY}" width="${pillW}" height="${pillH}" rx="${Math.round(pillH / 2)}" fill="#f4f7fb"/>
    <text x="${Math.round(cx)}" y="${pillY + Math.round(pillH * 0.67)}" text-anchor="middle" fill="${royal.ink}" font-family="${fontFamilyBold}" font-size="${chipSize}" font-weight="600">${escapeXml(chipLabels[i])}</text>
  </g>`;
    })
    .join('\n  ');




  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <linearGradient id="royalBase" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="${th.bg0}"/>
      <stop offset="0.45" stop-color="${th.bg1}"/>
      <stop offset="1" stop-color="${th.bg2}"/>
    </linearGradient>
    <linearGradient id="royalGold" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${royal.goldDeep}"/>
      <stop offset="0.35" stop-color="${royal.goldBright}"/>
      <stop offset="0.7" stop-color="${royal.gold}"/>
      <stop offset="1" stop-color="${royal.goldDeep}"/>
    </linearGradient>
    <linearGradient id="royalCyan" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="${royal.cyan}" stop-opacity="0"/>
      <stop offset="0.5" stop-color="${royal.cyan}" stop-opacity="0.9"/>
      <stop offset="1" stop-color="${royal.cyan}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="royalBanner" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="${th.ban0}"/>
      <stop offset="0.5" stop-color="${th.ban1}"/>
      <stop offset="1" stop-color="${th.ban0}"/>
    </linearGradient>
    <radialGradient id="royalGlow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="${th.glow}" stop-opacity="0.55"/>
      <stop offset="1" stop-color="${th.glow}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="royalGlass" cx="0.35" cy="0.3" r="0.8">
      <stop offset="0" stop-color="${th.glass0}"/>
      <stop offset="1" stop-color="${th.glass1}"/>
    </radialGradient>
    <radialGradient id="royalPearl" cx="0.35" cy="0.3" r="0.78">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="0.5" stop-color="#f2f7ff"/>
      <stop offset="1" stop-color="#b9cbe6"/>
    </radialGradient>
    <filter id="royalSoft" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="${S(16)}"/>
    </filter>
    <clipPath id="royalClipCircle"><circle cx="${circleCx}" cy="${circleCy}" r="${circleR}"/></clipPath>
    <clipPath id="royalClipPanel"><rect x="${panelX}" y="${panelY}" width="${panelW}" height="${panelH}" rx="${S(18)}"/></clipPath>
  </defs>

  <rect width="${width}" height="${height}" fill="url(#royalBase)"/>
  <ellipse cx="${X(880)}" cy="${Y(150)}" rx="${X(520)}" ry="${Y(430)}" fill="url(#royalGlow)" opacity="0.55"/>
  <ellipse cx="${X(150)}" cy="${Y(1180)}" rx="${X(470)}" ry="${Y(380)}" fill="url(#royalGlow)" opacity="0.35"/>
  <g opacity="0.8" filter="url(#royalSoft)">
    <path d="M${X(-40)} ${Y(300)} Q ${X(540)} ${Y(110)} ${X(1140)} ${Y(330)}" fill="none" stroke="url(#royalCyan)" stroke-width="${S(26)}" stroke-linecap="round"/>
    <path d="M${X(1140)} ${Y(980)} Q ${X(560)} ${Y(1200)} ${X(-40)} ${Y(940)}" fill="none" stroke="url(#royalCyan)" stroke-width="${S(20)}" stroke-linecap="round"/>
  </g>
  <path d="M${X(-40)} ${Y(300)} Q ${X(540)} ${Y(110)} ${X(1140)} ${Y(330)}" fill="none" stroke="url(#royalGold)" stroke-width="${S(4)}" stroke-linecap="round" opacity="0.7"/>
  <path d="M${X(1140)} ${Y(980)} Q ${X(560)} ${Y(1200)} ${X(-40)} ${Y(940)}" fill="none" stroke="url(#royalGold)" stroke-width="${S(3)}" stroke-linecap="round" opacity="0.6"/>
  ${sparkleField(width, height, 30)}

  ${logoUri
    ? `<image href="${logoUri}" x="${X(48)}" y="${Y(36)}" width="${S(150)}" height="${S(150)}" preserveAspectRatio="xMidYMid meet"/>`
    : royalShield(X(56), Y(44), S(96))}
  <text x="${X(158)}" y="${Y(96)}" fill="url(#royalGold)" font-family="${fontFamilyBold}" font-size="${S(30)}" font-weight="700" letter-spacing="1.5">${escapeXml(brand.name)}</text>
  ${tipOnly
    ? ''
    : `<text x="${X(158)}" y="${Y(128)}" fill="${royal.muted}" font-family="${fontFamily}" font-size="${S(20)}">${escapeXml(category || brand.tagline)}</text>`}

  <circle cx="${circleCx}" cy="${circleCy}" r="${circleR + S(16)}" fill="none" stroke="${royal.cyan}" stroke-width="2" opacity="0.5"/>
  <circle cx="${circleCx}" cy="${circleCy}" r="${circleR + S(8)}" fill="none" stroke="url(#royalGold)" stroke-width="4"/>
  ${circleFill}
  <circle cx="${circleCx}" cy="${circleCy}" r="${circleR}" fill="none" stroke="url(#royalGold)" stroke-width="2" opacity="0.9"/>

  <text x="${X(540)}" y="${headingY}" text-anchor="middle" fill="url(#royalGold)" font-family="${fontFamilyBold}" font-size="${headingSize}" font-weight="700">${escapeXml(heading)}</text>
  ${centeredLines(heroLines, { cx: X(540), startY: tipOnly ? heroStart : titleStart, lineHeight: tipOnly ? heroLH : titleLH, size: heroSize, fill: royal.white, weight: 700 })}

  ${tipOnly
    ? `<g opacity="0.85"><path d="M${X(360)} ${Y(878)} H ${X(508)}" stroke="url(#royalGold)" stroke-width="2"/><path d="M${X(572)} ${Y(878)} H ${X(720)}" stroke="url(#royalGold)" stroke-width="2"/><path d="M${X(540)} ${Y(868)} L${X(550)} ${Y(878)} L${X(540)} ${Y(888)} L${X(530)} ${Y(878)} Z" fill="url(#royalGold)"/></g>`
    : ''}

  ${tipOnly
    ? ''
    : [X(396), X(540), X(684)]
        .map(
          (cx) =>
            `<circle cx="${cx}" cy="${miniCy}" r="${miniR}" fill="url(#royalGlass)" stroke="url(#royalGold)" stroke-width="2.5"/>`,
        )
        .join('\n  ')}

  <rect x="${pad}" y="${bannerY}" width="${width - pad * 2}" height="${bannerH}" rx="${S(12)}" fill="url(#royalBanner)" stroke="url(#royalGold)" stroke-width="1.5"/>
  <text x="${X(540)}" y="${bannerY + Math.round(bannerH * 0.66)}" text-anchor="middle" fill="${royal.white}" font-family="${fontFamily}" font-size="${S(30)}" font-weight="600">${escapeXml(banner)}</text>

  ${tipOnly
    ? ''
    : `<rect x="${panelX}" y="${panelY}" width="${panelW}" height="${panelH}" rx="${S(18)}" fill="none" stroke="url(#royalGold)" stroke-width="2.5"/>
  ${panelFill}
  <rect x="${panelX}" y="${panelY}" width="${panelW}" height="${panelH}" rx="${S(18)}" fill="none" stroke="url(#royalGold)" stroke-width="2.5"/>
  ${steps}`}

  ${chips}
</svg>`;
}


// ---------------------------------------------------------------------------
// Rendering pipeline
// ---------------------------------------------------------------------------
const DEFAULTS = {
  csv: path.join(scriptDir, 'examples', 'beauty_tips.csv'),
  outDir: path.join(repoRoot, 'cards'),
  template: 'photo',
  size: null,
  photo: null,
  photoDir: null,
  limit: null,
  filter: null,
  captions: false,
  tipOnly: false,
  heading: 'আজকের বিশেষ টিপ',
  banner: 'সৌন্দর্যের গোপন টিপস পেতে আমাদের সাথে থাকুন',
  logo: null,
  theme: 'navy',
  help: false,
};

const USAGE = `
Generate social-media photo cards from a CSV of tips.

Usage: node scripts/generate-tip-cards.mjs [options]

Options:
  --csv <file>        CSV with category,title,tip columns
                      (default: scripts/examples/beauty_tips.csv)
  --out-dir <dir>     where PNGs are written (default: public/social-cards)
  --template <name>   photo (default) | og | royal
  --size <WxH>        card size (1080x1080 photo, 1200x630 og, 1080x1350 royal)
  --photo <file>      background/featured photo
  --photo-dir <dir>   rotate through every image in a folder
  --heading <text>    royal template: gold heading (default: আজকের বিশেষ টিপ)
  --banner <text>     royal template: banner line
  --logo <file>       royal template: use an image logo instead of the shield
  --theme <name>      royal template: navy (default) | rose | emerald | plum | random
  --website <text>    website shown in the footer chip (default: www.trueface.bond)
  --phone <text>      phone shown in the footer chip (default: 01933211642)
  --limit <n>         only the first n rows
  --filter <text>     keep rows whose category/title/tip contains text
  --captions          also write captions.txt next to the PNGs
  --tip-only          royal template: use only the tip (ignore the title/category)
  --brand <text>      brand pill text (default: Face By Sumona)
  --initials <text>   monogram in the corner badge (default: FS)
  --handle <text>     footer handle (default: @facebysumona)
  --author <text>     author name on the og template (default: Face By Sumona)
  --tagline <text>    footer tagline
  --help              show this message
`;

function parseArgs(argv) {
  const args = { ...DEFAULTS };
  const takesValue = new Set([
    'csv', 'out-dir', 'template', 'size', 'photo', 'photo-dir', 'limit', 'filter',
    'brand', 'initials', 'handle', 'author', 'tagline', 'heading', 'banner', 'logo',
    'website', 'phone', 'theme',
  ]);
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    if (key === 'help') args.help = true;
    else if (key === 'captions') args.captions = true;
    else if (key === 'tip-only') args.tipOnly = true;
    else if (takesValue.has(key)) {
      const value = argv[i + 1];
      if (value === undefined || value.startsWith('--')) throw new Error(`missing value for --${key}`);
      i += 1;
      const camel = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      args[camel] = key === 'limit' ? Number.parseInt(value, 10) : value;
    } else throw new Error(`unknown option --${key}`);
  }
  if (!['photo', 'og', 'royal'].includes(args.template)) throw new Error(`unknown template: ${args.template}`);
  return args;
}

async function firstExisting(...candidates) {
  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      await fs.access(candidate);
      return candidate;
    } catch {
      /* keep looking */
    }
  }
  return null;
}

const rasterExtensions = new Set(['.png', '.jpg', '.jpeg', '.webp', '.avif']);

async function collectPhotos({ photo, photoDir }) {
  const photos = [];
  if (photo) photos.push(path.resolve(photo));
  if (photoDir) {
    const entries = await fs.readdir(path.resolve(photoDir));
    for (const entry of entries.sort()) {
      if (rasterExtensions.has(path.extname(entry).toLowerCase())) {
        photos.push(path.join(path.resolve(photoDir), entry));
      }
    }
  }
  return photos;
}

function parseSize(value, fallback) {
  if (!value) return fallback;
  const match = String(value).match(/^(\d+)\s*[x×]\s*(\d+)$/i);
  if (!match) throw new Error(`invalid --size: ${value} (expected e.g. 1080x1080)`);
  return { width: Number.parseInt(match[1], 10), height: Number.parseInt(match[2], 10) };
}
function buildCaption(row) {
  const hashtags = ['#beauty', '#skincare', '#selfcare', '#beautytips', '#বাংলা'];
  return [row.title, row.tip, '', hashtags.join(' ')].filter((line) => line !== undefined).join('\n');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(USAGE.trim());
    return 0;
  }

  const brandOverrides = {
    brand: 'name',
    initials: 'initials',
    handle: 'handle',
    author: 'author',
    tagline: 'tagline',
    website: 'website',
    phone: 'phone',
  };
  for (const [flag, property] of Object.entries(brandOverrides)) {
    if (args[flag]) brand[property] = args[flag];
  }

  const csvPath = path.resolve(args.csv);
  let rows = await readTips(csvPath);
  if (args.filter) {
    const needle = args.filter.toLowerCase();
    rows = rows.filter((row) =>
      [row.category, row.title, row.tip].join(' ').toLowerCase().includes(needle),
    );
  }
  if (args.limit) rows = rows.slice(0, args.limit);
  if (!rows.length) {
    console.error(`error: no rows found in ${csvPath}`);
    return 1;
  }

  const isOg = args.template === 'og';
  const isRoyal = args.template === 'royal';
  const defaultSize = isOg
    ? { width: 1200, height: 630 }
    : isRoyal
      ? { width: 1080, height: 1350 }
      : { width: 1080, height: 1080 };
  const { width, height } = parseSize(args.size, defaultSize);

  const photos = await collectPhotos(args);
  const outDir = path.resolve(args.outDir);
  await fs.mkdir(outDir, { recursive: true });

  let authorImageUri = '';
  const authorPath = await firstExisting(
    path.join(repoRoot, 'assets', 'portrait.webp'),
    path.join(repoRoot, 'public', 'portrait.webp'),
  );
  if (authorPath) {
    const buffer = await sharp(authorPath).resize(76, 76, { fit: 'cover' }).png().toBuffer();
    authorImageUri = imageDataUri(buffer);
  }

  let logoUri = '';
  if (args.logo) {
    logoUri = imageDataUri(
      await sharp(path.resolve(args.logo), { failOn: 'none' })
        .resize({ height: 300, fit: 'inside' })
        .png()
        .toBuffer(),
    );
  }

  const written = [];
  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i];
    const photo = photos.length ? photos[i % photos.length] : null;
    const headline = row.title || row.tip;
    const body = row.title ? row.tip : '';
    let svg;

    if (isOg) {
      // No photo supplied? The template falls back to a brand monogram.
      const featuredPath = photo;
      const featuredUri = featuredPath
        ? imageDataUri(
            await sharp(featuredPath, { failOn: 'none' })
              .resize(330, 330, { fit: 'cover', position: 'attention' })
              .png()
              .toBuffer(),
          )
        : '';
      svg = buildOgCardSvg({
        category: row.category || 'Beauty tips',
        title: headline,
        tip: body,
        featuredImageUri: featuredUri,
        authorImageUri,
      });
    } else if (isRoyal) {
      const circlePx = Math.round(width * 0.46);
      const panelPxW = Math.round(width * 0.3);
      const panelPxH = Math.round(height * 0.29);
      const imageUri = photo
        ? imageDataUri(
            await sharp(photo, { failOn: 'none' })
              .resize(circlePx, circlePx, { fit: 'cover', position: 'attention' })
              .png()
              .toBuffer(),
          )
        : '';
      const panelImageUri = photo
        ? imageDataUri(
            await sharp(photo, { failOn: 'none' })
              .resize(panelPxW, panelPxH, { fit: 'cover', position: 'attention' })
              .png()
              .toBuffer(),
          )
        : '';
      // Everything the royal card actually draws, so the theme only varies when
      // the visible content does.
      const themeSeed = [
        args.tipOnly ? '' : row.category,
        args.tipOnly ? '' : headline,
        body || row.tip,
      ].join('|');
      svg = buildRoyalCardSvg({
        width,
        height,
        category: args.tipOnly ? '' : row.category,
        title: args.tipOnly ? '' : headline,
        tip: body || row.tip,
        imageUri,
        panelImageUri,
        heading: args.heading,
        banner: args.banner,
        logoUri,
        tipOnly: args.tipOnly,
        theme: resolveTheme(args.theme, themeSeed),
      });
    } else {
      const backgroundUri = photo
        ? imageDataUri(
            await sharp(photo, { failOn: 'none' })
              .resize(width, height, { fit: 'cover', position: 'attention' })
              .png()
              .toBuffer(),
          )
        : null;
      svg = buildPhotoCardSvg({
        width,
        height,
        category: row.category,
        title: headline,
        tip: body,
        backgroundUri,
      });
    }

    // The name is content-addressed: a digest of the SVG that was drawn. The
    // old `${index}-${category}` name was recycled by every batch, so the same
    // filename meant different cards over time and the uploader could not tell
    // "already queued" from "new" - it either re-posted cards or skipped fresh
    // ones. Note the row index is deliberately NOT part of the name: if rows
    // shift (a new tip is scraped) an index would rename unchanged cards and
    // they would be queued a second time.
    const digest = crypto.createHash('sha256').update(svg).digest('hex').slice(0, 12);
    const name = `${digest}-${asciiSlug(row.category, headline)}.png`;
    const file = path.join(outDir, name);
    await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toFile(file);
    written.push({ file, row });
  }

  if (args.captions) {
    const captionsPath = path.join(outDir, 'captions.txt');
    const text = written
      .map(({ file, row }, i) => `--- ${i + 1}. ${path.basename(file)} ---\n${buildCaption(row)}\n`)
      .join('\n');
    await fs.writeFile(captionsPath, text, 'utf8');
  }

  console.log(`font source: ${fontInfo.source}`);
  console.log(
    `Generated ${written.length} card(s) in ${path.relative(repoRoot, outDir) || outDir} ` +
      `(${width}x${height}, ${args.template} template).`,
  );
  return 0;
}

try {
  process.exitCode = await main();
} catch (error) {
  console.error(`error: ${error.message}`);
  process.exitCode = 1;
}
