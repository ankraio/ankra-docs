import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, mkdir, writeFile, rm, symlink, open } from 'node:fs/promises';
import { request } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync, gunzipSync } from 'node:zlib';
import test from 'node:test';

const serverFile = fileURLToPath(new URL('./serve.mjs', import.meta.url));

async function fixture(t, manifest = []) {
  const directory = await mkdtemp(join(tmpdir(), 'docs-serve-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const site = join(directory, 'site');
  await mkdir(site);
  await writeFile(join(site, 'index.html.gz'), gzipSync('fixture page'));
  const redirects = join(directory, 'redirects.json');
  if (manifest !== undefined) await writeFile(redirects, JSON.stringify(manifest));
  return { directory, site, redirects };
}

function start(t, fixture) {
  const child = spawn(process.execPath, [serverFile], {
    env: { ...process.env, SITE_DIR: fixture.site, REDIRECTS_FILE: fixture.redirects, PORT: '0' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const exit = once(child, 'exit');
  t.after(async () => {
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
    await exit;
  });
  return { child, exit };
}

async function ready(child) {
  let output = '';
  for await (const chunk of child.stdout) {
    output += chunk;
    const match = /on :(\d+)/.exec(output);
    if (match) return Number(match[1]);
  }
  throw new Error('Server exited before listening');
}

function get(port, path, headers = {}, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = request({ host: '127.0.0.1', port, path, headers, method }, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks) }));
      res.on('error', reject);
    });
    req.on('error', reject);
    req.end();
  });
}

for (const [name, manifest] of [['object', {}], ['invalid entry', [{}]], ['empty entry', [{ source: '', destination: '/new' }]]]) {
  test(`refuses ${name} redirect manifest at startup`, { timeout: 5000 }, async (t) => {
    const files = await fixture(t, manifest);
    const { exit } = start(t, files);
    const [code, signal] = await exit;
    assert.equal(signal, null);
    assert.equal(code, 1);
  });
}

for (const name of ['missing', 'malformed']) {
  test(`refuses ${name} redirect manifest at startup`, { timeout: 5000 }, async (t) => {
    const files = await fixture(t);
    if (name === 'missing') await rm(files.redirects);
    else await writeFile(files.redirects, '{');
    const { exit } = start(t, files);
    const [code, signal] = await exit;
    assert.equal(signal, null);
    assert.equal(code, 1);
  });
}

test('serves pages, redirects and encoding preferences while rejecting escapes', { timeout: 5000 }, async (t) => {
  const files = await fixture(t, [{ source: '/old/:slug*', destination: '/new/:slug*' }]);
  await writeFile(join(files.directory, 'private.html'), 'outside site');
  await symlink(join(files.directory, 'private.html'), join(files.site, 'escape.html'));
  const { child, exit } = start(t, files);
  const port = await ready(child);
  const plain = await get(port, '/', { 'accept-encoding': 'gzip;q=0, *;q=1' });
  assert.equal(plain.status, 200);
  assert.equal(plain.headers['content-encoding'], undefined);
  assert.equal(plain.body.toString(), 'fixture page');
  const zipped = await get(port, '/', { 'accept-encoding': 'gzip' });
  assert.equal(zipped.headers['content-encoding'], 'gzip');
  assert.equal(gunzipSync(zipped.body).toString(), 'fixture page');
  assert.equal((await get(port, '/', {}, 'HEAD')).body.length, 0);
  for (const path of ['/escape.html', '/%2e%2e%2fprivate.html', '/%00', '/missing']) {
    assert.equal((await get(port, path)).status, 404, path);
  }
  assert.equal((await get(port, '/', {}, 'POST')).status, 405);
  const redirect = await get(port, '/old/a/b');
  assert.equal(redirect.status, 307);
  assert.equal(redirect.headers.location, '/new/a/b');
  assert.equal((await get(port, '/old')).headers.location, '/new');
  child.kill('SIGTERM');
  assert.deepEqual(await exit, [0, null]);
});

test('bounds shutdown while an active client stops consuming a large response', { timeout: 30000 }, async (t) => {
  const files = await fixture(t);
  const large = await open(join(files.site, 'large.txt'), 'w');
  await large.truncate(64 * 1024 * 1024);
  await large.close();
  const { child, exit } = start(t, files);
  const port = await ready(child);
  const req = request({ host: '127.0.0.1', port, path: '/large.txt' });
  t.after(() => req.destroy());
  req.on('error', () => {});
  const response = once(req, 'response');
  req.end();
  const [res] = await response;
  res.on('error', () => {});
  assert.equal(res.statusCode, 200);
  assert.equal(res.headers['transfer-encoding'], 'chunked');
  assert.equal(res.complete, false);
  res.pause();
  child.kill('SIGTERM');
  assert.deepEqual(await exit, [0, null]);
});
