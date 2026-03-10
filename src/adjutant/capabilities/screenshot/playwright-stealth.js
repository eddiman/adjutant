// Stealth patches to avoid bot detection
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'permissions', {
  get: () => ({
    query: (p) => Promise.resolve({ state: p.name === 'notifications' ? 'denied' : 'granted' })
  })
});
