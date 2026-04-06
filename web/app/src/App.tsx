import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import { Home } from './components/Home';
import { Sidebar } from './components/Sidebar';
import { Toolbar } from './components/Toolbar';
import { GhostSection } from './components/GhostSection';
import { GhostSticky } from './components/GhostSticky';
import { GhostNote } from './components/GhostNote';
import { PlacementHint } from './components/PlacementHint';
import { Canvas, type FocusOnNodeOptions } from './components/Canvas';
import { Dialog } from './components/Dialog';
import { ToolSwitcher } from './components/ToolSwitcher';
import { AdjutantDashboard } from './components/AdjutantDashboard';
import { ErrorBoundary } from './components/ErrorBoundary';

const NoteEditor = lazy(() => import('./components/NoteEditor/NoteEditor'));
const SettingsDialog = lazy(() => import('./components/SettingsDialog/SettingsDialog'));

import { useCanvas } from './hooks/useCanvas';
import { useKbs } from './hooks/useKbs';
import { useRecursiveFolder } from './hooks/useRecursiveFolder';
import { useNotes } from './hooks/useNotes';
import { useImages } from './hooks/useImages';
import { useSettings } from './hooks/useSettings';
import { useAdjutant } from './hooks/useAdjutant';
import { EditorProvider, useEditor, PlacementProvider, usePlacement } from './contexts';
import { isTouchDevice } from './utils/platform.js';
import type { Position, StickyColor, Section, CanvasTool } from './types';

