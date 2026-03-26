import type { Node } from '@xyflow/react';
import type { Position, Section } from '../types';

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
