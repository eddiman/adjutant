import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import { Home } from './components/Home';
import { Sidebar } from './components/Sidebar';
import { Toolbar } from './components/Toolbar';
import { GhostSection } from './components/GhostSection';
import { GhostSticky } from './components/GhostSticky';
import { PlacementHint } from './components/PlacementHint';
import { Canvas } from './components/Canvas';
import { Dialog } from './components/Dialog';
import { AdjutantDashboard } from './components/AdjutantDashboard';

const NoteEditor = lazy(() => import('./components/NoteEditor/NoteEditor'));
const SettingsDialog = lazy(() => import('./components/SettingsDialog/SettingsDialog'));

import { useCanvas } from './hooks/useCanvas';
import { useKbs } from './hooks/useKbs';
import { useFolder } from './hooks/useFolder';
import { useRecursiveFolder } from './hooks/useRecursiveFolder';
import { useNotes } from './hooks/useNotes';
import { useImages } from './hooks/useImages';
import { useSettings } from './hooks/useSettings';
import { useAdjutant } from './hooks/useAdjutant';
import { EditorProvider, useEditor, PlacementProvider, usePlacement } from './contexts';
import type { Position, StickyColor, NoteFile, Section } from './types';

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
    meta,
    rootEntries,
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
  } = useRecursiveFolder(folderOptions);

  // Keep flat folder listing for sidebar navigation
  const {
    entries: sidebarEntries,
    meta: sidebarMeta,
  } = useFolder(folderOptions);

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
  }, [setFocusedNote, clearEditorState]);

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

  // === Folder navigation ===

  const handleFolderOpen = useCallback((folderName: string) => {
    if (!currentKb) return;
    const newPath = currentPath ? `${currentPath}/${folderName}` : folderName;
    navigateToFolder(currentKb, newPath);
  }, [currentKb, currentPath, navigateToFolder]);

  // === Note CRUD handlers ===

  const handleNoteCreate = useCallback(async (position: Position) => {
    if (!currentKb) return;
    const note = await createNote({
      kb: currentKb,
      folder: currentPath,
      title: 'Untitled Note',
      position,
    });
    if (note) {
      refetchFolder();
      // Open the new note in the editor
      prepareEditorOpen(
        { x: window.innerWidth / 2 - 100, y: window.innerHeight / 2 - 141, width: 200, height: 283 },
        note,
      );
      setFocusedNote(note.path);
    }
  }, [currentKb, currentPath, createNote, refetchFolder, prepareEditorOpen, setFocusedNote]);

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

  const handleFolderFocus = useCallback((folderName: string) => {
    // When clicking a folder in sidebar, focus the corresponding section on canvas
    const dirPath = currentPath ? `${currentPath}/${folderName}` : folderName;
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
    // Revert by refetching
    refetchFolder();
    setPendingMove(null);
  }, [refetchFolder]);

  const isOnCanvas = currentKb !== null && !isAdjutantPage;

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        onToggle={handleSidebarToggle}
        kbs={kbs}
        currentKb={currentKb}
        currentPath={currentPath}
        entries={sidebarEntries}
        meta={sidebarMeta}
        onKbSelect={setCurrentKb}
        onFolderOpen={handleFolderOpen}
        onFolderFocus={handleFolderFocus}
        onNoteOpen={(notePath) => {
          if (!currentKb) return;
          handleNoteOpen(
            notePath,
            { x: window.innerWidth / 2 - 100, y: window.innerHeight / 2 - 141, width: 200, height: 283 },
          );
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
            activeTool="pan"
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
            onNoteDuplicate={async () => {}}
            onImageDuplicate={async () => {}}
            onSectionCreate={handleSectionCreate}
            onSectionPositionChange={handleSectionPositionChange}
            onSectionResize={handleSectionResize}
            onSectionRename={handleSectionRename}
            onSectionColorChange={handleSectionColorChange}
            onSectionsDelete={handleSectionsDelete}
            onStickyCreate={handleStickyCreate}
            onStickyPositionChange={handleStickyPositionChange}
            onStickyTextChange={handleStickyTextChange}
            onStickyColorChange={handleStickyColorChange}
            onStickiesDelete={handleStickiesDelete}
            onEnterPlacementMode={enterPlacementMode}
            onSectionSelected={handleSectionSelected}
            focusOnSectionId={focusOnSectionId}
            onFocusComplete={() => setFocusOnSectionId(null)}
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
          <GhostSection visible={isPlacementMode && placementType === 'section'} />
          <GhostSticky visible={isPlacementMode && placementType === 'sticky'} />
          <PlacementHint visible={isPlacementMode} />
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
