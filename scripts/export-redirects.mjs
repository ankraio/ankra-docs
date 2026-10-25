// Writes the redirect list scripts/serve.mjs answers for a static `mint export`.
//
//   node scripts/export-redirects.mjs <docs.json> <site dir> <out.json>
//
// Two kinds of URL have no page in the export but resolve under `mint dev`:
// - docs.json `redirects`, copied as they are;
// - a directory with no page of its own (`/guides`, `/api-reference/alerts`),
//   which `mint dev` sends to the first page under it in navigation order:
//   docs.json's navigation where it lists a page under the directory, and
//   otherwise (OpenAPI-generated pages docs.json does not list) the sidebar of
//   an exported page under it, taking the first link inside the directory.
//
// Run before the site's HTML is gzipped.
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

const [docsJson, siteDir, outFile] = process.argv.slice(2);
const docs = JSON.parse(readFileSync(docsJson, 'utf8'));
const redirects = docs.redirects || [];
const sources = new Set(redirects.map((r) => r.source.replace(/\/+$/, '')));

// Pages docs.json's navigation lists, in navigation order.
const navOrder = [];
(function collect(node, inPages) {
  if (typeof node === 'string') {
    if (inPages) navOrder.push(`/${node.replace(/^\/+/, '')}`.replace(/\/index$/, ''));
  } else if (Array.isArray(node)) {
    for (const item of node) collect(item, inPages);
  } else if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node)) collect(value, key === 'pages');
  }
})(docs.navigation, false);

// URL path of every exported page, and the page file each was rendered to.
const pages = new Map();
(function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walk(path);
    else if (entry.name.endsWith('.html')) {
      // `a/b.html` and `a/b/index.html` are page /a/b; a docs page named
      // index (`a/index.mdx`, exported as `a/index/index.html`) is also /a.
      const url = `/${relative(siteDir, path).split(sep).join('/')}`
        .replace(/\.html$/, '')
        .replace(/\/index$/, '');
      pages.set(url || '/', path);
      if (url.endsWith('/index')) pages.set(url.slice(0, -'/index'.length) || '/', path);
    }
  }
})(siteDir);

// Every ancestor directory of a page that is not itself a page.
const dirs = new Map();
for (const [url, file] of pages) {
  if (url.startsWith('/_next')) continue;
  const parts = url.split('/').slice(1, -1);
  for (let i = 1; i <= parts.length; i++) {
    const dir = `/${parts.slice(0, i).join('/')}`;
    if (!pages.has(dir) && !sources.has(dir) && !dirs.has(dir)) dirs.set(dir, file);
  }
}

const generated = [];
for (const [dir, file] of dirs) {
  const listed = navOrder.find((url) => url.startsWith(`${dir}/`) && pages.has(url));
  if (listed) {
    generated.push({ source: dir, destination: listed });
    continue;
  }
  const html = readFileSync(file, 'utf8');
  for (const [, href] of html.matchAll(/href="([^"#?]+)"/g)) {
    const target = href.replace(/\/+$/, '');
    if (target.startsWith(`${dir}/`) && pages.has(target)) {
      generated.push({ source: dir, destination: target });
      break;
    }
  }
}

writeFileSync(outFile, JSON.stringify([...redirects, ...generated]));
console.log(`redirects: ${redirects.length} from docs.json, ${generated.length} for directories without a page`);
