import type { Node } from '@xyflow/react';
import type { Position, Section, RecursiveFolderEntry, WebSidecar } from '../types';

// Default sizes for different node types
const NOTE_WIDTH = 200;
const NOTE_HEIGHT = 283;
const NOTE_PADDING = 20; // Padding from section edges

interface NodeWithData {
  id: string;
  position: { x: number; y: number };
  type?: string;
  measured?: { width?: number; height?: number };
  data?: { width?: number; height?: number };
}

/**
 * Check if a node is inside a section's bounds (based on center point)
 */
export function isNodeInsideSection<T extends NodeWithData>(
  node: T,
  section: T | Section,
  sectionPosition?: Position
): boolean {
  // Get section bounds
  const sectionData = 'data' in section ? section.data : section;
  const sectionWidth = (sectionData as { width?: number })?.width || 300;
  const sectionHeight = (sectionData as { height?: number })?.height || 200;
  
  // Handle position - can come from sectionPosition param, section.position (Node), or section itself (Section)
  let sectionX = 0;
  let sectionY = 0;
  if (sectionPosition) {
    sectionX = sectionPosition.x;
    sectionY = sectionPosition.y;
  } else if ('position' in section && section.position) {
    sectionX = section.position.x;
    sectionY = section.position.y;
  }

  // Get node dimensions
  const nodeWidth = node.measured?.width ?? NOTE_WIDTH;
  const nodeHeight = node.measured?.height ?? NOTE_HEIGHT;

  // Check if node center is inside section bounds
  const nodeCenterX = node.position.x + nodeWidth / 2;
  const nodeCenterY = node.position.y + nodeHeight / 2;

  return (
    nodeCenterX >= sectionX &&
    nodeCenterX <= sectionX + sectionWidth &&
    nodeCenterY >= sectionY &&
    nodeCenterY <= sectionY + sectionHeight
  );
}

/**
 * Find a free position inside a section for placing a note
 * Uses a simple grid-based approach, scanning for empty spots
 */
export function findFreePositionInSection(
  section: Section,
  existingNodes: Node[],
  nodeWidth: number = NOTE_WIDTH,
  nodeHeight: number = NOTE_HEIGHT
): Position {
  const sectionX = section.position?.x ?? 0;
  const sectionY = section.position?.y ?? 0;
  const sectionWidth = section.width || 300;
  const sectionHeight = section.height || 200;

  // Start from top-left with padding
  const startX = sectionX + NOTE_PADDING;
  const startY = sectionY + NOTE_PADDING;
  const maxX = sectionX + sectionWidth - nodeWidth - NOTE_PADDING;
  const maxY = sectionY + sectionHeight - nodeHeight - NOTE_PADDING;

  // Get existing note positions that are inside this section
  const occupiedPositions = existingNodes
    .filter(n => n.type === 'note' && isNodeInsideSection(n, section, section.position))
    .map(n => ({
      x: n.position.x,
      y: n.position.y,
      width: n.measured?.width ?? NOTE_WIDTH,
      height: n.measured?.height ?? NOTE_HEIGHT,
    }));

  // Grid-based search for free position
  const gridStepX = nodeWidth + NOTE_PADDING;
  const gridStepY = nodeHeight + NOTE_PADDING;

  for (let y = startY; y <= maxY; y += gridStepY) {
    for (let x = startX; x <= maxX; x += gridStepX) {
      const overlaps = occupiedPositions.some(pos => 
        x < pos.x + pos.width &&
        x + nodeWidth > pos.x &&
        y < pos.y + pos.height &&
        y + nodeHeight > pos.y
      );

      if (!overlaps) {
        return { x, y };
      }
    }
  }

  // Fallback: place at top-left with padding (may overlap)
  return { x: startX, y: startY };
}

/**
 * Find a position outside all sections for a note
 * Searches to the right of the rightmost section, or below if that doesn't work
 */
