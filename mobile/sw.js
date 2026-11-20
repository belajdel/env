/**
 * Service Worker for Environmental Monitoring PWA
 * Provides offline support, caching, and push notifications
 */

const CACHE_NAME = 'envmonitor-v1';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/styles.css',
    '/app.js',
    '/manifest.json',
    '/icon.svg',
];

const CACHE_STRATEGIES = {
    // Network first, fallback to cache
    networkFirst: [
        '/api/',
        '/auth/',
        '/zones',
        '/devices',
        '/measurements',
        '/alerts',
        '/reports',
        '/ai/',
        '/relay',
    ],
    // Cache first, fallback to network
    cacheFirst: [
        '/styles.css',
        '/app.js',
        '/manifest.json',
        '/icon.svg',
        '/icon-',
    ],
    // Stale while revalidate
    staleWhileRevalidate: [
        '/',
        '/index.html',
    ],
};

// Install event - cache static assets
self.addEventListener('install', (event) => {
    console.log('[SW] Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[SW] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => self.skipWaiting())
    );
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
    console.log('[SW] Activating...');
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => name !== CACHE_NAME)
                        .map((name) => caches.delete(name))
                );
            })
            .then(() => self.clients.claim())
    );
});

// Fetch event - implement caching strategies
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }
    
    // Skip chrome-extension and other non-http(s) requests
    if (!url.protocol.startsWith('http')) {
        return;
    }
    
    // Determine caching strategy
    let strategy = 'networkFirst';
    
    for (const [key, patterns] of Object.entries(CACHE_STRATEGIES)) {
        if (patterns.some(pattern => url.pathname.startsWith(pattern) || url.href.includes(pattern))) {
            strategy = key;
            break;
        }
    }
    
    switch (strategy) {
        case 'cacheFirst':
            event.respondWith(cacheFirst(event.request));
            break;
        case 'staleWhileRevalidate':
            event.respondWith(staleWhileRevalidate(event.request));
            break;
        case 'networkFirst':
        default:
            event.respondWith(networkFirst(event.request));
            break;
    }
});

// Network first strategy
async function networkFirst(request) {
    try {
        const response = await fetch(request);
        
        // Cache successful responses
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        
        return response;
    } catch (error) {
        console.log('[SW] Network failed, trying cache:', request.url);
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Return offline page for navigation requests
        if (request.mode === 'navigate') {
            return caches.match('/index.html');
        }
        
        throw error;
    }
}

// Cache first strategy
async function cacheFirst(request) {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
        // Update cache in background
        fetch(request).then(response => {
            if (response.ok) {
                caches.open(CACHE_NAME).then(cache => cache.put(request, response));
            }
        }).catch(() => {});
        return cachedResponse;
    }
    
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch (error) {
        if (request.mode === 'navigate') {
            return caches.match('/index.html');
        }
        throw error;
    }
}

// Stale while revalidate strategy
async function staleWhileRevalidate(request) {
    const cachedResponse = await caches.match(request);
    
    const fetchPromise = fetch(request).then(response => {
        if (response.ok) {
            caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone()));
        }
        return response;
    }).catch(() => cachedResponse);
    
    return cachedResponse || fetchPromise;
}

// Push notification event
self.addEventListener('push', (event) => {
    console.log('[SW] Push received');
    
    let notificationData = {
        title: 'EnvMonitor',
        body: 'New notification',
        icon: '/icon-192.png',
        badge: '/icon-72.png',
        tag: 'default',
        data: {},
        actions: [
            { action: 'view', title: 'View' },
            { action: 'dismiss', title: 'Dismiss' },
        ],
        requireInteraction: true,
    };
    
    if (event.data) {
        try {
            const payload = event.data.json();
            notificationData = { ...notificationData, ...payload };
        } catch (e) {
            notificationData.body = event.data.text();
        }
    }
    
    // Adjust for alert level
    if (notificationData.data.level === 'critical') {
        notificationData.requireInteraction = true;
        notificationData.vibrate = [200, 100, 200, 100, 200];
    } else if (notificationData.data.level === 'warning') {
        notificationData.vibrate = [100, 50, 100];
    }
    
    event.waitUntil(
        self.registration.showNotification(notificationData.title, notificationData)
    );
});

