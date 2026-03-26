import fs from 'fs/promises';
import path from 'path';
import { kbService } from './kbService.js';
import { folderService } from './folderService.js';
import { NoteCreateSchema } from '../types/note.js';
import type { NoteFile, NoteMeta, NoteUpdateInput } from '../types/note.js';

// Match first # heading in markdown content
const HEADING_REGEX = /^#\s+(.+)$/m;

class FileNoteService {
  /**
   * Create a new note (.md file) within a KB.
   * Accepts partial input — defaults are applied via Zod schema.
   */
  async create(rawInput: { kb: string; title: string; content?: string; folder?: string; filename?: string; tags?: string[]; position?: { x: number; y: number } }): Promise<NoteFile | null> {
    const input = NoteCreateSchema.parse(rawInput);
    const kbRoot = await kbService.resolveKbPath(input.kb);
    if (!kbRoot) return null;

    const folderPath = input.folder || '';
    const normalized = path.normalize(folderPath);
    if (normalized.startsWith('..') || path.isAbsolute(normalized)) return null;

    const absFolderPath = folderPath ? path.join(kbRoot, normalized) : kbRoot;
    if (!absFolderPath.startsWith(kbRoot)) return null;

    // Ensure folder exists
    await fs.mkdir(absFolderPath, { recursive: true });

    // Generate filename from title if not provided
    const filename = input.filename || this.slugify(input.title) + '.md';

    // Ensure unique filename
    const uniqueFilename = await this.ensureUniqueFilename(absFolderPath, filename);
    const absFilePath = path.join(absFolderPath, uniqueFilename);

    // Build markdown content: prepend # title if content doesn't already start with one
    let content = input.content;
    if (!content || !content.trimStart().startsWith('# ')) {
      content = `# ${input.title}\n\n${content || ''}`;
    }

    await fs.writeFile(absFilePath, content, 'utf-8');

    // Write metadata to .adjutant-web.json
    const itemMeta: Record<string, unknown> = {};
    if (input.tags && input.tags.length > 0) itemMeta.tags = input.tags;
    if (input.position) itemMeta.position = input.position;
    if (input.title) itemMeta.title = input.title;

    if (Object.keys(itemMeta).length > 0) {
      await folderService.updateMeta(input.kb, folderPath, {
        items: { [uniqueFilename]: itemMeta },
      });
    }

    const stat = await fs.stat(absFilePath);
    const relativePath = path.relative(kbRoot, absFilePath);

    return {
      filename: uniqueFilename,
      path: relativePath,
      kb: input.kb,
      content,
      title: input.title,
      tags: input.tags || [],
      position: input.position,
      size: stat.size,
      mtime: stat.mtime.toISOString(),
    };
  }

  /**
   * Update an existing note's content and/or metadata.
   */
  async update(kb: string, filePath: string, input: NoteUpdateInput): Promise<NoteFile | null> {
    const kbRoot = await kbService.resolveKbPath(kb);
    if (!kbRoot) return null;

    const normalized = path.normalize(filePath);
    if (normalized.startsWith('..') || path.isAbsolute(normalized)) return null;

    const absPath = path.join(kbRoot, normalized);
    if (!absPath.startsWith(kbRoot)) return null;

    try {
      await fs.access(absPath);
    } catch {
      return null;
    }

    // Update file content if provided
    if (input.content !== undefined) {
      await fs.writeFile(absPath, input.content, 'utf-8');
    }

    // Update metadata in .adjutant-web.json
    const filename = path.basename(absPath);
    const folderPathRel = path.relative(kbRoot, path.dirname(absPath));
    const metaUpdates: Record<string, unknown> = {};

    if (input.title !== undefined) metaUpdates.title = input.title;
    if (input.tags !== undefined) metaUpdates.tags = input.tags;
    if (input.position !== undefined) metaUpdates.position = input.position;
    if (input.section !== undefined) metaUpdates.section = input.section === null ? undefined : input.section;

    if (Object.keys(metaUpdates).length > 0) {
      await folderService.updateMeta(kb, folderPathRel, {
        items: { [filename]: metaUpdates },
      });
    }

    // Return the updated note
    return this.get(kb, filePath);
  }

  /**
   * Delete a note (.md file) and its metadata.
   */
  async delete(kb: string, filePath: string): Promise<boolean> {
    const kbRoot = await kbService.resolveKbPath(kb);
    if (!kbRoot) return false;

    const normalized = path.normalize(filePath);
    if (normalized.startsWith('..') || path.isAbsolute(normalized)) return false;

    const absPath = path.join(kbRoot, normalized);
    if (!absPath.startsWith(kbRoot)) return false;

    try {
      await fs.unlink(absPath);

      // Remove metadata from .adjutant-web.json
      const filename = path.basename(absPath);
      const folderPathRel = path.relative(kbRoot, path.dirname(absPath));
      await folderService.removeItemMeta(kb, folderPathRel, filename);

      return true;
    } catch {
      return false;
    }
  }