export function findPositionOutsideSections(
  sections: Section[],
  existingNodes: Node[],
  nodeWidth: number = NOTE_WIDTH,
  nodeHeight: number = NOTE_HEIGHT
): Position {
  if (sections.length === 0) {
    // No sections, use default position
    return { x: 100, y: 100 };
  }

  // Find the bounds of all sections
  let maxX = 0;
  let maxY = 0;

  for (const section of sections) {
    const sectionRight = (section.position?.x ?? 0) + (section.width || 300);
    const sectionBottom = (section.position?.y ?? 0) + (section.height || 200);
    maxX = Math.max(maxX, sectionRight);
    maxY = Math.max(maxY, sectionBottom);
  }

  // Try placing to the right of all sections
  const candidateX = maxX + NOTE_PADDING * 2;
  const candidateY = 100;

  // Check if this position overlaps with any existing node
  const overlapsExisting = existingNodes.some(n => {
    const nWidth = n.measured?.width ?? NOTE_WIDTH;
    const nHeight = n.measured?.height ?? NOTE_HEIGHT;
    return (
      candidateX < n.position.x + nWidth &&
      candidateX + nodeWidth > n.position.x &&
      candidateY < n.position.y + nHeight &&
      candidateY + nodeHeight > n.position.y
    );
  });

  if (!overlapsExisting) {
    return { x: candidateX, y: candidateY };
  }

  // Fallback: place below all sections
  return { x: 100, y: maxY + NOTE_PADDING * 2 };
}

/**
 * Get the section slug that a node is currently inside (if any)
 */
export function getSectionContainingNode(
  node: NodeWithData,
  sections: Section[]
): string | undefined {
  for (const section of sections) {
    if (isNodeInsideSection(node, section, section.position)) {
      return section.id;
    }
  }
  return undefined;
}

/**
 * Comprehensive function to manage note-section associations
 * Returns notes that should be added to or removed from a section
 */
export function getNotesForSectionUpdate(
  section: Section,
  nodes: Node[]
): {
  notesToAdd: string[];
  notesToRemove: string[];
} {
  const notesToAdd: string[] = [];
  const notesToRemove: string[] = [];

  for (const node of nodes) {
    if (node.type !== 'note') continue;

    const noteData = node.data as { section?: string };
    const isCurrentlyInSection = noteData.section === section.id;
    const isInOtherSection = noteData.section && noteData.section !== section.id;

    // Skip notes that are in other sections (unless we're implementing section switching)
    if (isInOtherSection) continue;

    // Check if note is inside this section
    const isInsideSection = isNodeInsideSection(node, section, section.position);

    if (isInsideSection && !isCurrentlyInSection) {
      // Note is inside section but not currently associated - should be added
      notesToAdd.push(node.id);
    } else if (!isInsideSection && isCurrentlyInSection) {
      // Note is not inside section but is currently associated - should be removed
      notesToRemove.push(node.id);
    }
  }

  return { notesToAdd, notesToRemove };
}

/**
 * Find notes that would be inside a section at a given position
 */
export function findNotesInsideSectionBounds(
  sectionPosition: Position,
  sectionWidth: number,
  sectionHeight: number,
  notes: Node[]
): string[] {
  const noteSlugs: string[] = [];

  for (const note of notes) {
    if (note.type !== 'note') continue;

    // Check if note is already in another section
    const noteData = note.data as { section?: string };
    if (noteData.section) continue; // Skip notes already in sections

    // Get note dimensions
    const noteWidth = note.measured?.width ?? NOTE_WIDTH;
    const noteHeight = note.measured?.height ?? NOTE_HEIGHT;

    // Check if note center is inside the new section bounds
    const noteCenterX = note.position.x + noteWidth / 2;
    const noteCenterY = note.position.y + noteHeight / 2;

    const sectionX = sectionPosition.x;
    const sectionY = sectionPosition.y;

    const isInside = (
      noteCenterX >= sectionX &&
      noteCenterX <= sectionX + sectionWidth &&
      noteCenterY >= sectionY &&
      noteCenterY <= sectionY + sectionHeight
    );

    if (isInside) {
      noteSlugs.push(note.id);
    }
  }

  return noteSlugs;
}

