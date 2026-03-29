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
