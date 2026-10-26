#!/usr/bin/env node
/**
 * export-instagram.mjs — turn queued cards into an Instagram upload pack.
 *
 * Instagram's Content Publishing API has no "schedule for later" field, so the
 * no-code route is to upload these files in Meta Business Suite Planner (or a
 * third-party scheduler) and select the Facebook Page + Instagram account
 * together.
 *
 * Instagram wants JPEG (not PNG), so every card is converted and the caption
 * and scheduled time come from data/.photo-schedule-manifest.json.
 *
 * Usage
 *   npm run instagram:export -- --cards cards-daily
 *   npm run instagram:export -- --cards cards-daily --future-only
 *   node scripts/export-instagram.mjs --cards cards-daily --dry-run
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const sharp = (await import('sharp')).default;

const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp']);
const DHAKA_OFFSET_MS = 6 * 60 * 60 * 1000;
const DEFAULT_CAPTION = 'Face By Sumona ✨\n#beauty #skincare #facebysumona';

const DEFAULTS = {
  cards: 'cards-daily',
  manifest: path.join('data', '.photo-schedule-manifest.json'),
  out: 'instagram-export',
  limit: 0,
  quality: 90,
  futureOnly: false,
  dryRun: false,
  help: false,
};

const USAGE = `
export-instagram.mjs — build an Instagram-ready folder from queued cards

Options:
  --cards <dir>       folder of rendered cards (default: cards-daily)
  --manifest <file>   queue manifest (default: data/.photo-schedule-manifest.json)
  --out <dir>         output folder (default: instagram-export)
  --future-only       only cards whose scheduled time is still in the future
  --limit <n>         cap the number of cards (0 = all)
  --quality <n>       JPEG quality, 1-100 (default: 90)
  --dry-run           print the plan, write nothing
  --help              show this message
`;

function parseArgs(argv) {
  const args = { ...DEFAULTS };
  const takesValue = new Set(['cards', 'manifest', 'out', 'limit', 'quality']);

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) throw new Error(`unexpected argument: ${token}`);
    const key = token.slice(2);

    if (key === 'help') args.help = true;
    else if (key === 'future-only') args.futureOnly = true;
    else if (key === 'dry-run') args.dryRun = true;
    else if (takesValue.has(key)) {
      const value = argv[i + 1];
      if (value === undefined || value.startsWith('--')) {
        throw new Error(`missing value for --${key}`);
      }
      i += 1;
      const camel = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      args[camel] = key === 'limit' || key === 'quality'
        ? Number.parseInt(value, 10)
        : value;
    } else {
      throw new Error(`unknown option --${key}`);
    }
  }

  if (!Number.isFinite(args.limit) || args.limit < 0) {
    throw new Error('--limit must be a non-negative integer');
  }
  if (!Number.isFinite(args.quality) || args.quality < 1 || args.quality > 100) {
    throw new Error('--quality must be between 1 and 100');
  }
  return args;
}

async function readManifest(file) {
  try {
    return JSON.parse(await fs.readFile(file, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT') return {};
    throw error;
  }
}

function scheduledTime(entry) {
  const stamp = entry && typeof entry === 'object'
    ? entry.scheduled_publish_time_utc
    : null;
  if (!stamp) return null;
  const when = new Date(stamp);
  return Number.isNaN(when.getTime()) ? null : when;
}

function stampFor(when) {
  const pad = (value) => String(value).padStart(2, '0');
  return [
    when.getUTCFullYear(),
    pad(when.getUTCMonth() + 1),
    pad(when.getUTCDate()),
  ].join('') + '-' + pad(when.getUTCHours()) + pad(when.getUTCMinutes());
}

function dhakaLabel(when) {
  const local = new Date(when.getTime() + DHAKA_OFFSET_MS);
  const pad = (value) => String(value).padStart(2, '0');
  return `${local.getUTCFullYear()}-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())} `
    + `${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}`;
}

function csvCell(value) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

function buildPack(cards, manifest, { futureOnly, limit }) {
  const now = new Date();
  const items = [];

  for (const name of cards) {
    const entry = manifest[name];
    const when = scheduledTime(entry);

    // With no manifest entry we cannot know the slot; keep it only when the
    // caller asked for every card (future-only makes no sense without a time).
    if (futureOnly && (!when || when <= now)) continue;

    items.push({
      name,
      when,
      whenIso: when ? when.toISOString().replace('.000Z', 'Z') : '',
      caption: (entry && entry.message) || DEFAULT_CAPTION,
    });
  }

  items.sort((a, b) => {
    const left = a.when ? a.when.getTime() : Number.POSITIVE_INFINITY;
    const right = b.when ? b.when.getTime() : Number.POSITIVE_INFINITY;
    return left - right || a.name.localeCompare(b.name);
  });

  return limit > 0 ? items.slice(0, limit) : items;
}

function outputName(item) {
  const stem = path.parse(item.name).name;
  return item.when ? `${stampFor(item.when)}-${stem}.jpg` : `${stem}.jpg`;
}

function readmeText(items) {
  return [
    'Instagram upload pack',
    '=====================',
    '',
    'Meta Business Suite has no bulk API here, but this folder is ready for',
    'Planner (or any third-party scheduler):',
    '',
    '1. Open Meta Business Suite -> Planner -> Create post.',
    '2. Select the Facebook Page and the linked Instagram account.',
    '3. Upload the matching .jpg and paste its caption from captions.csv',
    '   (captions.txt is the same content in copy/paste blocks).',
    '4. Schedule it for the time shown: scheduled_utc is UTC, dhaka is local.',
    '',
    'Facebook keeps publishing through the existing queue; this pack is only',
    'the Instagram side. Instagram does not appear in the queue manifest.',
    '',
    `Cards in this pack: ${items.length}`,
    '',
  ].join('\n');
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(`error: ${error.message}`);
    console.error(USAGE);
    return 1;
  }

  if (args.help) {
    console.log(USAGE.trim());
    return 0;
  }

  const cardsDir = path.resolve(args.cards);
  let entries;
  try {
    entries = await fs.readdir(cardsDir);
  } catch (error) {
    console.error(`error: cannot read cards folder ${cardsDir}: ${error.message}`);
    return 1;
  }

  const cards = entries
    .filter((name) => IMAGE_EXTENSIONS.has(path.extname(name).toLowerCase()))
    .sort();

  if (!cards.length) {
    console.error(`error: no images in ${cardsDir}`);
    return 1;
  }

  const manifest = await readManifest(path.resolve(args.manifest));
  const items = buildPack(cards, manifest, args);
  if (!items.length) {
    console.error('error: nothing to export (no future cards in the manifest)');
    return 1;
  }

  console.log(`${'#'.padStart(2)}  ${'Scheduled (UTC)'.padEnd(22)}  File -> Instagram JPEG`);
  console.log('-'.repeat(86));
  for (const [index, item] of items.entries()) {
    const when = item.whenIso || '(no schedule)';
    console.log(`${String(index + 1).padStart(2)}  ${when.padEnd(22)}  ${item.name} -> ${outputName(item)}`);
  }

  if (args.dryRun) {
    console.log(`\nDRY RUN: ${items.length} card(s) would go to ${path.resolve(args.out)}`);
    return 0;
  }

  const outDir = path.resolve(args.out);
  await fs.mkdir(outDir, { recursive: true });

  const rows = [['scheduled_utc', 'dhaka', 'image', 'caption']];
  const blocks = [];

  for (const item of items) {
    const imageName = outputName(item);
    const destination = path.join(outDir, imageName);
    await sharp(path.join(cardsDir, item.name))
      .rotate()
      .flatten({ background: '#ffffff' })
      .resize({ width: 1440, withoutEnlargement: true })
      .jpeg({ quality: args.quality, mozjpeg: true })
      .toFile(destination);

    const dhaka = item.when ? dhakaLabel(item.when) : '';
    rows.push([item.whenIso, dhaka, imageName, item.caption]);
    blocks.push(`--- ${item.whenIso || 'no schedule'} | ${imageName} ---\n${item.caption}`);
  }

  const csv = rows.map((row) => row.map(csvCell).join(',')).join('\n') + '\n';
  await fs.writeFile(path.join(outDir, 'captions.csv'), `\uFEFF${csv}`, 'utf8');
  await fs.writeFile(path.join(outDir, 'captions.txt'), blocks.join('\n\n') + '\n', 'utf8');
  await fs.writeFile(path.join(outDir, 'README.txt'), readmeText(items), 'utf8');

  console.log(`\nExported ${items.length} card(s) to ${outDir}`);
  console.log(`Captions: ${path.join(outDir, 'captions.csv')}`);
  console.log('Next: Business Suite -> Planner -> select Facebook + Instagram,');
  console.log('upload the JPEG and paste its caption. See README.txt in the pack.');
  return 0;
}

process.exitCode = await main();


