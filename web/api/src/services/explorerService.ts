import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import type { DirectoryEntry, ExplorerRoots, KbRootValidation } from '../types/explorer.js';
import { configService } from './configService.js';

const DENIED_SEGMENTS = new Set([
  '.ssh', '.gnupg', '.env', 'node_modules', '.git',
]);

const DENIED_PATHS_UNIX = new Set([
  '/proc', '/sys', '/dev', '/private/var/db',
]);

const MAX_ENTRIES = 200;

class ExplorerService {
  /**
   * Return platform-aware filesystem root starting points.
   */
  async getRoots(): Promise<ExplorerRoots> {
    const home = os.homedir();
    const current = await configService.getKbRoot() ?? undefined;
    const platform = process.platform;

    let roots: { path: string; label: string }[];

    if (platform === 'darwin') {
      roots = [
        { path: home, label: 'Home' },
        { path: '/', label: '/' },
        { path: '/Volumes', label: 'Volumes' },
      ];
    } else if (platform === 'win32') {
      // List available drive letters
      roots = [{ path: home, label: 'Home' }];
      for (const letter of 'CDEFGHIJKLMNOPQRSTUVWXYZ') {
        const drive = `${letter}:\\`;
        try {
          await fs.access(drive);
          roots.push({ path: drive, label: `${letter}:` });
        } catch {
          // Drive doesn't exist
        }
      }
    } else {
      // Linux / other Unix
      roots = [
        { path: home, label: 'Home' },
        { path: '/', label: '/' },
      ];
      try {
        await fs.access('/mnt');
        roots.push({ path: '/mnt', label: 'Mounts' });
      } catch { /* no /mnt */ }
    }

    return { roots, home, current };
  }

  /**
   * List subdirectories at a given absolute path.
   */
  async listDirectories(absolutePath: string): Promise<DirectoryEntry[] | null> {
    const resolved = path.resolve(absolutePath);

    if (!this.isPathAllowed(resolved)) {
      return null;
    }

    let dirEntries;
    try {
      dirEntries = await fs.readdir(resolved, { withFileTypes: true });
    } catch {
      return null;
    }

    const entries: DirectoryEntry[] = [];

    for (const entry of dirEntries) {
      // Skip hidden entries
      if (entry.name.startsWith('.')) continue;

      // Skip denied segments
      if (DENIED_SEGMENTS.has(entry.name)) continue;

      let isDir = false;
      const entryPath = path.join(resolved, entry.name);

      try {
        if (entry.isDirectory()) {
          isDir = true;
        } else if (entry.isSymbolicLink()) {
          const stat = await fs.stat(entryPath);
          isDir = stat.isDirectory();
        }
      } catch {
        continue;
      }

      if (!isDir) continue;

      // Check if it has subdirectories (for expand arrows in UI)
      let hasChildren = false;
      try {
        const subEntries = await fs.readdir(entryPath, { withFileTypes: true });
        hasChildren = subEntries.some(
          e => (e.isDirectory() || e.isSymbolicLink()) && !e.name.startsWith('.') && !DENIED_SEGMENTS.has(e.name)
        );
      } catch {
        // Can't read — treat as no children
      }

      entries.push({ name: entry.name, path: entryPath, hasChildren });

      if (entries.length >= MAX_ENTRIES) break;
    }

    entries.sort((a, b) => a.name.localeCompare(b.name));
    return entries;
  }

  /**
   * Validate whether a path looks like a valid KB root.
   */
  async validateKbRoot(absolutePath: string): Promise<KbRootValidation> {
    const resolved = path.resolve(absolutePath);
    const kbNames: string[] = [];

    try {
      const stat = await fs.stat(resolved);
      if (!stat.isDirectory()) {
        return { valid: false, kbCount: 0, kbNames: [] };
      }
    } catch {
      return { valid: false, kbCount: 0, kbNames: [] };
    }

    try {
      const entries = await fs.readdir(resolved, { withFileTypes: true });
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;
        try {
          await fs.access(path.join(resolved, entry.name, 'kb.yaml'));
          kbNames.push(entry.name);
        } catch {
          // Not a KB
        }
      }
    } catch {
      return { valid: false, kbCount: 0, kbNames: [] };
    }

    return {
      valid: kbNames.length > 0,
      kbCount: kbNames.length,
      kbNames,
    };
  }

  /**
   * Check if a path is allowed to be browsed.
   */
  private isPathAllowed(resolved: string): boolean {
    // Must be absolute
    if (!path.isAbsolute(resolved)) return false;

    // Check against denied unix paths
    for (const denied of DENIED_PATHS_UNIX) {
      if (resolved === denied || resolved.startsWith(denied + '/')) {
        return false;
      }
    }

    // Check path segments for denied names
    const segments = resolved.split(path.sep);
    for (const seg of segments) {
      if (DENIED_SEGMENTS.has(seg)) return false;
    }

    // Check env-based allowlist
    const allowedRoots = process.env.ADJUTANT_EXPLORER_ALLOWED_ROOTS;
    if (allowedRoots) {
      const roots = allowedRoots.split(',').map(r => r.trim());
      const underAllowed = roots.some(
        root => resolved === root || resolved.startsWith(root + path.sep)
      );
      if (!underAllowed) return false;
    }

    return true;
  }
}

export const explorerService = new ExplorerService();