// === Directory-section auto-layout ===

const SECTION_PADDING = 40;
const SECTION_LABEL_HEIGHT = 32;
const NOTE_GAP = 20;
const SECTION_GAP = 40;

interface DirSectionLayout {
  id: string;
  dirPath: string;
  name: string;
  position: Position;
  /** True if position is relative to parent section, false if absolute */
  positionIsRelative: boolean;
  width: number;
  height: number;
  notePositions: Map<string, Position>;
  childSections: DirSectionLayout[];
}

/**
 * Estimate how large a section needs to be for a given number of notes and child sections.
 */
function estimateSectionSize(
  noteCount: number,
  childSizes: { width: number; height: number }[],
): { width: number; height: number } {
  // Layout notes in a grid (3 columns)
  const cols = 3;
  const noteRows = Math.ceil(noteCount / cols);
  const notesWidth = cols * (NOTE_WIDTH + NOTE_GAP) - NOTE_GAP + SECTION_PADDING * 2;
  const notesHeight = noteRows * (NOTE_HEIGHT + NOTE_GAP) - (noteRows > 0 ? NOTE_GAP : 0);

  // Child sections laid out horizontally below the notes
  let childrenWidth = 0;
  let childrenHeight = 0;
  for (const cs of childSizes) {
    childrenWidth += cs.width + SECTION_GAP;
    childrenHeight = Math.max(childrenHeight, cs.height);
  }
  if (childSizes.length > 0) {
    childrenWidth -= SECTION_GAP; // remove trailing gap
  }

  const innerWidth = Math.max(notesWidth, childrenWidth + SECTION_PADDING * 2);
  const innerHeight =
    SECTION_LABEL_HEIGHT +
    (noteRows > 0 ? notesHeight + SECTION_PADDING : 0) +
    (childSizes.length > 0 ? childrenHeight + SECTION_PADDING : 0) +
    SECTION_PADDING;

  return {
    width: Math.max(innerWidth, 300),
    height: Math.max(innerHeight, 200),
  };
}

/**
 * Recursively build layout data for directory sections from a recursive folder tree.
 * Bottom-up: leaf directories are sized first, then parents.
 *
 * All positions in the layout tree are ABSOLUTE canvas coordinates.
 * The rootMeta parameter must always be the top-level sidecar (where all
 * dirsection-* entries are stored), regardless of nesting depth.
 */
