#!/usr/bin/env node
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const indexFile = path.join(root, 'web', 'index.html');
const reviewFile = path.join(root, 'examples', 'pr-73235', 'review.json');

let passed = 0;
let failed = 0;
function check(name, ok) {
  if (ok) { passed++; console.log('  ok  ' + name); }
  else { failed++; console.log('FAIL  ' + name); }
}

const html = fs.readFileSync(indexFile, 'utf8');

// ---- static checks on web/index.html ----
check("no <script src=\"data.js\">", !/src=["']data\.js["']/.test(html));
check("no hardcoded pingcap/tidb#73235", !html.includes('pingcap/tidb#73235'));
for (const ep of ['/api/review', '/api/prefs', '/api/state', '/api/send', '/api/open', '/api/version']) {
  check('contains ' + ep, html.includes(ep));
}
check('figure sanitizer present', html.includes('DOMParser') && html.includes('script|foreignobject') && html.includes("startsWith('on')"));
check('design rendered with prose', html.includes('${prose(L(d))}') && !html.includes('${terms(L(d))}'));

// ---- fake contract server (informational; the assertions above are the gate) ----
let reviewData = null;
if (fs.existsSync(reviewFile)) {
  reviewData = JSON.parse(fs.readFileSync(reviewFile, 'utf8'));
  console.log('  info using examples/pr-73235/review.json (' + (reviewData.units || []).length + ' units)');
} else {
  console.log('  info examples/pr-73235/review.json not found; fake server will stub /api/review');
}

let version = 7;
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  const send = (code, obj) => {
    const body = JSON.stringify(obj);
    res.writeHead(code, { 'Content-Type': 'application/json' });
    res.end(body);
  };
  let raw = '';
  req.on('data', (c) => { raw += c; });
  req.on('end', () => {
    if (url.pathname === '/api/review') {
      if (reviewData) send(200, Object.assign({}, reviewData, { version }));
      else send(200, { meta: { repo: 'example/repo', pr: 1, title: { en: 't', zh: 't' }, root: '/' }, overview: {}, glossary: [], files: [], chapters: [], units: [], filesrc: {}, newfiles: [], version });
    } else if (url.pathname === '/api/version') {
      send(200, { version });
    } else if (url.pathname === '/api/prefs' && req.method === 'GET') {
      send(200, { theme: 'claude', lang: 'en', notes: true, order: 'reading', editor: 'rustrover', depth: {}, hinted: false });
    } else if (url.pathname === '/api/prefs' && req.method === 'PUT') {
      send(200, { ok: true });
    } else if (url.pathname === '/api/state' && req.method === 'GET') {
      send(200, { done: {}, drafts: [] });
    } else if (url.pathname === '/api/state' && req.method === 'PUT') {
      send(200, { ok: true });
    } else if (url.pathname === '/api/send' && req.method === 'POST') {
      send(200, { round: 1, path: 'comments-round-1.md' });
    } else if (url.pathname === '/api/open' && req.method === 'POST') {
      send(200, { ok: true });
    } else {
      send(404, { error: 'not found' });
    }
  });
});

let finished = false;
function finish() {
  if (finished) return;
  finished = true;
  console.log('');
  console.log(passed + ' passed, ' + failed + ' failed');
  process.exit(failed ? 1 : 0);
}
server.on('error', (err) => {
  console.log('  info fake server could not bind (' + err.code + '); static checks only');
  finish();
});
server.listen(0, '127.0.0.1', () => {
  const addr = server.address();
  console.log('  info fake server on http://127.0.0.1:' + addr.port + ' (started, then closed)');
  server.close(finish);
});
