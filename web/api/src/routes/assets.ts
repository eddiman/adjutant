import { Router } from 'express';
import multer from 'multer';
import rateLimit from 'express-rate-limit';
import { imageService } from '../services/imageService.js';
import type { ImageMetadata } from '../services/imageService.js';

const router = Router();

const uploadLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 20, // 20 uploads per 15 minutes
  message: 'Too many upload requests, please try again later',
  standardHeaders: true,
  legacyHeaders: false,
});

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml', 'image/heic', 'image/heif'];
    if (allowedTypes.includes(file.mimetype)) {
      cb(null, true);
    } else {
      cb(new Error('Invalid file type. Only JPEG, PNG, GIF, WebP, SVG, and HEIC are allowed.'));
    }
  },
});

// POST /api/assets/upload — Upload an image (requires kb in body)
router.post('/upload', uploadLimiter, upload.single('image'), async (req, res) => {
  try {
    if (!req.file) {
      res.status(400).json({ error: 'No image file provided' });
      return;
    }

    const kb = req.body.kb as string;
    if (!kb) {
      res.status(400).json({ error: 'Missing required field: kb' });
      return;
    }

    const processed = await imageService.processAndSave(req.file.buffer, req.file.originalname, kb);
    if (!processed) {
      res.status(404).json({ error: 'Knowledge base not found' });
      return;
    }

    const urls = imageService.getUrls(processed.id, kb);
    const metadata: ImageMetadata = {
      id: processed.id,
      ...urls,
      width: processed.width,
      height: processed.height,
      aspectRatio: processed.width / processed.height,
      kb,
    };

    res.status(201).json(metadata);
  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ error: 'Failed to upload image' });
  }
});

// GET /api/assets?kb=:kb — List images for a KB
router.get('/', async (req, res) => {
  try {
    const kb = req.query.kb as string;
    if (!kb) {
      res.status(400).json({ error: 'Missing required query parameter: kb' });
      return;
    }

    const images = await imageService.list(kb);
    res.json({ images, total: images.length });
  } catch (error) {
    console.error('List error:', error);
    res.status(500).json({ error: 'Failed to list images' });
  }
});

// GET /api/assets/:filename?kb=:kb — Serve an image file
router.get('/:filename', async (req, res) => {
  try {
    const kb = req.query.kb as string;
    if (!kb) {
      res.status(400).json({ error: 'Missing required query parameter: kb' });
      return;
    }

    const result = await imageService.get(req.params.filename, kb);
    if (!result) {
      res.status(404).json({ error: 'Image not found' });
      return;
    }

    res.set('Content-Type', result.contentType);
    res.set('Cache-Control', 'public, max-age=31536000');
    res.send(result.buffer);
  } catch (error) {
    console.error('Get error:', error);
    res.status(500).json({ error: 'Failed to get image' });
  }
});

// DELETE /api/assets/:id?kb=:kb — Delete an image
router.delete('/:id', async (req, res) => {
  try {
    const kb = req.query.kb as string;
    if (!kb) {
      res.status(400).json({ error: 'Missing required query parameter: kb' });
      return;
    }

    const success = await imageService.delete(req.params.id, kb);
    if (!success) {
      res.status(404).json({ error: 'Image not found' });
      return;
    }

    res.status(204).send();
  } catch (error) {
    console.error('Delete error:', error);
    res.status(500).json({ error: 'Failed to delete image' });
  }
});

export default router;
