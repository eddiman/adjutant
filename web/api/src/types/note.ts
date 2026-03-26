import { z } from 'zod';
import type { Position } from './folder.js';

// A note is a .md file within a KB
export interface NoteFile {
  filename: string;
  path: string;       // Relative path within KB (e.g. "data/current.md")
  kb: string;
  content: string;
  title: string;
  tags: string[];
  position?: Position;
  section?: string;
  size: number;
  mtime: string;
}

// Lightweight note info (no content) for listings and search results
export interface NoteMeta {
  filename: string;
  path: string;
  kb: string;
  title: string;
  tags: string[];
  position?: Position;
  section?: string;
  size: number;
  mtime: string;
}

// Input for creating a new note
export const NoteCreateSchema = z.object({
  kb: z.string().min(1),
  folder: z.string().default(''),           // Relative folder path within KB
  filename: z.string().optional(),           // Optional — auto-generated if omitted
  title: z.string().min(1, 'Title is required'),
  content: z.string().default(''),
  tags: z.array(z.string()).default([]),
  position: z.object({ x: z.number(), y: z.number() }).optional(),
});

export type NoteCreateInput = z.infer<typeof NoteCreateSchema>;

// Input for updating a note
export const NoteUpdateSchema = z.object({
  content: z.string().optional(),
  title: z.string().optional(),
  tags: z.array(z.string()).optional(),
  position: z.object({ x: z.number(), y: z.number() }).optional(),
  section: z.string().nullable().optional(),
});

export type NoteUpdateInput = z.infer<typeof NoteUpdateSchema>;