// Notification click event
self.addEventListener('notificationclick', (event) => {
    console.log('[SW] Notification clicked:', event.action);
    
    event.notification.close();
    
    if (event.action === 'dismiss') {
        return;
    }
    
    // Determine target URL based on notification data
    let targetUrl = '/';
    const data = event.notification.data || {};
    
    if (data.type === 'alert') {
        targetUrl = `/?page=alerts&alert=${data.alert_id}`;
    } else if (data.type === 'report') {
        targetUrl = `/?page=reports&report=${data.report_id}`;
    } else if (data.zone_id) {
        targetUrl = `/?page=zones&zone=${data.zone_id}`;
    }
    
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                // Check if app is already open
                for (const client of clientList) {
                    if (client.url.includes(self.location.origin) && 'focus' in client) {
                        client.postMessage({ type: 'navigate', url: targetUrl });
                        return client.focus();
                    }
                }
                // Open new window
                return clients.openWindow(targetUrl);
            })
    );
});

// Notification close event
self.addEventListener('notificationclose', (event) => {
    console.log('[SW] Notification closed');
    // Could send analytics here
});

// Message event - communication with main thread
self.addEventListener('message', (event) => {
    console.log('[SW] Message received:', event.data);
    
    if (event.data.type === 'skipWaiting') {
        self.skipWaiting();
    } else if (event.data.type === 'getCacheInfo') {
        getCacheInfo().then(info => {
            event.ports[0].postMessage({ type: 'cacheInfo', data: info });
        });
    } else if (event.data.type === 'clearCache') {
        clearAllCaches().then(() => {
            event.ports[0].postMessage({ type: 'cacheCleared' });
        });
    }
});

// Background sync for offline actions
self.addEventListener('sync', (event) => {
    console.log('[SW] Background sync:', event.tag);
    
    if (event.tag === 'sync-alerts') {
        event.waitUntil(syncPendingAlerts());
    } else if (event.tag === 'sync-relay') {
        event.waitUntil(syncPendingRelayCommands());
    }
});

// Periodic background sync (if supported)
self.addEventListener('periodicsync', (event) => {
    if (event.tag === 'update-risk-scores') {
        event.waitUntil(updateRiskScoresInBackground());
    }
});

// Helper functions
async function getCacheInfo() {
    const cache = await caches.open(CACHE_NAME);
    const keys = await cache.keys();
    return {
        cacheName: CACHE_NAME,
        entries: keys.length,
        urls: keys.map(k => k.url),
    };
}

async function clearAllCaches() {
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames.map(name => caches.delete(name)));
}

async function syncPendingAlerts() {
    // Would sync acknowledged/resolved alerts when back online
    console.log('[SW] Syncing pending alerts...');
}

async function syncPendingRelayCommands() {
    // Would sync relay commands when back online
    console.log('[SW] Syncing pending relay commands...');
}

async function updateRiskScoresInBackground() {
    // Fetch updated risk scores periodically
    console.log('[SW] Updating risk scores in background...');
    try {
        const response = await fetch('/api/ai/risk/all', { credentials: 'include' });
        if (response.ok) {
            // Notify clients
            const clients = await self.clients.matchAll();
            clients.forEach(client => {
                client.postMessage({ type: 'riskScoresUpdated', data: await response.json() });
            });
        }
    } catch (e) {
        console.log('[SW] Background risk update failed:', e);
    }
}

// Handle fetch errors gracefully
self.addEventListener('fetch', (event) => {
    // Catch any unhandled errors
    event.respondWith(
        (async () => {
            try {
                return await networkFirst(event.request);
            } catch (error) {
                console.error('[SW] Fetch failed:', error);
                return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
            }
        })()
    );
});

console.log('[SW] Service Worker loaded');