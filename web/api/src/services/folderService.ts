import fs from 'fs/promises';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { kbService } from './kbService.js';
import { WebSidecarSchema } from '../types/folder.js';
import type { WebSidecar, FolderEntry, FolderListing } from '../types/folder.js';

const SIDECAR_FILENAME = '.adjutant-web.json';

class FolderService {
  /**
   * List folder contents with .adjutant-web.json metadata.
   * path is relative to the KB root (empty string = KB root).
   */
  async list(kb: string, folderPath: string = ''): Promise<FolderListing | null> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return null;

    const entries: FolderEntry[] = [];

    try {
      const dirEntries = await fs.readdir(absPath, { withFileTypes: true });

      for (const entry of dirEntries) {
        // Skip hidden files/folders (including .adjutant-web.json itself)
        if (entry.name.startsWith('.')) continue;

        if (entry.isDirectory()) {
          entries.push({ name: entry.name, type: 'folder' });
        } else if (entry.isFile()) {
          try {
            const stat = await fs.stat(path.join(absPath, entry.name));
            entries.push({
              name: entry.name,
              type: 'file',
              size: stat.size,
              mtime: stat.mtime.toISOString(),
            });
          } catch {
            entries.push({ name: entry.name, type: 'file' });
          }
        }
      }
    } catch {
      return null;
    }

