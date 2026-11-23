'use strict';
// Builds examples/pr-73235/review.json from the prototype data in prototypes/.
// Run with: node scripts/build_example.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.join(__dirname, '..');
const dataPath = path.join(root, 'prototypes', 'data.js');
const appPath = path.join(root, 'prototypes', 'app.html');
const outPath = path.join(root, 'examples', 'pr-73235', 'review.json');

const dataJs = fs.readFileSync(dataPath, 'utf8');
const appHtml = fs.readFileSync(appPath, 'utf8');

// --- Extract the const ... blocks from app.html by string location. ---

function skipString(src, i) {
  const quote = src[i];
  i += 1;
  while (i < src.length) {
    if (src[i] === '\\') {
      i += 2;
      continue;
    }
    if (src[i] === quote) return i + 1;
    i += 1;
  }
  throw new Error('unterminated string in app.html');
}

// Start at `marker` (which ends right before an opening bracket) and return the
// whole statement up to and including its terminating `;`, skipping strings so
// brackets inside text literals do not confuse the matching.
function extractBracketed(src, marker) {
  const start = src.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  let i = start + marker.length - 1; // points at the opening bracket
  const open = src[i];
  const close = { '{': '}', '[': ']', '(': ')' }[open];
  if (!close) throw new Error('expected an opening bracket after: ' + marker);
  let depth = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === '"' || c === "'") {
      i = skipString(src, i);
      continue;
    }
    if (c === open) depth += 1;
    else if (c === close) {
      depth -= 1;
      if (depth === 0) {
        i += 1;
        break;
      }
    }
    i += 1;
  }
  while (i < src.length && /\s/.test(src[i])) i += 1;
  if (src[i] !== ';') {
    throw new Error('expected ";" after block, found: ' + JSON.stringify(src.slice(i, i + 12)));
  }
  return src.slice(start, i + 1);
}

// `const Fi=...` is a one-line arrow function; no internal semicolons.
function extractSingleStatement(src, marker) {
  const start = src.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  const end = src.indexOf(';', start);
  if (end < 0) throw new Error('no terminating ";" for: ' + marker);
  return src.slice(start, end + 1);
}

const appCode =
  [
    extractSingleStatement(appHtml, 'const Fi='),
    extractBracketed(appHtml, 'const FILES=['),
    extractBracketed(appHtml, 'const M={'),
    extractBracketed(appHtml, 'const CHAPTERS=['),
    extractBracketed(appHtml, 'const GLOSS=['),
  ].join('\n') +
  '\n;__out = {M: M, GLOSS: GLOSS, CHAPTERS: CHAPTERS, FILES: FILES};';

// --- Run both sources in a shared sandbox. ---
const sandbox = {
  window: {},
  location: { search: '' },
  URLSearchParams, // data.js builds window.RP from location.search
  T: (en, zh) => ({ en, zh }), // the bilingual-object constructor used by app.html
};
vm.createContext(sandbox);

vm.runInContext(dataJs, sandbox, { filename: 'data.js' });
vm.runInContext(appCode, sandbox, { filename: 'app.html' });

const out = sandbox.__out;
const units = sandbox.window.UNITS;
const filesrc = sandbox.window.FILESRC;
const newfiles = sandbox.window.NEWFILES;

const review = {
  meta: {
    repo: 'pingcap/tidb',
    pr: 73235,
    title: out.M.title,
    mode: 'pr',
    root: '',
    base: 'aa410927742db7869a31f7c4a85a34cf0ad88c5c',
    head: '61d912dd20e0b21420772633063b0f7c84aeb103',
  },
  overview: {
    summary: out.M.verdict,
    bg: out.M.bg,
    bgLong: out.M.bgLong,
    depthWhy: out.M.depthWhy,
    design: out.M.design,
    // The prototype draws the change map in code; keep the map already in the example.
    map: JSON.parse(fs.readFileSync(outPath, 'utf8')).overview.map,
    cover: out.M.cover,
    decide: out.M.decide,
  },
  glossary: out.GLOSS,
  files: out.FILES,
  chapters: out.CHAPTERS,
  units: units,
  filesrc: filesrc,
  newfiles: newfiles,
};

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, JSON.stringify(review, null, 2) + '\n');
console.log('wrote ' + outPath);
