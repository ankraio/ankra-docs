// Serves the static `mint export` of these docs inside the container image.
//
// Node built-ins only, so the runtime image carries no npm dependency tree for
// the image gate to scan. Text assets are gzipped at build time and stored only
// as `<file>.gz`; they are sent as-is to clients that accept gzip and inflated
// on the fly for the rest.
import { createReadStream, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, resolve, sep } from 'node:path';
import { createGunzip } from 'node:zlib';

const ROOT = resolve(process.env.SITE_DIR || '/app/site');
const PORT = Number(process.env.PORT || 3000);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.webmanifest': 'application/manifest+json',
};

function isFile(path) {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

// Maps a URL path to { path, gzipped, type }: the file itself, its index.html,
// or `<path>.html`, each either plain or as the build's `.gz` copy. Only the
// extensions in TYPES are served, so nothing but web assets ever leaves.
function lookup(urlPath) {
  const base = resolve(ROOT, `.${urlPath}`);
  if (base !== ROOT && !base.startsWith(ROOT + sep)) return undefined;
  for (const candidate of [base, join(base, 'index.html'), `${base}.html`]) {
    const type = TYPES[extname(candidate).toLowerCase()];
    if (!type) continue;
    if (isFile(candidate)) return { path: candidate, gzipped: false, type };
    if (isFile(`${candidate}.gz`)) return { path: `${candidate}.gz`, gzipped: true, type };
  }
  return undefined;
}

const server = createServer((req, res) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' }).end();
    return;
  }

  let file;
  try {
    file = lookup(decodeURIComponent(new URL(req.url, 'http://docs').pathname));
  } catch {
    file = undefined;
  }
  if (!file) {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('404 Not Found');
    return;
  }

  const headers = {
    'Content-Type': file.type,
    'X-Content-Type-Options': 'nosniff',
    // Next.js build assets are content-hashed; pages must revalidate.
    'Cache-Control': req.url.startsWith('/_next/static/')
      ? 'public, max-age=31536000, immutable'
      : 'no-cache',
  };
  const sendGzip = file.gzipped && /\bgzip\b/.test(req.headers['accept-encoding'] || '');
  if (file.gzipped) headers.Vary = 'Accept-Encoding';
  if (sendGzip) headers['Content-Encoding'] = 'gzip';
  res.writeHead(200, headers);
  if (req.method === 'HEAD') {
    res.end();
    return;
  }

  const body = createReadStream(file.path);
  body.on('error', () => res.destroy());
  if (file.gzipped && !sendGzip) {
    body.pipe(createGunzip()).on('error', () => res.destroy()).pipe(res);
  } else {
    body.pipe(res);
  }
});

server.listen(PORT, () => console.log(`serving ${ROOT} on :${PORT}`));

// Node as PID 1 ignores SIGTERM by default; exit promptly so a rollout does
// not wait out the termination grace period.
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