    // Sort: folders first, then files, alphabetically within each group
    entries.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });

    const meta = await this.readSidecar(absPath);

    return {
      kb,
      path: folderPath,
      entries,
      meta,
    };
  }

  /**
   * Read the .adjutant-web.json sidecar for a folder.
   */
  async getMeta(kb: string, folderPath: string = ''): Promise<WebSidecar | null> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return null;

    return this.readSidecar(absPath);
  }

  /**
   * Update the .adjutant-web.json sidecar for a folder.
   * Merges the update with existing data.
   */
  async updateMeta(kb: string, folderPath: string = '', update: Partial<WebSidecar>): Promise<WebSidecar | null> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return null;

    const existing = await this.readSidecar(absPath);
    const merged: WebSidecar = {
      items: { ...existing.items, ...update.items },
      sections: update.sections !== undefined ? { ...existing.sections, ...update.sections } : existing.sections,
      stickies: update.stickies !== undefined ? { ...existing.stickies, ...update.stickies } : existing.stickies,
      images: update.images !== undefined ? { ...existing.images, ...update.images } : existing.images,
    };

    await this.writeSidecar(absPath, merged);
    return merged;
  }

  /**
   * Remove an item's metadata from the .adjutant-web.json sidecar.
   */
  async removeItemMeta(kb: string, folderPath: string = '', itemName: string): Promise<boolean> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return false;

    const meta = await this.readSidecar(absPath);
    if (!meta.items[itemName]) return false;

    delete meta.items[itemName];
    await this.writeSidecar(absPath, meta);
    return true;
  }

  // === Section helpers ===

  async createSection(kb: string, folderPath: string, input: { name?: string; position?: { x: number; y: number }; width?: number; height?: number; color?: string }): Promise<{ id: string; section: import('../types/folder.js').SectionData } | null> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return null;

    const meta = await this.readSidecar(absPath);
    const id = `section-${uuidv4()}`;
    const now = new Date().toISOString();

    const section: import('../types/folder.js').SectionData = {
      name: input.name || 'Section',
      position: input.position,
      width: input.width || 500,
      height: input.height || 400,
      color: input.color,
      createdAt: now,
      updatedAt: now,
    };

    meta.sections[id] = section;

    await this.writeSidecar(absPath, meta);
    return { id, section };
  }

  async deleteSection(kb: string, folderPath: string, sectionId: string): Promise<boolean> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return false;

    const meta = await this.readSidecar(absPath);
    if (!meta.sections[sectionId]) return false;

    delete meta.sections[sectionId];

    // Clear section reference from items
    for (const itemMeta of Object.values(meta.items)) {
      if (itemMeta.section === sectionId) {
        delete itemMeta.section;
      }
    }

    await this.writeSidecar(absPath, meta);
    return true;
  }

  // === Sticky helpers ===

  async createSticky(kb: string, folderPath: string, input: { text?: string; color?: import('../types/folder.js').StickyColor; position?: { x: number; y: number } }): Promise<{ id: string; sticky: import('../types/folder.js').StickyData } | null> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return null;

    const meta = await this.readSidecar(absPath);
    const id = `sticky-${uuidv4()}`;
    const now = new Date().toISOString();

    const sticky: import('../types/folder.js').StickyData = {
      text: input.text || '',
      color: input.color || 'yellow',
      position: input.position,
      createdAt: now,
      updatedAt: now,
    };

    meta.stickies[id] = sticky;

    await this.writeSidecar(absPath, meta);
    return { id, sticky };
  }

  async deleteSticky(kb: string, folderPath: string, stickyId: string): Promise<boolean> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return false;

    const meta = await this.readSidecar(absPath);
    if (!meta.stickies[stickyId]) return false;

    delete meta.stickies[stickyId];
    await this.writeSidecar(absPath, meta);
    return true;
  }

  // === Image helpers ===

  async updateImagePosition(kb: string, folderPath: string, imageId: string, position: import('../types/folder.js').Position, width?: number, height?: number): Promise<boolean> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return false;

    const meta = await this.readSidecar(absPath);
    if (!meta.images) meta.images = {};
    if (!meta.images[imageId]) meta.images[imageId] = {};
    
    meta.images[imageId].position = position;
    if (width !== undefined) meta.images[imageId].width = width;
    if (height !== undefined) meta.images[imageId].height = height;

    await this.writeSidecar(absPath, meta);
    return true;
  }

  async getImagePosition(kb: string, folderPath: string, imageId: string): Promise<import('../types/folder.js').ImageMeta | null> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return null;

    const meta = await this.readSidecar(absPath);
    return meta.images?.[imageId] || null;
  }

  async deleteImagePosition(kb: string, folderPath: string, imageId: string): Promise<boolean> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return false;

    const meta = await this.readSidecar(absPath);
    if (!meta.images || !meta.images[imageId]) return false;

    delete meta.images[imageId];
    await this.writeSidecar(absPath, meta);
    return true;
  }

  // === Private ===

  /**
   * Resolve a KB name + relative folder path to an absolute filesystem path.
   * Returns null if the path doesn't exist or is invalid.
   */
  private async resolveFolder(kb: string, folderPath: string): Promise<string | null> {
    const kbRoot = await kbService.resolveKbPath(kb);
    if (!kbRoot) return null;

    // Normalize and validate the path (prevent traversal)
    const normalized = path.normalize(folderPath);
    if (normalized.startsWith('..') || path.isAbsolute(normalized)) {
      return null;
    }

    const absPath = folderPath ? path.join(kbRoot, normalized) : kbRoot;

    // Ensure the resolved path is still within the KB
    if (!absPath.startsWith(kbRoot)) {
      return null;
    }

    try {
      const stat = await fs.stat(absPath);
      if (!stat.isDirectory()) return null;
      return absPath;
    } catch {
      return null;
    }
  }

  private async readSidecar(absPath: string): Promise<WebSidecar> {
    try {
      const sidecarPath = path.join(absPath, SIDECAR_FILENAME);
      const content = await fs.readFile(sidecarPath, 'utf-8');
      return WebSidecarSchema.parse(JSON.parse(content));
    } catch {
      // No sidecar or invalid — return defaults
      return WebSidecarSchema.parse({});
    }
  }

  private async writeSidecar(absPath: string, data: WebSidecar): Promise<void> {
    const sidecarPath = path.join(absPath, SIDECAR_FILENAME);

    // Backup existing sidecar before overwriting (keep last 3)
    try {
      await fs.access(sidecarPath);
      const backupName = `.adjutant-web.json.backup-${Date.now()}`;
      await fs.copyFile(sidecarPath, path.join(absPath, backupName));

      const files = await fs.readdir(absPath);
      const backups = files
        .filter(f => f.startsWith('.adjutant-web.json.backup-'))
        .sort()
        .reverse();

      for (const old of backups.slice(3)) {
        await fs.unlink(path.join(absPath, old)).catch(() => {});
      }
    } catch {
      // No existing sidecar to back up — first write
    }

    // Atomic-ish write: write to unique temp, then rename
    const tmpPath = sidecarPath + `.tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await fs.writeFile(tmpPath, JSON.stringify(data, null, 2), 'utf-8');
    await fs.rename(tmpPath, sidecarPath);
  }
}

export const folderService = new FolderService();
