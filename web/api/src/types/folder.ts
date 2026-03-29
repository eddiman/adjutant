import { z } from 'zod';

// === Position ===

export const PositionSchema = z.object({
  x: z.number(),
  y: z.number(),
});

export interface Position {
  x: number;
  y: number;
}

// === Sticky colors ===

export const StickyColors = [
  'white', 'yellow', 'pink', 'blue', 'green',
  'purple', 'orange', 'mint', 'peach',
] as const;
export type StickyColor = typeof StickyColors[number];

// === Item metadata (per file or subfolder in .adjutant-web.json) ===

export const ItemMetaSchema = z.object({
  position: PositionSchema.optional(),
  tags: z.array(z.string()).optional(),
  title: z.string().optional(),
  section: z.string().optional(),
});

export interface ItemMeta {
  position?: Position;
  tags?: string[];
  title?: string;
  section?: string;
}

// === Section (stored in .adjutant-web.json) ===

export const SectionSchema = z.object({
  name: z.string().default('Section'),
  position: PositionSchema.optional(),
  width: z.number().default(500),
  height: z.number().default(400),
  color: z.string().optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export interface SectionData {
  name: string;
  position?: Position;
  width: number;
  height: number;
  color?: string;
  createdAt: string;
  updatedAt: string;
}

// === Sticky (stored in .adjutant-web.json) ===

export const StickySchema = z.object({
  text: z.string().default(''),
  color: z.enum(StickyColors).default('yellow'),
  position: PositionSchema.optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export interface StickyData {
  text: string;
  color: StickyColor;
  position?: Position;
  createdAt: string;
  updatedAt: string;
}

// === Image metadata (stored in .adjutant-web.json) ===

export const ImageMetaSchema = z.object({
  position: PositionSchema.optional(),
  width: z.number().optional(),
  height: z.number().optional(),
});

export interface ImageMeta {
  position?: Position;
  width?: number;
  height?: number;
}

// === .adjutant-web.json root schema ===

export const WebSidecarSchema = z.object({
  items: z.record(z.string(), ItemMetaSchema).default({}),
  sections: z.record(z.string(), SectionSchema).default({}),
  stickies: z.record(z.string(), StickySchema).default({}),
  images: z.record(z.string(), ImageMetaSchema).default({}),
  nextSectionId: z.number().optional(), // Deprecated - kept for backward compatibility
  nextStickyId: z.number().optional(),  // Deprecated - kept for backward compatibility
});

export interface WebSidecar {
  items: Record<string, ItemMeta>;
  sections: Record<string, SectionData>;
  stickies: Record<string, StickyData>;
  images: Record<string, ImageMeta>;
  nextSectionId?: number; // Deprecated - kept for backward compatibility
  nextStickyId?: number;  // Deprecated - kept for backward compatibility
}

// === Folder entry (returned by folder listing) ===

export interface FolderEntry {
  name: string;
  type: 'file' | 'folder';
  size?: number;
  mtime?: string;
}

// === Folder listing response ===

export interface FolderListing {
  kb: string;
  path: string;
  entries: FolderEntry[];
  meta: WebSidecar;
}

// === Recursive folder entry (for tree listing) ===

export interface RecursiveFolderEntry extends FolderEntry {
  relativePath: string;
  preview?: string;
  children?: RecursiveFolderEntry[];
  meta?: WebSidecar;
}

// === Recursive folder listing response ===

export interface RecursiveFolderListing {
  kb: string;
  path: string;
  entries: RecursiveFolderEntry[];
  meta: WebSidecar;
}