export function layoutDirectoryTree(
  entries: RecursiveFolderEntry[],
  rootMeta: WebSidecar,
  kb: string,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _basePath: string,
): DirSectionLayout[] {
  const folders = entries.filter(e => e.type === 'folder');
  if (folders.length === 0) return [];

  const layouts: DirSectionLayout[] = [];

  for (const folder of folders) {
    const dirPath = folder.relativePath;
    const sectionId = `dirsection-${dirPath.replace(/\//g, '-')}`;

    // Always pass rootMeta (top-level sidecar) — all dirsection-* entries live there
    const childLayouts = folder.children
      ? layoutDirectoryTree(folder.children, rootMeta, kb, dirPath)
      : [];

    // Count notes in this folder
    const noteFiles = (folder.children || []).filter(
      e => e.type === 'file' && e.name.endsWith('.md'),
    );

    // Calculate size based on contents
    const childSizes = childLayouts.map(cl => ({ width: cl.width, height: cl.height }));
    const { width, height } = estimateSectionSize(noteFiles.length, childSizes);

    // Check saved position/size from root sidecar
    const savedSection = rootMeta.sections[sectionId];
    const finalWidth = savedSection?.width || width;
    const finalHeight = savedSection?.height || height;

    // Note positions are RELATIVE to their containing section
    const notePositions = new Map<string, Position>();
    const cols = 3;
    const notesStartX = SECTION_PADDING;
    const notesStartY = SECTION_LABEL_HEIGHT + SECTION_PADDING;

    for (let i = 0; i < noteFiles.length; i++) {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const noteKey = noteFiles[i].name;

      // Default grid position (relative to section)
      notePositions.set(noteKey, {
        x: notesStartX + col * (NOTE_WIDTH + NOTE_GAP),
        y: notesStartY + row * (NOTE_HEIGHT + NOTE_GAP),
      });
    }

    // Child section default positions (relative to parent section)
    const noteRows = Math.ceil(noteFiles.length / cols);
    const childStartY =
      SECTION_LABEL_HEIGHT +
      SECTION_PADDING +
      (noteRows > 0 ? noteRows * (NOTE_HEIGHT + NOTE_GAP) : 0);
    let childX = SECTION_PADDING;

    for (const child of childLayouts) {
      // Only assign default position if child doesn't have a saved absolute position
      if (!rootMeta.sections[child.id]?.position) {
        child.position = { x: childX, y: childStartY };
        child.positionIsRelative = true;
      }
      childX += child.width + SECTION_GAP;
    }

    layouts.push({
      id: sectionId,
      dirPath,
      name: folder.name,
      position: savedSection?.position || { x: 0, y: 0 },
      positionIsRelative: !savedSection?.position,
      width: finalWidth,
      height: finalHeight,
      notePositions,
      childSections: childLayouts,
    });
  }

  // Auto-position root-level sections that don't have saved positions
  let nextX = 100;
  const startY = 100;

  for (const layout of layouts) {
    if (layout.positionIsRelative) {
      layout.position = { x: nextX, y: startY };
      layout.positionIsRelative = false; // Now absolute
      nextX += layout.width + SECTION_GAP;
    }
  }

  // Resolve overlaps: sort by x, push any overlapping section to the right
  layouts.sort((a, b) => a.position.x - b.position.x);
  for (let i = 1; i < layouts.length; i++) {
    const prev = layouts[i - 1];
    const prevRight = prev.position.x + prev.width + SECTION_GAP;
    if (layouts[i].position.x < prevRight) {
      layouts[i].position = { x: prevRight, y: layouts[i].position.y };
    }
  }

  return layouts;
}

/**
 * Flatten a layout tree into arrays of sections and note positions
 * suitable for building React Flow nodes.
 *
 * Sections with saved absolute positions use them directly.
 * Sections with relative (layout-computed) positions are offset by the parent.
 * Note positions are always relative to their section and get converted to absolute.
 */
export function flattenDirLayouts(
  layouts: DirSectionLayout[],
  parentPosition?: Position,
): {
  sections: Array<{
    id: string;
    dirPath: string;
    name: string;
    position: Position;
    width: number;
    height: number;
  }>;
  notePositions: Map<string, Position>;
} {
  const sections: Array<{
    id: string;
    dirPath: string;
    name: string;
    position: Position;
    width: number;
    height: number;
  }> = [];
  const notePositions = new Map<string, Position>();

  for (const layout of layouts) {
    // If position is relative (layout-computed), offset by parent.
    // If position is absolute (saved), use as-is.
    let absPos: Position;
    if (layout.positionIsRelative && parentPosition) {
      absPos = {
        x: parentPosition.x + layout.position.x,
        y: parentPosition.y + layout.position.y,
      };
    } else {
      absPos = layout.position;
    }

    sections.push({
      id: layout.id,
      dirPath: layout.dirPath,
      name: layout.name,
      position: absPos,
      width: layout.width,
      height: layout.height,
    });

    // Note positions are always relative to section → convert to absolute
    for (const [noteKey, relPos] of layout.notePositions) {
      notePositions.set(
        `${layout.dirPath}/${noteKey}`,
        { x: absPos.x + relPos.x, y: absPos.y + relPos.y },
      );
    }

    // Recurse into children, passing this section's absolute position
    const childResult = flattenDirLayouts(layout.childSections, absPos);
    for (const s of childResult.sections) sections.push(s);
    for (const [k, v] of childResult.notePositions) notePositions.set(k, v);
  }

  return { sections, notePositions };
}
