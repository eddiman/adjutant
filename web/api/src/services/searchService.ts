/**
 * Search service with in-memory Fuse.js index.
 *
 * Builds a search index from all .md files in a KB on first query,
 * then uses fuzzy matching for fast results. Index is rebuilt when
 * notes are created, updated, or deleted (via invalidation).
 *
 * Performance targets:
 * - Index build: < 200ms for 1000 notes
 * - Search: < 10ms regardless of KB size
 */

import fs from 'fs/promises';
import path from 'path';
import Fuse from 'fuse.js';
import { kbService } from './kbService.js';
import { folderService } from './folderService.js';
import type { NoteMeta } from '../types/note.js';

interface IndexEntry {
  filename: string;
  path: string;
  kb: string;
  title: string;
  tags: string[];
  content: string;
  size: number;
  mtime: string;
}

const HEADING_REGEX = /^#\s+(.+)$/m;

class SearchService {
  private indices = new Map<string, {
    fuse: Fuse<IndexEntry>;
    builtAt: number;
  }>();

  // Index TTL: rebuild if older than 60 seconds
  private readonly INDEX_TTL_MS = 60_000;

  /**
   * Search a KB with fuzzy matching.
   * Builds/refreshes index automatically.
   */
  async search(kb: string, query: string, limit = 50): Promise<NoteMeta[]> {
    const fuse = await this.getOrBuildIndex(kb);
    if (!fuse) return [];

    const results = fuse.search(query, { limit });

    return results.map(r => ({
      filename: r.item.filename,
      path: r.item.path,
      kb: r.item.kb,
      title: r.item.title,
      tags: r.item.tags,
      size: r.item.size,
      mtime: r.item.mtime,
    }));
  }

  /**
   * Invalidate the index for a KB (call after note create/update/delete).
   */
  invalidate(kb: string): void {
    this.indices.delete(kb);
  }

  /**
   * Invalidate all indices.
   */
  invalidateAll(): void {
    this.indices.clear();
  }

  // === Private ===

  private async getOrBuildIndex(kb: string): Promise<Fuse<IndexEntry> | null> {
    const cached = this.indices.get(kb);
    const now = Date.now();

    if (cached && (now - cached.builtAt) < this.INDEX_TTL_MS) {
      return cached.fuse;
    }

    const entries = await this.buildEntries(kb);
    if (!entries) return null;

    const fuse = new Fuse(entries, {
      keys: [
        { name: 'title', weight: 3 },
        { name: 'filename', weight: 2 },
        { name: 'tags', weight: 2 },
        { name: 'content', weight: 1 },
      ],
      threshold: 0.4,
      includeScore: true,
      minMatchCharLength: 2,
    });

    this.indices.set(kb, { fuse, builtAt: now });
    return fuse;
  }

  private async buildEntries(kb: string): Promise<IndexEntry[] | null> {
    const kbRoot = await kbService.resolveKbPath(kb);
    if (!kbRoot) return null;

    const entries: IndexEntry[] = [];
    await this.scanDirectory(kbRoot, kbRoot, kb, entries);
    return entries;
  }

  private async scanDirectory(
    rootPath: string,
    dirPath: string,
    kb: string,
    entries: IndexEntry[],
  ): Promise<void> {
    try {
      const dirEntries = await fs.readdir(dirPath, { withFileTypes: true });
      const folderPath = path.relative(rootPath, dirPath);
      const meta = await folderService.getMeta(kb, folderPath);

      for (const entry of dirEntries) {
        if (entry.name.startsWith('.')) continue;

        const entryPath = path.join(dirPath, entry.name);

        if (entry.isDirectory()) {
          await this.scanDirectory(rootPath, entryPath, kb, entries);
        } else if (entry.isFile() && entry.name.endsWith('.md')) {
          try {
            const content = await fs.readFile(entryPath, 'utf-8');
            const stat = await fs.stat(entryPath);
            const itemMeta = meta?.items[entry.name] || {};

            const titleMatch = content.match(HEADING_REGEX);
            const title = itemMeta.title
              || (titleMatch ? titleMatch[1].trim() : '')
              || path.basename(entry.name, '.md');

            entries.push({
              filename: entry.name,
              path: path.relative(rootPath, entryPath),
              kb,
              title,
              tags: itemMeta.tags || [],
              content: content.slice(0, 2000), // Index first 2000 chars for memory efficiency
              size: stat.size,
              mtime: stat.mtime.toISOString(),
            });
          } catch {
            // Skip unreadable files
          }
        }
      }
    } catch {
      // Skip unreadable directories
    }
  }
}

export const searchService = new SearchService();
