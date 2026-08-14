/**
 * Regenerates LandSignal home-screen / PWA icons from the Fraunces "L"
 * glyph — the same letter used in the site wordmark (font-semibold / 600).
 *
 * Usage (from apps/web):
 *   node scripts/generate-app-icons.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const sharp = require("sharp");
const opentype = require("opentype.js");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const outDir = path.join(root, "public");
const iconsDir = path.join(outDir, "icons");
const brandDir = path.join(outDir, "brand");

const BRAND = "#0f3d2e";
const BG = "#f6f3ee";

const FONT_URL =
  "https://fonts.gstatic.com/s/fraunces/v38/6NUh8FyLNQOQZAnv9bYEvDiIdE9Ea92uemAk_WBq8U_9v0c2Wa0K7iN7hzFUPJH58njr1a03gg7S2nfgRYIcaRyjDg.ttf";

function round(n) {
  return Math.round(n * 100) / 100;
}

function createIco(images) {
  const headerSize = 6 + 16 * images.length;
  let offset = headerSize;
  const headers = images.map((img) => {
    const h = {
      width: img.size >= 256 ? 0 : img.size,
      height: img.size >= 256 ? 0 : img.size,
      size: img.data.length,
      offset,
    };
    offset += img.data.length;
    return h;
  });
  const buf = Buffer.alloc(offset);
  buf.writeUInt16LE(0, 0);
  buf.writeUInt16LE(1, 2);
  buf.writeUInt16LE(images.length, 4);
  let hOff = 6;
  for (const h of headers) {
    buf.writeUInt8(h.width, hOff++);
    buf.writeUInt8(h.height, hOff++);
    buf.writeUInt8(0, hOff++);
    buf.writeUInt8(0, hOff++);
    buf.writeUInt16LE(1, hOff);
    hOff += 2;
    buf.writeUInt16LE(32, hOff);
    hOff += 2;
    buf.writeUInt32LE(h.size, hOff);
    hOff += 4;
    buf.writeUInt32LE(h.offset, hOff);
    hOff += 4;
  }
  images.forEach((img, i) => img.data.copy(buf, headers[i].offset));
  return buf;
}

async function main() {
  let opentypeMod;
  try {
    opentypeMod = opentype;
  } catch {
    console.error("Install opentype.js in apps/web (or run via npx) to regenerate.");
    process.exit(1);
  }

  const fontRes = await fetch(FONT_URL);
  if (!fontRes.ok) throw new Error(`Font download failed: ${fontRes.status}`);
  const fontBuf = Buffer.from(await fontRes.arrayBuffer());
  const font = opentypeMod.parse(fontBuf.buffer.slice(fontBuf.byteOffset, fontBuf.byteOffset + fontBuf.byteLength));
  const glyph = font.charToGlyph("L");
  const upm = font.unitsPerEm;
  const pathObj = glyph.getPath(0, 0, upm);

  let d = "";
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const c of pathObj.commands) {
    if (c.type === "M") d += `M${round(c.x)} ${round(c.y)}`;
    else if (c.type === "L") d += `L${round(c.x)} ${round(c.y)}`;
    else if (c.type === "C")
      d += `C${round(c.x1)} ${round(c.y1)} ${round(c.x2)} ${round(c.y2)} ${round(c.x)} ${round(c.y)}`;
    else if (c.type === "Q") d += `Q${round(c.x1)} ${round(c.y1)} ${round(c.x)} ${round(c.y)}`;
    else if (c.type === "Z") d += "Z";
    for (const key of ["x", "y", "x1", "y1", "x2", "y2"]) {
      if (c[key] == null) continue;
      if (key.startsWith("x")) {
        minX = Math.min(minX, c[key]);
        maxX = Math.max(maxX, c[key]);
      } else {
        minY = Math.min(minY, c[key]);
        maxY = Math.max(maxY, c[key]);
      }
    }
  }

  const gw = maxX - minX;
  const gh = maxY - minY;

  function makeSvg({ size, padRatio }) {
    const inner = size * (1 - 2 * padRatio);
    const scale = Math.min(inner / gw, inner / gh);
    const drawW = gw * scale;
    const drawH = gh * scale;
    const ox = (size - drawW) / 2 - minX * scale;
    const oy = (size - drawH) / 2 - minY * scale - size * 0.012;
    return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="LandSignal">
  <rect width="${size}" height="${size}" fill="${BG}"/>
  <path transform="translate(${ox.toFixed(4)} ${oy.toFixed(4)}) scale(${scale.toFixed(10)})" d="${d}" fill="${BRAND}"/>
</svg>`;
  }

  const canonicalSvg = makeSvg({ size: 512, padRatio: 0.17 });
  fs.mkdirSync(iconsDir, { recursive: true });
  fs.mkdirSync(brandDir, { recursive: true });
  fs.writeFileSync(path.join(brandDir, "l-mark.svg"), canonicalSvg);
  fs.writeFileSync(path.join(iconsDir, "icon.svg"), canonicalSvg);

  async function masterBuffer(padRatio) {
    const svg = makeSvg({ size: 4096, padRatio });
    return sharp(Buffer.from(svg), { density: 72 }).ensureAlpha().png().toBuffer();
  }

  async function writeSized(master, size, file) {
    await sharp(master)
      .resize(size, size, { kernel: sharp.kernel.lanczos3, fit: "fill" })
      .png({ compressionLevel: 6, adaptiveFiltering: true, force: true })
      .toFile(file);
    console.log(path.relative(root, file), size, fs.statSync(file).size);
  }

  const anyMaster = await masterBuffer(0.17);
  const maskMaster = await masterBuffer(0.22);

  await writeSized(anyMaster, 1024, path.join(iconsDir, "icon-1024.png"));
  await writeSized(anyMaster, 512, path.join(iconsDir, "icon-512.png"));
  await writeSized(anyMaster, 192, path.join(iconsDir, "icon-192.png"));
  await writeSized(anyMaster, 180, path.join(iconsDir, "apple-touch-icon.png"));
  await writeSized(anyMaster, 180, path.join(outDir, "apple-touch-icon.png"));
  await writeSized(anyMaster, 32, path.join(iconsDir, "icon-32.png"));
  await writeSized(anyMaster, 16, path.join(iconsDir, "icon-16.png"));
  await writeSized(anyMaster, 512, path.join(brandDir, "l-mark.png"));
  await writeSized(maskMaster, 512, path.join(iconsDir, "icon-maskable-512.png"));
  await writeSized(maskMaster, 192, path.join(iconsDir, "icon-maskable-192.png"));

  const png16 = await sharp(anyMaster).resize(16, 16, { kernel: "lanczos3" }).png().toBuffer();
  const png32 = await sharp(anyMaster).resize(32, 32, { kernel: "lanczos3" }).png().toBuffer();
  const png48 = await sharp(anyMaster).resize(48, 48, { kernel: "lanczos3" }).png().toBuffer();
  fs.writeFileSync(
    path.join(outDir, "favicon.ico"),
    createIco([
      { size: 16, data: png16 },
      { size: 32, data: png32 },
      { size: 48, data: png48 },
    ]),
  );
  console.log("done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
