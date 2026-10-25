// Serves the static `mint export` of these docs inside the container image.
//
// Node built-ins only, so the runtime image carries no npm dependency tree for
// the image gate to scan. Text assets are gzipped at build time and stored only
// as `<file>.gz`; they are sent as-is to clients that accept gzip and inflated
// on the fly for the rest.
//
// The export has no pages for docs.json `redirects`, so they are answered here
// from the list the build extracts, with a 307 as `mint dev` answers them.
import { createReadStream, readFileSync, realpathSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, resolve, sep } from 'node:path';
import { createGunzip } from 'node:zlib';

const ROOT = realpathSync(resolve(process.env.SITE_DIR || '/app/site'));
const PORT = Number(process.env.PORT || 3000);
const REDIRECTS = loadRedirects(process.env.REDIRECTS_FILE || '/app/redirects.json');

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

function trimSlash(path) {
  return path.length > 1 ? path.replace(/\/+$/, '') : path;
}

// docs.json redirects use exact sources plus Next.js-style `:name*` segments
// (zero or more path segments, substituted into the destination). A colon not
// followed by a name, as in some generated API slugs, is literal.
function loadRedirects(file) {
  const exact = new Map();
  const patterns = [];
  // The build always writes this manifest. Missing or malformed data must not
  // turn documented links into a healthy server's silent 404s.
  const list = JSON.parse(readFileSync(file, 'utf8'));
  if (!Array.isArray(list)) throw new Error('Redirect manifest must be an array');
  const param = /(\/?:[A-Za-z_]\w*\*)/;
  for (const { source, destination } of list) {
    if (typeof source !== 'string' || typeof destination !== 'string' || !source || !destination) {
      throw new Error('Redirect manifest contains an invalid entry');
    }
    if (!param.test(source)) {
      exact.set(trimSlash(source), destination);
      continue;
    }
    const names = [];
    const pattern = source
      .split(param)
      .map((part) => {
        const name = /^(\/?):([A-Za-z_]\w*)\*$/.exec(part);
        if (!name) return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        names.push(name[2]);
        return name[1] ? '(?:/(.*))?' : '(.*)';
      })
      .join('');
    patterns.push({ re: new RegExp(`^${pattern}$`), names, destination });
  }
  return { exact, patterns };
}

function redirectFor(pathname) {
  const path = trimSlash(pathname);
  const hit = REDIRECTS.exact.get(path);
  if (hit) return hit;
  for (const { re, names, destination } of REDIRECTS.patterns) {
    const match = re.exec(path);
    if (!match) continue;
    return names.reduce(
      (dest, name, i) =>
        dest
          .replace(`/:${name}*`, () => (match[i + 1] ? `/${match[i + 1]}` : ''))
          .replace(`:${name}*`, () => match[i + 1] || ''),
      destination,
    );
  }
  return undefined;
}

// True unless the client gave gzip (or `*`) no weight; `gzip;q=0` refuses it.
function acceptsGzip(header = '') {
  let weight;
  for (const entry of header.toLowerCase().split(',')) {
    const [coding, ...params] = entry.trim().split(';');
    if (coding !== 'gzip' && coding !== '*') continue;
    const q = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
    const value = q ? Number(q.slice(2)) : 1;
    if (coding === 'gzip' || weight === undefined) weight = value;
  }
  return weight > 0;
}

// A regular file whose real path (symlinks resolved) is still inside ROOT.
function isFile(path) {
  try {
    const real = realpathSync(path);
    return real.startsWith(ROOT + sep) && statSync(real).isFile();
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
  // The last candidate is a docs page named index (`a/index.mdx` is exported
  // as `a/index/index.html`), which `mint dev` serves at /a.
  for (const candidate of [base, join(base, 'index.html'), `${base}.html`, join(base, 'index', 'index.html')]) {
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

  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://docs').pathname);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('404 Not Found');
    return;
  }

  // Redirects win over files and drop the query string, as `mint dev` does.
  const location = redirectFor(pathname);
  if (location) {
    res.writeHead(307, { Location: encodeURI(location), 'Cache-Control': 'no-cache' }).end();
    return;
  }

  const file = lookup(pathname);
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
  const sendGzip = file.gzipped && acceptsGzip(req.headers['accept-encoding']);
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

server.listen(PORT, () => console.log(`serving ${ROOT} on :${server.address().port}`));

// Node as PID 1 ignores SIGTERM by default; exit promptly so a rollout does
// not wait out the termination grace period.
let stopping = false;
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => {
    if (stopping) return;
    stopping = true;
    // Allow active transfers to drain, then bound termination even if a client
    // stops reading. Idle connections still close immediately.
    const deadline = setTimeout(() => {
      server.closeAllConnections();
      process.exit(0);
    }, 10_000).unref();
    server.close(() => {
      clearTimeout(deadline);
      process.exit(0);
    });
    // close() waits for open keep-alive sockets; drop the idle ones now.
    server.closeIdleConnections();
  });
}
