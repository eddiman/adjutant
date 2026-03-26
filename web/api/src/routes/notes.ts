import { Router, Request, Response } from 'express';
import { ZodError } from 'zod';
import { fileNoteService } from '../services/fileNoteService.js';
import { searchService } from '../services/searchService.js';
import { NoteCreateSchema, NoteUpdateSchema } from '../types/note.js';

const router = Router();

// GET /api/notes/search?kb=:kb&q=:query — Search notes within a KB
// NOTE: This must be before the GET / route to avoid matching "search" as a path param
router.get('/search', async (req: Request, res: Response) => {
  try {
    const kb = req.query.kb as string;
    const query = req.query.q as string;

    if (!kb || !query) {
      res.status(400).json({ error: 'Missing required query parameters: kb, q' });
      return;
    }

    const results = await searchService.search(kb, query);
    res.json({ notes: results, total: results.length });
  } catch (error) {
    res.status(500).json({ error: 'Failed to search notes' });
  }
});

// GET /api/notes?kb=:kb&path=:filePath — Get a single note
router.get('/', async (req: Request, res: Response) => {
  try {
    const kb = req.query.kb as string;
    const filePath = req.query.path as string;

    if (!kb || !filePath) {
      res.status(400).json({ error: 'Missing required query parameters: kb, path' });
      return;
    }

    const note = await fileNoteService.get(kb, filePath);
    if (!note) {
      res.status(404).json({ error: 'Note not found' });
      return;
    }

    res.json(note);
  } catch (error) {
    res.status(500).json({ error: 'Failed to get note' });
  }
});

// POST /api/notes — Create a new note
router.post('/', async (req: Request, res: Response) => {
  try {
    const input = NoteCreateSchema.parse(req.body);
    const note = await fileNoteService.create(input);
    if (!note) {
      res.status(400).json({ error: 'Failed to create note — KB or folder not found' });
      return;
    }
    searchService.invalidate(input.kb);
    res.status(201).json(note);
  } catch (error) {
    if (error instanceof ZodError) {
      res.status(400).json({ error: 'Invalid note data', details: error.errors });
    } else {
      console.error('Failed to create note:', error);
      res.status(500).json({ error: 'Failed to create note' });
    }
  }
});

// PUT /api/notes?kb=:kb&path=:filePath — Update a note
router.put('/', async (req: Request, res: Response) => {
  try {
    const kb = req.query.kb as string;
    const filePath = req.query.path as string;

    if (!kb || !filePath) {
      res.status(400).json({ error: 'Missing required query parameters: kb, path' });
      return;
    }

    const input = NoteUpdateSchema.parse(req.body);
    const note = await fileNoteService.update(kb, filePath, input);
    if (!note) {
      res.status(404).json({ error: 'Note not found' });
      return;
    }

    searchService.invalidate(kb);
    res.json(note);
  } catch (error) {
    if (error instanceof ZodError) {
      res.status(400).json({ error: 'Invalid note data', details: error.errors });
    } else {
      console.error('Failed to update note:', error);
      res.status(500).json({ error: 'Failed to update note' });
    }
  }
});

// DELETE /api/notes?kb=:kb&path=:filePath — Delete a note
router.delete('/', async (req: Request, res: Response) => {
  try {
    const kb = req.query.kb as string;
    const filePath = req.query.path as string;

    if (!kb || !filePath) {
      res.status(400).json({ error: 'Missing required query parameters: kb, path' });
      return;
    }

    const deleted = await fileNoteService.delete(kb, filePath);
    if (!deleted) {
      res.status(404).json({ error: 'Note not found' });
      return;
    }

    searchService.invalidate(kb);
    res.status(204).send();
  } catch (error) {
    res.status(500).json({ error: 'Failed to delete note' });
  }
});

export default router;
