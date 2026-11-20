// Draws the show tiles: the square artwork a show gets when no real cover
// exists (the listening hero, the now-playing bar, the lock screen). Each is
// a close crop of a tie-dye burst on the page's dark green ground: colour and
// pattern only, in the family of the page's rosettes. One palette per era of
// the band, and a few compositions per palette, so two shows on one page
// seldom match (src/cards/show-tile.ts picks one from the show's date).
//
// The tiles are committed; run this only to change them:
//
//   node web/scripts/make-show-tiles.mjs <empty folder>
//   for f in <folder>/*.png; do sips -s format jpeg -s formatOptions 72 "$f" --out web/public/icons/tiles/$(basename "${f%.png}").jpg; done
//
// It writes PNGs with nothing but Node; the JPEG step (macOS `sips`, or any
// converter) keeps the files small. They live under /icons so the server and
// the service worker already serve and keep them.
import { deflateSync } from "node:zlib";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const SIZE = 512;
const GROUND = [20, 34, 27]; // --forest-900
const GROUND_LIT = [34, 58, 44];

// Three dyes per era, from the site's own colours and their near neighbours.
export const ERA_PALETTES = [
  ["#e8779a", "#e7b94e", "#8b5cf6"], // to 1967
  ["#8b5cf6", "#3f95dc", "#e8779a"], // 1968-70
  ["#e7b94e", "#e08a3c", "#e8779a"], // 1971-72
  ["#2f9aa6", "#3f95dc", "#e9d9a0"], // 1973-74
  ["#e8779a", "#8b5cf6", "#2f9aa6"], // 1975-79
  ["#3f95dc", "#2f9aa6", "#e7b94e"], // 1980-86
  ["#e08a3c", "#e8779a", "#3f95dc"]  // 1987-95
];

// Where the burst's centre sits (in tile widths; outside the square, so the
// tile shows rays crossing it and never a bullseye), and how far it reaches.
export const COMPOSITIONS = [
  { cx: -0.18, cy: -0.12, reach: 1.75, spin: 0.0 },
  { cx: 1.2, cy: -0.1, reach: 1.85, spin: 1.3 },
  { cx: -0.1, cy: 1.18, reach: 1.8, spin: 2.1 },
  { cx: 1.15, cy: 1.2, reach: 1.9, spin: 3.4 }
];

const hex = (value) => [1, 3, 5].map((at) => parseInt(value.slice(at, at + 2), 16));
const mix = (a, b, t) => a.map((channel, index) => channel + (b[index] - channel) * t);
const smooth = (edge0, edge1, x) => {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
};

// Repeatable noise: a hash on the lattice, smoothed between points.
function lattice(x, y, seed) {
  const n = Math.sin(x * 127.1 + y * 311.7 + seed * 74.7) * 43758.5453;
  return n - Math.floor(n);
}
function noise(x, y, seed) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const top = lattice(xi, yi, seed) * (1 - u) + lattice(xi + 1, yi, seed) * u;
  const bottom = lattice(xi, yi + 1, seed) * (1 - u) + lattice(xi + 1, yi + 1, seed) * u;
  return top * (1 - v) + bottom * v;
}

function tile(palette, composition, seed) {
  const dyes = palette.map(hex);
  const pixels = Buffer.alloc(SIZE * SIZE * 3);
  for (let py = 0; py < SIZE; py += 1) {
    for (let px = 0; px < SIZE; px += 1) {
      const x = px / SIZE, y = py / SIZE;
      const dx = x - composition.cx, dy = y - composition.cy;
      const angle = Math.atan2(dy, dx) + composition.spin;
      const soft = noise(x * 3, y * 3, seed) - 0.5;
      const distance = Math.hypot(dx, dy) / composition.reach + soft * 0.08;
      // The pleats: rays of uneven width, as folded cloth takes dye.
      const pleat = 0.5 + 0.28 * Math.sin(angle * 31 + seed) + 0.16 * Math.sin(angle * 59 + seed * 2.3 + soft * 3) + 0.06 * Math.sin(angle * 113 + seed * 0.7);
      // The dyes follow one another outward from the centre, pulled along the rays.
      const band = (distance * 3.1 + pleat * 0.3 + seed * 0.37) % 1;
      const at = band * dyes.length;
      const from = dyes[Math.floor(at) % dyes.length], to = dyes[(Math.floor(at) + 1) % dyes.length];
      const dye = mix(from, to, smooth(0.25, 0.75, at - Math.floor(at)));
      // The burst fades into the ground toward its tips; the rays reach unevenly.
      const tip = 0.66 + 0.34 * pleat;
      const strength = (1 - smooth(tip * 0.55, tip, distance)) * (0.5 + 0.5 * smooth(0.2, 0.75, pleat)) * 0.8;
      const ground = mix(GROUND, GROUND_LIT, smooth(0.9, 0.1, distance));
      const speckle = (noise(x * 90, y * 90, seed + 9) - 0.5) * 8;
      const colour = mix(ground, dye, strength);
      const offset = (py * SIZE + px) * 3;
      for (let channel = 0; channel < 3; channel += 1) {
        pixels[offset + channel] = Math.max(0, Math.min(255, Math.round(colour[channel] + speckle * (0.35 + strength))));
      }
    }
  }
  return pixels;
}

// A minimal PNG: 8-bit RGB, one zlib stream.
const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc(buffer) {
  let c = 0xffffffff;
  for (const byte of buffer) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(data.length, 0);
  head.write(type, 4, "ascii");
  const tail = Buffer.alloc(4);
  tail.writeUInt32BE(crc(Buffer.concat([head.subarray(4), data])), 0);
  return Buffer.concat([head, data, tail]);
}
function png(pixels) {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(SIZE, 0);
  header.writeUInt32BE(SIZE, 4);
  header.set([8, 2, 0, 0, 0], 8);
  const rows = Buffer.alloc((SIZE * 3 + 1) * SIZE);
  for (let y = 0; y < SIZE; y += 1) pixels.copy(rows, y * (SIZE * 3 + 1) + 1, y * SIZE * 3, (y + 1) * SIZE * 3);
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", header), chunk("IDAT", deflateSync(rows, { level: 9 })), chunk("IEND", Buffer.alloc(0))]);
}

const out = process.argv[2];
if (!out) {
  console.error("Usage: node web/scripts/make-show-tiles.mjs <output folder>");
  process.exit(1);
}
mkdirSync(out, { recursive: true });
ERA_PALETTES.forEach((palette, era) => {
  COMPOSITIONS.forEach((composition, variant) => {
    writeFileSync(join(out, `e${era}v${variant}.png`), png(tile(palette, composition, 1 + era * 4 + variant)));
  });
});
console.log(`Wrote ${ERA_PALETTES.length * COMPOSITIONS.length} tiles to ${out}`);
