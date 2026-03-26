import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { OriginRect } from '../components/Canvas';
import type { NoteFile } from '../types';

interface EditorContextValue {
  originRect: OriginRect | null;
  initialNoteForEditor: NoteFile | null;
  prepareEditorOpen: (rect: OriginRect, note: NoteFile | null) => void;
  clearEditorState: () => void;
}

const EditorContext = createContext<EditorContextValue | null>(null);

interface EditorProviderProps {
  children: ReactNode;
}

export function EditorProvider({ children }: EditorProviderProps) {
  const [originRect, setOriginRect] = useState<OriginRect | null>(null);
  const [initialNoteForEditor, setInitialNoteForEditor] = useState<NoteFile | null>(null);

  const prepareEditorOpen = useCallback((rect: OriginRect, note: NoteFile | null) => {
    setOriginRect(rect);
    setInitialNoteForEditor(note);
  }, []);

  const clearEditorState = useCallback(() => {
    setInitialNoteForEditor(null);
    setTimeout(() => setOriginRect(null), 300);
  }, []);

  return (
    <EditorContext.Provider value={{ originRect, initialNoteForEditor, prepareEditorOpen, clearEditorState }}>
      {children}
    </EditorContext.Provider>
  );
}

export function useEditor() {
  const context = useContext(EditorContext);
  if (!context) {
    throw new Error('useEditor must be used within an EditorProvider');
  }
  return context;
}
