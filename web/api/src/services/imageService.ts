import fs from 'fs/promises';
import path from 'path';
import sharp from 'sharp';
import { v4 as uuidv4 } from 'uuid';
import { kbService } from './kbService.js';

export interface ImageMetadata {
  id: string;
  webpUrl: string;
  thumbUrl: string;
  width: number;
  height: number;
  aspectRatio: number;
  kb: string;
}

interface ProcessedImage {
  id: string;
  webpPath: string;
  thumbPath: string;
  width: number;
  height: number;
}

class ImageService {
  /**
   * Resolve the assets directory for a given KB.
   * Assets are stored in <kb-root>/.adjutant-web/assets/
   */
  private async resolveAssetsDir(kb: string): Promise<string | null> {
    const kbRoot = await kbService.resolveKbPath(kb);
    if (!kbRoot) return null;

    const assetsDir = path.join(kbRoot, '.adjutant-web', 'assets');
    await fs.mkdir(assetsDir, { recursive: true });
    return assetsDir;
  }

  async processAndSave(buffer: Buffer, _originalName: string, kb: string): Promise<(ProcessedImage & { kb: string }) | null> {
    const assetsDir = await this.resolveAssetsDir(kb);
    if (!assetsDir) return null;

    const id = uuidv4();
    const metadata = await sharp(buffer).metadata();
    const width = metadata.width || 800;
    const height = metadata.height || 600;

    const webpPath = path.join(assetsDir, `${id}.webp`);
    const thumbPath = path.join(assetsDir, `${id}-thumb.webp`);

    await sharp(buffer)
      .webp({ quality: 80 })
      .toFile(webpPath);

    await sharp(buffer)
      .resize(300, null, { withoutEnlargement: true })
      .webp({ quality: 75 })
      .toFile(thumbPath);

    return { id, webpPath, thumbPath, width, height, kb };
  }

  getUrls(id: string, kb: string): { webpUrl: string; thumbUrl: string } {
    return {
      webpUrl: `/api/assets/${id}.webp?kb=${encodeURIComponent(kb)}`,
      thumbUrl: `/api/assets/${id}-thumb.webp?kb=${encodeURIComponent(kb)}`,
    };
  }

  async get(filename: string, kb: string): Promise<{ buffer: Buffer; contentType: string } | null> {
    const assetsDir = await this.resolveAssetsDir(kb);
    if (!assetsDir) return null;

    // Prevent path traversal in filename
    const base = path.basename(filename);
    const filePath = path.join(assetsDir, base);

    try {
      const buffer = await fs.readFile(filePath);
      return {
        buffer,
        contentType: 'image/webp',
      };
    } catch {
      return null;
    }
  }

  async delete(id: string, kb: string): Promise<boolean> {
    const assetsDir = await this.resolveAssetsDir(kb);
    if (!assetsDir) return false;

    try {
      const files = await fs.readdir(assetsDir);
      const matchingFiles = files.filter(f => f.startsWith(id));

      if (matchingFiles.length === 0) return false;

      for (const file of matchingFiles) {
        await fs.unlink(path.join(assetsDir, file));
      }
      return true;
    } catch {
      return false;
    }
  }

  async list(kb: string): Promise<ImageMetadata[]> {
    const assetsDir = await this.resolveAssetsDir(kb);
    if (!assetsDir) return [];

    try {
      const files = await fs.readdir(assetsDir);
      const idSet = new Set<string>();

      for (const file of files) {
        const match = file.match(/^([a-f0-9-]{36})\.webp$/);
        if (match) idSet.add(match[1]);
      }

      const images: ImageMetadata[] = [];
      for (const id of idSet) {
        const webpPath = path.join(assetsDir, `${id}.webp`);
        try {
          const metadata = await sharp(webpPath).metadata();
          const width = metadata.width || 800;
          const height = metadata.height || 600;

          images.push({
            id,
            ...this.getUrls(id, kb),
            width,
            height,
            aspectRatio: width / height,
            kb,
          });
        } catch {
          // Skip unreadable images
        }
      }

      return images;
    } catch {
      return [];
    }
  }
}

export const imageService = new ImageService();
