// Shared TypeScript interfaces for the web app

// === Canvas tool modes ===

export type CanvasTool = 'pan' | 'select';

// === Position ===

export interface Position {
  x: number;
  y: number;
}

// === App Config ===

export interface AppConfig {
  kbRoot?: string;
}

// === Knowledge Base ===

export interface KbMeta {
  name: string;
  description: string;
  path: string;
  access: 'read-only' | 'read-write';
  created?: string;
}

export interface KbsResponse {
  kbs: KbMeta[];
  total: number;
}

// === Folder ===

export interface FolderEntry {
  name: string;
  type: 'file' | 'folder';
  size?: number;
  mtime?: string;
}

export interface ItemMeta {
  position?: Position;
  tags?: string[];
  title?: string;
  section?: string;
}

export interface ImageMeta {
  position?: Position;
  width?: number;
  height?: number;
}

export interface WebSidecar {
  items: Record<string, ItemMeta>;
  sections: Record<string, SectionData>;
  stickies: Record<string, StickyData>;
  images: Record<string, ImageMeta>;
  nextSectionId?: number; // Deprecated
  nextStickyId?: number;  // Deprecated
}

export interface FolderListing {
  kb: string;
  path: string;
  entries: FolderEntry[];
  meta: WebSidecar;
}

// === Note (read-only .md file) ===

export interface NoteFile {
  filename: string;
  path: string;
  kb: string;
  content: string;
  title: string;
  tags: string[];
  position?: Position;
  section?: string;
  preview?: string;
  dirPath?: string;
  size: number;
  mtime: string;
}

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

export interface NotesSearchResponse {
  notes: NoteMeta[];
  total: number;
}

// === Section (stored in .adjutant-web.json) ===

export interface SectionData {
  name: string;
  position?: Position;
  width: number;
  height: number;
  color?: string;
  dirPath?: string;
  createdAt: string;
  updatedAt: string;
}

// For use with canvas nodes (has an ID)
export interface Section {
  id: string;
  name: string;
  width: number;
  height: number;
  color?: string;
  dirPath?: string;
  position?: Position;
  createdAt: string;
  updatedAt: string;
}

// === Sticky (stored in .adjutant-web.json) ===

export type StickyColor = 'white' | 'yellow' | 'pink' | 'blue' | 'green' | 'purple' | 'orange' | 'mint' | 'peach';

export interface StickyData {
  text: string;
  color: StickyColor;
  position?: Position;
  createdAt: string;
  updatedAt: string;
}

// For use with canvas nodes (has an ID)
export interface Sticky {
  id: string;
  text: string;
  color: StickyColor;
  position?: Position;
  createdAt: string;
  updatedAt: string;
}

// === Image ===

export interface CanvasImage {
  id: string;
  webpUrl: string;
  thumbUrl: string;
  width: number;
  height: number;
  aspectRatio: number;
  kb: string;
  position?: Position;
  displayWidth?: number;
  displayHeight?: number;
  status?: 'uploading' | 'ready' | 'error';
  errorMessage?: string;
}

export interface ImagesResponse {
  images: CanvasImage[];
  total: number;
}

// === Settings ===

export type Theme = 'default' | 'bauhaus';

export interface Settings {
  theme: Theme;
  snapToObject: boolean;
  showSnapLines: boolean;
  kbRoot?: string;
}

// === Explorer (server-side folder browsing) ===

export interface DirectoryEntry {
  name: string;
  path: string;
  hasChildren: boolean;
}

export interface ExplorerRoots {
  roots: { path: string; label: string }[];
  home: string;
  current?: string;
}

export interface KbRootValidation {
  valid: boolean;
  kbCount: number;
  kbNames: string[];
}

// === Recursive folder types ===

export interface RecursiveFolderEntry extends FolderEntry {
  relativePath: string;
  preview?: string;
  children?: RecursiveFolderEntry[];
  meta?: WebSidecar;
}

export interface RecursiveFolderListing {
  kb: string;
  path: string;
  entries: RecursiveFolderEntry[];
  meta: WebSidecar;
}