  /**
   * Get a single note by KB name and file path (relative to KB root).
   */
  async get(kb: string, filePath: string): Promise<NoteFile | null> {
    const kbRoot = await kbService.resolveKbPath(kb);
    if (!kbRoot) return null;

    // Validate path
    const normalized = path.normalize(filePath);
    if (normalized.startsWith('..') || path.isAbsolute(normalized)) {
      return null;
    }

    const absPath = path.join(kbRoot, normalized);
    if (!absPath.startsWith(kbRoot)) return null;

    try {
      const stat = await fs.stat(absPath);
      if (!stat.isFile()) return null;

      const content = await fs.readFile(absPath, 'utf-8');
      const filename = path.basename(absPath);
      const folderPath = path.relative(kbRoot, path.dirname(absPath));

      // Get metadata from .adjutant-web.json
      const meta = await folderService.getMeta(kb, folderPath);
      const itemMeta = meta?.items[filename] || {};

      return {
        filename,
        path: normalized,
        kb,
        content,
        title: itemMeta.title || this.extractTitle(content, filename),
        tags: itemMeta.tags || [],
        position: itemMeta.position,
        section: itemMeta.section,
        size: stat.size,
        mtime: stat.mtime.toISOString(),
      };
    } catch {
      return null;
    }
  }

  /**
   * Search for notes within a KB by text query.
   * Searches filenames and file contents.
   */
  async search(kb: string, query: string): Promise<NoteMeta[]> {
    const kbRoot = await kbService.resolveKbPath(kb);
    if (!kbRoot) return [];

    const results: NoteMeta[] = [];
    const queryLower = query.toLowerCase();

    await this.searchRecursive(kbRoot, kbRoot, kb, queryLower, results);

    return results;
  }

  /**
   * Extract a title from markdown content.
   * Uses first # heading, falls back to filename sans extension.
   */
  extractTitle(content: string, filename: string): string {
    const match = content.match(HEADING_REGEX);
    if (match) return match[1].trim();
    return path.basename(filename, path.extname(filename));
  }

  // === Helpers ===

  /**
   * Convert a title to a filename-safe slug.
   */
  slugify(title: string): string {
    return title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 80) || 'untitled';
  }

  /**
   * Ensure a filename is unique within a directory.
   * Appends -2, -3, etc. if needed.
   * Uses O_EXCL flag for atomic check-and-create to prevent race conditions.
   */
  private async ensureUniqueFilename(dirPath: string, filename: string): Promise<string> {
    const ext = path.extname(filename);
    const base = path.basename(filename, ext);
    let candidate = filename;
    let counter = 2;

    while (true) {
      const candidatePath = path.join(dirPath, candidate);
      try {
        // wx = write + fail if exists (O_CREAT | O_EXCL) — atomic
        const handle = await fs.open(candidatePath, 'wx');
        await handle.close();
        // We created an empty placeholder — caller will overwrite with real content
        return candidate;
      } catch (err: unknown) {
        const code = (err as NodeJS.ErrnoException).code;
        if (code === 'EEXIST') {
          candidate = `${base}-${counter}${ext}`;
          counter++;
        } else {
          throw err;
        }
      }
    }
  }

  // === Private ===

  private async searchRecursive(
    kbRoot: string,
    dirPath: string,
    kb: string,
    query: string,
    results: NoteMeta[],
  ): Promise<void> {
    try {
      const entries = await fs.readdir(dirPath, { withFileTypes: true });
      const folderPath = path.relative(kbRoot, dirPath);
      const meta = await folderService.getMeta(kb, folderPath);

      for (const entry of entries) {
        if (entry.name.startsWith('.')) continue;

        const entryPath = path.join(dirPath, entry.name);

        if (entry.isDirectory()) {
          await this.searchRecursive(kbRoot, entryPath, kb, query, results);
        } else if (entry.isFile() && entry.name.endsWith('.md')) {
          const nameMatch = entry.name.toLowerCase().includes(query);

          let contentMatch = false;
          let content = '';
          if (!nameMatch) {
            try {
              content = await fs.readFile(entryPath, 'utf-8');
              contentMatch = content.toLowerCase().includes(query);
            } catch {
              // Can't read file, skip
              continue;
            }
          } else {
            try {
              content = await fs.readFile(entryPath, 'utf-8');
            } catch {
              content = '';
            }
          }

          if (nameMatch || contentMatch) {
            const stat = await fs.stat(entryPath);
            const itemMeta = meta?.items[entry.name] || {};
            const relativePath = path.relative(kbRoot, entryPath);

            results.push({
              filename: entry.name,
              path: relativePath,
              kb,
              title: itemMeta.title || this.extractTitle(content, entry.name),
              tags: itemMeta.tags || [],
              position: itemMeta.position,
              section: itemMeta.section,
              size: stat.size,
              mtime: stat.mtime.toISOString(),
            });
          }
        }
      }
    } catch {
      // Can't read directory, skip
    }
  }
}

export const fileNoteService = new FileNoteService();
