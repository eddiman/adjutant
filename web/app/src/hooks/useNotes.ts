import { useCallback, useState } from 'react';
import type { NoteFile, NoteMeta, Position } from '../types';

interface NoteCreateInput {
  kb: string;
  folder?: string;
  title: string;
  content?: string;
  tags?: string[];
  position?: Position;
}

interface NoteUpdateInput {
  content?: string;
  title?: string;
  tags?: string[];
  position?: Position;
  section?: string | null;
}

interface UseNotesReturn {
  getNote: (kb: string, path: string) => Promise<NoteFile | null>;
  createNote: (input: NoteCreateInput) => Promise<NoteFile | null>;
  updateNote: (kb: string, path: string, input: NoteUpdateInput) => Promise<NoteFile | null>;
  deleteNote: (kb: string, path: string) => Promise<boolean>;
  searchNotes: (kb: string, query: string) => Promise<NoteMeta[]>;
  searching: boolean;
}

export function useNotes(): UseNotesReturn {
  const [searching, setSearching] = useState(false);

  const getNote = useCallback(async (kb: string, filePath: string): Promise<NoteFile | null> => {
    try {
      const params = new URLSearchParams({ kb, path: filePath });
      const res = await fetch(`/api/notes?${params}`);
      if (!res.ok) {
        if (res.status === 404) return null;
        throw new Error(`HTTP ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      console.error('Failed to get note:', err);
      return null;
    }
  }, []);

  const createNote = useCallback(async (input: NoteCreateInput): Promise<NoteFile | null> => {
    try {
      const res = await fetch('/api/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.error('Failed to create note:', err);
      return null;
    }
  }, []);

  const updateNote = useCallback(async (kb: string, filePath: string, input: NoteUpdateInput): Promise<NoteFile | null> => {
    try {
      const params = new URLSearchParams({ kb, path: filePath });
      const res = await fetch(`/api/notes?${params}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.error('Failed to update note:', err);
      return null;
    }
  }, []);

  const deleteNote = useCallback(async (kb: string, filePath: string): Promise<boolean> => {
    try {
      const params = new URLSearchParams({ kb, path: filePath });
      const res = await fetch(`/api/notes?${params}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);
      return true;
    } catch (err) {
      console.error('Failed to delete note:', err);
      return false;
    }
  }, []);

  const searchNotes = useCallback(async (kb: string, query: string): Promise<NoteMeta[]> => {
    setSearching(true);
    try {
      const params = new URLSearchParams({ kb, q: query });
      const res = await fetch(`/api/notes/search?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return data.notes || [];
    } catch (err) {
      console.error('Failed to search notes:', err);
      return [];
    } finally {
      setSearching(false);
    }
  }, []);

  return { getNote, createNote, updateNote, deleteNote, searchNotes, searching };
}