function AppContent() {
  const location = useLocation();
  const isAdjutantPage = location.pathname === '/adjutant';

  const {
    currentKb,
    currentPath,
    focusedNote,
    setCurrentKb,
    navigateToFolder,
    setFocusedNote,
  } = useCanvas();

  const { kbs, loading: loadingKbs, refetch: refetchKbs } = useKbs();
  const { settings, updateSetting } = useSettings();
  const { getNote, createNote, updateNote, deleteNote, searchNotes, searching } = useNotes();
  const adjutantData = useAdjutant();

  // Apply theme
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', settings.theme);
  }, [settings.theme]);

  const { originRect, initialNoteForEditor, prepareEditorOpen, clearEditorState } = useEditor();
  const { isPlacementMode, placementType, exitPlacementMode, enterPlacementMode } = usePlacement();

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activeTool, setActiveTool] = useState<CanvasTool>('pan');
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    const saved = localStorage.getItem('adjutant-web-sidebar-open');
    return saved === 'true';
  });

  const handleSidebarToggle = useCallback(() => {
    setSidebarOpen(prev => {
      const next = !prev;
      localStorage.setItem('adjutant-web-sidebar-open', String(next));
      return next;
    });
  }, []);

  // Folder data for current view
  const folderOptions = useMemo(() => ({
    kb: currentKb,
    path: currentPath,
  }), [currentKb, currentPath]);

  // Recursive folder data for the canvas (includes subdirectories as sections)
  const {
    allNotes: canvasNotes,
    dirSections,
    manualSections,
    stickies,
    loading: loadingFolder,
    refetch: refetchFolder,
    updateItemPosition,
    updateSection,
    updateDirSectionPosition,
    updateDirSectionSize,
    createSection,
    deleteSection,
    createSticky,
    updateSticky,
    deleteSticky,
    moveEntry,
    rootEntries,
  } = useRecursiveFolder(folderOptions);

  // Merge directory sections + manual sections
  const allSections: Section[] = useMemo(() => {
    return [...dirSections, ...manualSections];
  }, [dirSections, manualSections]);

  const { images, uploadImage, updateImagePosition, updateImageSize, deleteImage } = useImages({ kb: currentKb, path: currentPath });

  // Move confirmation dialog state
  const [pendingMove, setPendingMove] = useState<{
    noteId: string;
    noteName: string;
    sourceDirPath: string;
    destDirPath: string;
    revertPosition: Position;
  } | null>(null);

  // Ref for Canvas focusOnNode function
  const focusOnNodeRef = useRef<((nodeId: string, options?: FocusOnNodeOptions) => void) | null>(null);
  // Ref for Canvas setNodePosition function (used for move revert)
  const setNodePositionRef = useRef<((nodeId: string, position: Position) => void) | null>(null);

  // === Note handlers ===

  const handleNoteOpen = useCallback(async (notePath: string, rect: { x: number; y: number; width: number; height: number }) => {
    if (!currentKb) return;
    const note = await getNote(currentKb, notePath);
    prepareEditorOpen(rect, note);
    setFocusedNote(notePath);
  }, [currentKb, getNote, prepareEditorOpen, setFocusedNote]);

  const handleNoteClose = useCallback(() => {
    setFocusedNote(null);
    clearEditorState();
    refetchFolder(); // Refresh canvas data to pick up title/content changes
  }, [setFocusedNote, clearEditorState, refetchFolder]);

  // === Position handlers ===

  const handleItemPositionChange = useCallback((itemName: string, position: Position, dirPath?: string) => {
    updateItemPosition(itemName, position, dirPath);
  }, [updateItemPosition]);

  const handleImagePositionChange = useCallback((id: string, position: Position) => {
    updateImagePosition(id, position);
  }, [updateImagePosition]);

  const handleImageResize = useCallback((id: string, width: number, height: number) => {
    updateImageSize(id, width, height);
  }, [updateImageSize]);

  const handleImagePaste = useCallback((file: File, position: Position) => {
    uploadImage(file, position);
  }, [uploadImage]);

  // === Section handlers ===

  const handleSectionCreate = useCallback(async (position: Position) => {
    await createSection({ position });
  }, [createSection]);

  const handleSectionPositionChange = useCallback((id: string, position: Position) => {
    if (id.startsWith('dirsection-')) {
      updateDirSectionPosition(id, position);
    } else {
      updateSection(id, { position });
    }
  }, [updateSection, updateDirSectionPosition]);

  const handleSectionResize = useCallback((id: string, width: number, height: number) => {
    if (id.startsWith('dirsection-')) {
      updateDirSectionSize(id, width, height);
    } else {
      updateSection(id, { width, height });
    }
  }, [updateSection, updateDirSectionSize]);

  const handleSectionRename = useCallback((id: string, name: string) => {
    updateSection(id, { name });
  }, [updateSection]);

  const handleSectionColorChange = useCallback((id: string, color: StickyColor) => {
    updateSection(id, { color });
  }, [updateSection]);

  const handleSectionsDelete = useCallback(async (ids: string[]) => {
    // Only delete manual sections, not directory-backed ones
    const manualIds = ids.filter(id => !id.startsWith('dirsection-'));
    await Promise.all(manualIds.map(id => deleteSection(id)));
  }, [deleteSection]);

  // === Sticky handlers ===

  const handleStickyCreate = useCallback(async (position: Position) => {
    await createSticky({ position });
  }, [createSticky]);

  const handleStickyPositionChange = useCallback((id: string, position: Position) => {
    updateSticky(id, { position });
  }, [updateSticky]);

  const handleStickyTextChange = useCallback((id: string, text: string) => {
    updateSticky(id, { text });
  }, [updateSticky]);

  const handleStickyColorChange = useCallback((id: string, color: StickyColor) => {
    updateSticky(id, { color });
  }, [updateSticky]);

  const handleStickiesDelete = useCallback(async (ids: string[]) => {
    await Promise.all(ids.map(id => deleteSticky(id)));
  }, [deleteSticky]);

  // === Image handlers ===

  const handleImagesDelete = useCallback(async (ids: string[]) => {
    await Promise.all(ids.map(id => deleteImage(id)));
  }, [deleteImage]);

  // === Note CRUD handlers ===

  const handleNoteCreate = useCallback(async (position: Position) => {
    if (!currentKb) return;

    // Determine target folder: if placing inside a directory section, use that folder
    let targetFolder = currentPath;
    for (const section of dirSections) {
      if (
        section.position &&
        position.x >= section.position.x &&
        position.y >= section.position.y &&
        position.x <= section.position.x + (section.width ?? 500) &&
        position.y <= section.position.y + (section.height ?? 400)
      ) {
        targetFolder = section.dirPath ? (currentPath ? `${currentPath}/${section.dirPath}` : section.dirPath) : currentPath;
      }
    }

    const note = await createNote({
      kb: currentKb,
      folder: targetFolder,
      title: 'Untitled Note',
      position,
    });
    if (note) {
      await refetchFolder();
      // Open the new note in the editor
      prepareEditorOpen(
        { x: window.innerWidth / 2 - 100, y: window.innerHeight / 2 - 141, width: 200, height: 283 },
        note,
      );
      setFocusedNote(note.path);
    }
  }, [currentKb, currentPath, dirSections, createNote, refetchFolder, prepareEditorOpen, setFocusedNote]);

  const handleNoteSave = useCallback(async (kb: string, notePath: string, content: string, title: string, tags: string[]) => {
    await updateNote(kb, notePath, { content, title, tags });
  }, [updateNote]);

  const handleNoteDelete = useCallback(async (kb: string, notePath: string) => {
    await deleteNote(kb, notePath);
    setFocusedNote(null);
    clearEditorState();
    refetchFolder();
  }, [deleteNote, setFocusedNote, clearEditorState, refetchFolder]);

  // === Placement handler ===

  const handlePlacementClick = useCallback(async (position: Position) => {
    if (!placementType) return;

    if (placementType === 'note') {
      exitPlacementMode();
      await handleNoteCreate(position);
    } else if (placementType === 'section') {
      exitPlacementMode();
      await createSection({ position });
    } else if (placementType === 'sticky') {
      exitPlacementMode();
      await createSticky({ position });
    }
  }, [placementType, exitPlacementMode, handleNoteCreate, createSection, createSticky]);

  // === Home page handler ===

  const handleHomeKbSelect = useCallback((kbName: string) => {
    setCurrentKb(kbName);
  }, [setCurrentKb]);

  const handleHomeNoteSelect = useCallback((note: { kb: string; path: string }) => {
    // Navigate to the KB and folder, then open the note
    const folderPath = note.path.split('/').slice(0, -1).join('/');
    navigateToFolder(note.kb, folderPath);
    setTimeout(() => {
      setFocusedNote(note.path);
    }, 100);
  }, [navigateToFolder, setFocusedNote]);

  // === Sidebar-Canvas sync state ===
  const [selectedDirPath, setSelectedDirPath] = useState<string | null>(null);
  const [focusOnSectionId, setFocusOnSectionId] = useState<string | null>(null);

  const handleFolderFocus = useCallback((folderRelativePath: string) => {
    // When clicking focus button in sidebar, pan to the corresponding section on canvas
    const dirPath = currentPath ? `${currentPath}/${folderRelativePath}` : folderRelativePath;
    const sectionId = `dirsection-${dirPath.replace(/\//g, '-')}`;
    setFocusOnSectionId(sectionId);
  }, [currentPath]);

  const handleSectionSelected = useCallback((sectionId: string | null) => {
    if (!sectionId) {
      setSelectedDirPath(null);
      return;
    }
    // Find the dir section and extract its dirPath
    const dirSection = dirSections.find(s => s.id === sectionId);
    setSelectedDirPath(dirSection?.dirPath || null);
  }, [dirSections]);

  // === Note section change handler (triggers move dialog for dir sections) ===
  const handleNoteSectionChange = useCallback((noteNodeId: string, newSectionId: string | null, startPosition: Position) => {
    // noteNodeId is 'note-<relativePath>'
    const relPath = noteNodeId.replace('note-', '');
    const parts = relPath.split('/');
    const filename = parts[parts.length - 1];
    const sourceDirPath = parts.length > 1 ? parts.slice(0, -1).join('/') : '';

    // Determine destination dirPath from the new section
    let destDirPath = '';
    if (newSectionId && newSectionId.startsWith('dirsection-')) {
      const dirSection = dirSections.find(s => s.id === newSectionId);
      destDirPath = dirSection?.dirPath || '';
    }

    // Only show dialog if the note actually changed directories
    if (sourceDirPath !== destDirPath) {
      setPendingMove({
        noteId: noteNodeId,
        noteName: filename,
        sourceDirPath,
        destDirPath,
        revertPosition: startPosition,
      });
    }
  }, [dirSections]);

  // === Move confirmation handlers ===
  const handleMoveConfirm = useCallback(async () => {
    if (!pendingMove) return;
    const { noteName, sourceDirPath, destDirPath } = pendingMove;
    const sourcePath = sourceDirPath ? `${sourceDirPath}/${noteName}` : noteName;
    const destPath = destDirPath ? `${destDirPath}/${noteName}` : noteName;
    await moveEntry(sourcePath, destPath);
    setPendingMove(null);
  }, [pendingMove, moveEntry]);

  const handleMoveCancel = useCallback(() => {
    if (pendingMove) {
      // Immediately revert the node position on canvas
      if (setNodePositionRef.current) {
        setNodePositionRef.current(pendingMove.noteId, pendingMove.revertPosition);
      }
      // Persist the reverted position to the sidecar
      const relPath = pendingMove.noteId.replace('note-', '');
      const parts = relPath.split('/');
      const filename = parts[parts.length - 1];
      const dirPath = parts.length > 1 ? parts.slice(0, -1).join('/') : undefined;
      updateItemPosition(filename, pendingMove.revertPosition, dirPath);
    }
    setPendingMove(null);
  }, [pendingMove, updateItemPosition]);

  const isOnCanvas = currentKb !== null && !isAdjutantPage;

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        onToggle={handleSidebarToggle}
        kbs={kbs}
        currentKb={currentKb}
        currentPath={currentPath}
        entries={rootEntries}
        onKbSelect={setCurrentKb}
        onFolderFocus={handleFolderFocus}
        onNoteOpen={(notePath) => {
          if (!currentKb) return;
          // Pan canvas to the note, then open editor after animation
          const nodeId = `note-${notePath}`;
          const FOCUS_ANIMATION_MS = 600;
          if (focusOnNodeRef.current) {
            focusOnNodeRef.current(nodeId, { zoom: 1, duration: FOCUS_ANIMATION_MS });
            setTimeout(() => {
              requestAnimationFrame(() => {
                handleNoteOpen(
                  notePath,
                  { x: window.innerWidth / 2 - 100, y: window.innerHeight / 2 - 141, width: 200, height: 283 },
                );
              });
            }, FOCUS_ANIMATION_MS);
          } else {
            handleNoteOpen(
              notePath,
              { x: window.innerWidth / 2 - 100, y: window.innerHeight / 2 - 141, width: 200, height: 283 },
            );
          }
        }}
        onSettingsClick={() => setSettingsOpen(true)}
        onNavigateToFolder={navigateToFolder}
        loading={loadingKbs}
        highlightedDirPath={selectedDirPath}
      />

      {isAdjutantPage ? (
        <AdjutantDashboard sidebarOpen={sidebarOpen} data={adjutantData} />
      ) : (
      <main className={`app-main full ${isPlacementMode ? 'placement-mode' : ''}`}>
        {!isOnCanvas ? (
          <Home
            kbs={kbs}
            loadingKbs={loadingKbs}
            kbRootConfigured={!!settings.kbRoot}
            onKbSelect={handleHomeKbSelect}
            onNoteSelect={handleHomeNoteSelect}
            onSettingsClick={() => setSettingsOpen(true)}
            searchNotes={searchNotes}
            searching={searching}
          />
        ) : (
          <Canvas
            notes={canvasNotes}
            images={images}
            sections={allSections}
            stickies={stickies}
            categories={kbs}
            activeTool={activeTool}
            isPlacementMode={isPlacementMode}
            onPlacementClick={handlePlacementClick}
            onNoteOpen={handleNoteOpen}
            onNotePositionChange={(nodeId, position) => {
              // nodeId is 'note-<relativePath>' — extract filename and dirPath
              const relPath = nodeId.replace('note-', '');
              const parts = relPath.split('/');
              const filename = parts[parts.length - 1];
              const dirPath = parts.length > 1 ? parts.slice(0, -1).join('/') : undefined;
              handleItemPositionChange(filename, position, dirPath);
            }}
            onImagePositionChange={handleImagePositionChange}
            onImageResize={handleImageResize}
            onImagePaste={handleImagePaste}
            onNotesDelete={async (ids) => {
              if (!currentKb) return;
              for (const id of ids) {
                const filename = id.replace('note-', '');
                const notePath = currentPath ? `${currentPath}/${filename}` : filename;
                await deleteNote(currentKb, notePath);
              }
              refetchFolder();
            }}
            onImagesDelete={handleImagesDelete}
            onNoteDuplicate={async (slug, position) => {
              if (!currentKb) return;
              const relPath = slug.replace('note-', '');
              const fullPath = currentPath ? `${currentPath}/${relPath}` : relPath;
              const source = await getNote(currentKb, fullPath);
              if (!source) return;
              const parts = relPath.split('/');
              const dirPath = parts.length > 1 ? parts.slice(0, -1).join('/') : '';
              const folder = dirPath ? (currentPath ? `${currentPath}/${dirPath}` : dirPath) : currentPath;
              const created = await createNote({
                kb: currentKb,
                folder,
                title: `${source.title} (copy)`,
                position,
              });
              if (created) {
                await updateNote(currentKb, created.path, { content: source.content, title: `${source.title} (copy)`, tags: source.tags });
                refetchFolder();
              }
            }}
            onImageDuplicate={async (id, position) => {
              const source = images.find(img => img.id === id);
              if (!source) return;
              try {
                const res = await fetch(source.webpUrl);
                const blob = await res.blob();
                const file = new File([blob], `${id}-copy.webp`, { type: 'image/webp' });
                uploadImage(file, position);
              } catch { /* ignore failed duplicate */ }
            }}
            onSectionCreate={handleSectionCreate}
            onSectionPositionChange={handleSectionPositionChange}
            onSectionResize={handleSectionResize}
            onSectionRename={handleSectionRename}
            onSectionColorChange={handleSectionColorChange}
            onSectionsDelete={handleSectionsDelete}
            onNoteSectionChange={handleNoteSectionChange}
            onStickyCreate={handleStickyCreate}
            onStickyPositionChange={handleStickyPositionChange}
            onStickyTextChange={handleStickyTextChange}
            onStickyColorChange={handleStickyColorChange}
            onStickiesDelete={handleStickiesDelete}
            onEnterPlacementMode={enterPlacementMode}
            onSectionSelected={handleSectionSelected}
            focusOnSectionId={focusOnSectionId}
            onFocusComplete={() => setFocusOnSectionId(null)}
            onFocusOnNodeRef={(handler) => { focusOnNodeRef.current = handler; }}
            onSetNodePositionRef={(handler) => { setNodePositionRef.current = handler; }}
            loading={loadingFolder}
            settings={settings}
          />
        )}
      </main>
      )}

      {isOnCanvas && (
        <>
          <Toolbar
            isPlacementMode={isPlacementMode}
            placementType={placementType}
            onEnterPlacementMode={enterPlacementMode}
            onExitPlacementMode={exitPlacementMode}
          />
          <GhostNote visible={isPlacementMode && placementType === 'note'} />
          <GhostSection visible={isPlacementMode && placementType === 'section'} />
          <GhostSticky visible={isPlacementMode && placementType === 'sticky'} />
          <PlacementHint visible={isPlacementMode} />
          {isTouchDevice() && (
            <ToolSwitcher
              activeTool={activeTool}
              onToolChange={setActiveTool}
              sidebarOpen={sidebarOpen}
            />
          )}
        </>
      )}

      <Dialog
        open={!!pendingMove}
        title="Move file?"
        message={pendingMove ? `Move "${pendingMove.noteName}" from "${pendingMove.sourceDirPath || 'root'}" to "${pendingMove.destDirPath || 'root'}"?` : ''}
        confirmLabel="Move"
        cancelLabel="Cancel"
        onConfirm={handleMoveConfirm}
        onCancel={handleMoveCancel}
      />

      <ErrorBoundary>
        <Suspense fallback={null}>
          {settingsOpen && (
            <SettingsDialog
              open={settingsOpen}
              settings={settings}
              onSettingChange={updateSetting}
              onClose={() => setSettingsOpen(false)}
              onKbRootSaved={refetchKbs}
            />
          )}
        </Suspense>
      </ErrorBoundary>

      <ErrorBoundary>
        <Suspense fallback={null}>
          {focusedNote && currentKb && (
            <NoteEditor
            kb={currentKb}
            notePath={focusedNote}
            originRect={originRect}
            initialNote={initialNoteForEditor}
            sidebarOpen={sidebarOpen}
            onClose={handleNoteClose}
            onSave={handleNoteSave}
            onDelete={handleNoteDelete}
            getNote={getNote}
          />
          )}
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}

function AppWithProviders() {
  return (
    <PlacementProvider>
      <EditorProvider>
        <AppContent />
      </EditorProvider>
    </PlacementProvider>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<AppWithProviders />} />
      <Route path="/adjutant" element={<AppWithProviders />} />
      <Route path="/:kb" element={<AppWithProviders />} />
      <Route path="/:kb/*" element={<AppWithProviders />} />
    </Routes>
  );
}

export default App;
