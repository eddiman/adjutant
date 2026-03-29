import fs from 'fs/promises';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { kbService } from './kbService.js';
import { WebSidecarSchema } from '../types/folder.js';
import type { WebSidecar, FolderEntry, FolderListing, RecursiveFolderEntry, RecursiveFolderListing } from '../types/folder.js';

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

  // === Recursive listing ===

  /**
   * Recursively list folder contents as a tree.
   * Each .md file includes a short content preview.
   * Each subfolder includes its own sidecar metadata.
   */
  async listRecursive(kb: string, folderPath: string = '', maxDepth: number = 3): Promise<RecursiveFolderListing | null> {
    const absPath = await this.resolveFolder(kb, folderPath);
    if (!absPath) return null;

    const entries = await this.readDirRecursive(absPath, '', maxDepth);
    const meta = await this.readSidecar(absPath);

    return { kb, path: folderPath, entries, meta };
  }

  private async readDirRecursive(absDir: string, relativeTo: string, depth: number): Promise<RecursiveFolderEntry[]> {
    if (depth < 0) return [];

    let dirEntries;
    try {
      dirEntries = await fs.readdir(absDir, { withFileTypes: true });
    } catch {
      return [];
    }

    const results: RecursiveFolderEntry[] = [];

    for (const entry of dirEntries) {
      if (entry.name.startsWith('.')) continue;

      const relPath = relativeTo ? `${relativeTo}/${entry.name}` : entry.name;
      const absEntry = path.join(absDir, entry.name);

      if (entry.isDirectory()) {
        const children = depth > 0
          ? await this.readDirRecursive(absEntry, relPath, depth - 1)
          : [];
        const dirMeta = await this.readSidecar(absEntry);

        results.push({
          name: entry.name,
          type: 'folder',
          relativePath: relPath,
          children,
          meta: dirMeta,
        });
      } else if (entry.isFile()) {
        const rec: RecursiveFolderEntry = {
          name: entry.name,
          type: 'file',
          relativePath: relPath,
        };

        try {
          const stat = await fs.stat(absEntry);
          rec.size = stat.size;
          rec.mtime = stat.mtime.toISOString();
        } catch { /* ignore */ }

        // Read preview for markdown files
        if (entry.name.endsWith('.md')) {
          rec.preview = await this.readPreview(absEntry);
        }

        results.push(rec);
      }
    }

    // Sort: folders first, then files, alphabetically within each group
    results.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });

    return results;
  }

  /**
   * Read the first ~200 characters of a markdown file for preview.
   * Strips leading heading markers and truncates at a word boundary.
   */
  private async readPreview(absPath: string): Promise<string> {
    try {
      const fd = await fs.open(absPath, 'r');
      try {
        const buf = Buffer.alloc(500);
        const { bytesRead } = await fd.read(buf, 0, 500, 0);
        let text = buf.toString('utf-8', 0, bytesRead);

        // Strip YAML frontmatter if present
        if (text.startsWith('---')) {
          const endIdx = text.indexOf('---', 3);
          if (endIdx !== -1) {
            text = text.slice(endIdx + 3).trimStart();
          }
        }

        // Strip leading heading markers (# Title)
        text = text.replace(/^#{1,6}\s+.*\n?/, '').trimStart();

        // Truncate to ~200 chars at word boundary
        if (text.length > 200) {
          const cutoff = text.lastIndexOf(' ', 200);
          text = text.slice(0, cutoff > 100 ? cutoff : 200) + '...';
        }

        return text.trim();
      } finally {
        await fd.close();
      }
    } catch {
      return '';
    }
  }

  // === Move entry ===

  /**
   * Move a file or folder from sourcePath to destPath within a KB.
   * Migrates sidecar metadata from the source directory to the destination.
   */
  async moveEntry(kb: string, sourcePath: string, destPath: string): Promise<{ newPath: string } | null> {
    const kbRoot = await kbService.resolveKbPath(kb);
    if (!kbRoot) return null;

    // Validate and resolve paths
    const normSource = path.normalize(sourcePath);
    const normDest = path.normalize(destPath);
    if (normSource.startsWith('..') || normDest.startsWith('..') ||
        path.isAbsolute(normSource) || path.isAbsolute(normDest)) {
      return null;
    }

    const absSrc = path.join(kbRoot, normSource);
    const absDst = path.join(kbRoot, normDest);

    // Ensure both are within the KB
    if (!absSrc.startsWith(kbRoot) || !absDst.startsWith(kbRoot)) {
      return null;
    }

    // Ensure source exists
    try {
      await fs.access(absSrc);
    } catch {
      return null;
    }

    // Ensure destination directory exists
    const destDir = path.dirname(absDst);
    try {
      await fs.mkdir(destDir, { recursive: true });
    } catch { /* ignore if exists */ }

    // Move the file/folder
    await fs.rename(absSrc, absDst);

    // Migrate sidecar metadata
    const srcDir = path.dirname(absSrc);
    const srcName = path.basename(absSrc);
    const dstName = path.basename(absDst);

    try {
      // Remove from source sidecar
      const srcMeta = await this.readSidecar(srcDir);
      const itemMeta = srcMeta.items[srcName];
      if (itemMeta) {
        delete srcMeta.items[srcName];
        await this.writeSidecar(srcDir, srcMeta);
      }

      // Add to destination sidecar (preserve position if same name, clear if different dir)
      const dstMeta = await this.readSidecar(destDir);
      if (itemMeta) {
        // Clear section reference since it may not apply in the new location
        const { section: _, ...rest } = itemMeta;
        dstMeta.items[dstName] = rest;
        await this.writeSidecar(destDir, dstMeta);
      }
    } catch {
      // Sidecar migration is best-effort; the file move already succeeded
    }

    return { newPath: normDest };
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
