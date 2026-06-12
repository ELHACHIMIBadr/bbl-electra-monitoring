/**
 * Service Worker — BBL-ELECTRA Monitoring
 * Push Notifications + Offline Cache
 */

const CACHE_NAME = 'bbl-electra-v1';
const STATIC_ASSETS = [
  '/',
  '/frontend/css/style.css',
  '/frontend/js/app.js',
  '/frontend/js/api.js',
  '/frontend/manifest.json'
];

// Install — Cache les assets statiques
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate — Nettoyer les anciens caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch — Network first, fallback to cache
self.addEventListener('fetch', event => {
  if (event.request.url.includes('/api/')) {
    // API calls: network only
    event.respondWith(fetch(event.request));
  } else {
    // Static assets: network first, then cache
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  }
});

// Push Notification — Recevoir et afficher
self.addEventListener('push', event => {
  let data = { title: 'BBL-ELECTRA', body: 'Nouvelle alerte' };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body || data.message,
    icon: '/frontend/icons/icon-192x192.png',
    badge: '/frontend/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    tag: data.tag || 'alert',
    renotify: true,
    data: { url: data.url || '/' },
    actions: [
      { action: 'view', title: 'Voir' },
      { action: 'dismiss', title: 'OK' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'BBL-ELECTRA', options)
  );
});

// Click sur la notification
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(windowClients => {
      for (const client of windowClients) {
        if (client.url === '/' && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow('/');
    })
  );
});
