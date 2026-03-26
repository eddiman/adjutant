import { useCallback, useEffect, useState } from 'react';
import type { Settings, Theme } from '../types';

const STORAGE_KEY = 'adjutant-web-settings';

const defaultSettings: Settings = {
  theme: 'default',
  snapToObject: true,
  showSnapLines: true,
};

function loadSettings(): Settings {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return { ...defaultSettings, ...JSON.parse(stored) };
    }
  } catch {
    // Invalid JSON
  }
  return defaultSettings;
}

export { type Settings, type Theme };

export function useSettings() {
  const [settings, setSettings] = useState<Settings>(loadSettings);

  // Load kbRoot from server on mount
  useEffect(() => {
    fetch('/api/config')
      .then(res => res.json())
      .then(config => {
        if (config.kbRoot) {
          setSettings(prev => ({ ...prev, kbRoot: config.kbRoot }));
        }
      })
      .catch(() => {
        // Server not available
      });
  }, []);

  const updateSetting = useCallback(<K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings(prev => {
      const next = { ...prev, [key]: value };

      // Persist local settings to localStorage
      const { kbRoot: _, ...localSettings } = next;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(localSettings));

      // If kbRoot changed, persist to server
      if (key === 'kbRoot') {
        fetch('/api/config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kbRoot: value }),
        }).catch(err => console.error('Failed to save kbRoot:', err));
      }

      return next;
    });
  }, []);

  return { settings, updateSetting };
}
