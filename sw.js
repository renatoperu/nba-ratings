// Offline support. The app shell is served from cache and refreshed in the background;
// data/season.json is fetched from the network first so results are as fresh as possible.
const VERSION = '__VERSION__';
const SHELL = [
  './', 'index.html', 'wnba.html', 'nhl.html', 'manifest.webmanifest',
  'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png',
  'fonts/barlow-latin-400-normal.woff2', 'fonts/barlow-latin-500-normal.woff2', 'fonts/barlow-latin-600-normal.woff2', 'fonts/barlow-latin-700-normal.woff2',
  'fonts/big-shoulders-display-latin-700-normal.woff2', 'fonts/big-shoulders-display-latin-800-normal.woff2', 'fonts/big-shoulders-display-latin-900-normal.woff2',
  'data/season.json', 'data/wnba-season.json', 'data/nhl-season.json'
];
self.addEventListener('install', function(e){
  e.waitUntil(caches.open(VERSION).then(function(c){ return c.addAll(SHELL); }).then(function(){ return self.skipWaiting(); }));
});
self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.filter(function(k){ return k !== VERSION; }).map(function(k){ return caches.delete(k); }));
  }).then(function(){ return self.clients.claim(); }));
});
self.addEventListener('fetch', function(e){
  const req = e.request, url = new URL(req.url);
  if(req.method !== 'GET' || url.origin !== location.origin) return;
  if(/\/data\/[a-z-]*season\.json$/.test(url.pathname)){
    e.respondWith(fetch(req).then(function(r){
      const copy = r.clone(); caches.open(VERSION).then(function(c){ c.put(req, copy); }); return r;
    }).catch(function(){ return caches.match(req); }));
    return;
  }
  e.respondWith(caches.open(VERSION).then(function(c){
    return c.match(req, {ignoreSearch:true}).then(function(hit){
      const net = fetch(req).then(function(r){ if(r && r.ok) c.put(req, r.clone()); return r; }).catch(function(){ return hit || (req.mode === 'navigate' ? c.match(url.pathname.endsWith('wnba.html') ? 'wnba.html' : url.pathname.endsWith('nhl.html') ? 'nhl.html' : 'index.html') : undefined); });
      return hit || net;
    });
  }));
});
