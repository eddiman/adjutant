import { useCallback, useEffect, useState, useRef, useMemo } from 'react';
import type { CanvasImage, Position } from '../types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function debounce<T extends (...args: any[]) => void>(fn: T, delay: number): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

interface UseImagesOptions {
  kb: string | null;
  path: string;
}

interface UseImagesReturn {
  images: CanvasImage[];
  loading: boolean;
  uploadImage: (file: File, position: Position) => Promise<CanvasImage | null>;
  updateImagePosition: (id: string, position: Position) => void;
  updateImageSize: (id: string, width: number, height: number) => void;
  deleteImage: (id: string) => Promise<boolean>;
}

export function useImages(options: UseImagesOptions): UseImagesReturn {
  const { kb, path } = options;
  const [images, setImages] = useState<CanvasImage[]>([]);
  const [loading, setLoading] = useState(false);
  const imageMetaCache = useRef<Record<string, { position?: Position; width?: number; height?: number }>>({});

  const fetchImages = useCallback(async () => {
    if (!kb) {
      setImages([]);
      return;
    }

    setLoading(true);
    try {
      // Fetch image list from assets API
      const res = await fetch(`/api/assets?kb=${encodeURIComponent(kb)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      
      // Fetch folder metadata to get image positions
      const metaRes = await fetch(`/api/folders/meta?kb=${encodeURIComponent(kb)}&path=${encodeURIComponent(path)}`);
      const meta = metaRes.ok ? await metaRes.json() : { images: {} };
      
      imageMetaCache.current = meta.images || {};
      
      const fetchedImages: CanvasImage[] = (data.images || []).map((img: CanvasImage) => {
        const stored = imageMetaCache.current[img.id];
        return {
          ...img,
          position: stored?.position || { x: Math.random() * 400, y: Math.random() * 400 },
          displayWidth: stored?.width,
          displayHeight: stored?.height,
          status: 'ready' as const,
        };
      });
      setImages(fetchedImages);
    } catch (err) {
      console.error('Failed to fetch images:', err);
    } finally {
      setLoading(false);
    }
  }, [kb, path]);

  useEffect(() => {
    fetchImages();
  }, [fetchImages]);

  const uploadImage = useCallback(async (file: File, position: Position): Promise<CanvasImage | null> => {
    if (!kb) return null;

    const tempId = `upload-${Date.now()}`;
    const tempImage: CanvasImage = {
      id: tempId,
      webpUrl: '',
      thumbUrl: '',
      width: 300,
      height: 200,
      aspectRatio: 1.5,
      kb,
      position,
      status: 'uploading',
    };
    setImages(prev => [...prev, tempImage]);

    try {
      const formData = new FormData();
      formData.append('image', file);
      formData.append('kb', kb);

      const res = await fetch('/api/assets/upload', { method: 'POST', body: formData });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const metadata = await res.json();

      const newImage: CanvasImage = {
        ...metadata,
        position,
        status: 'ready',
      };

      // Save position to server
      await fetch(`/api/folders/images?kb=${encodeURIComponent(kb)}&path=${encodeURIComponent(path)}&id=${metadata.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position, width: metadata.width, height: metadata.height })
      });

      imageMetaCache.current[metadata.id] = { position, width: metadata.width, height: metadata.height };

      setImages(prev => prev.map(img => img.id === tempId ? newImage : img));
      return newImage;
    } catch (err) {
      console.error('Failed to upload image:', err);
      setImages(prev => prev.map(img =>
        img.id === tempId ? { ...img, status: 'error', errorMessage: 'Upload failed' } : img,
      ));
      return null;
    }
  }, [kb, path]);

  const debouncedUpdatePosition = useMemo(
    () => debounce(async (imageId: string, position: Position, width?: number, height?: number) => {
      if (!kb) return;
      try {
        await fetch(`/api/folders/images?kb=${encodeURIComponent(kb)}&path=${encodeURIComponent(path)}&id=${imageId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ position, width, height })
        });
      } catch (err) {
        console.error('Failed to update image position:', err);
      }
    }, 300),
    [kb, path]
  );

  const updateImagePosition = useCallback((id: string, position: Position) => {
    setImages(prev => prev.map(img => img.id === id ? { ...img, position } : img));
    imageMetaCache.current[id] = { ...imageMetaCache.current[id], position };
    debouncedUpdatePosition(id, position, imageMetaCache.current[id]?.width, imageMetaCache.current[id]?.height);
  }, [debouncedUpdatePosition]);

  const updateImageSize = useCallback((id: string, displayWidth: number, displayHeight: number) => {
    setImages(prev => {
      const img = prev.find(i => i.id === id);
      if (img) {
        // Use position from state if not in cache
        if (!imageMetaCache.current[id]?.position) {
          imageMetaCache.current[id] = { ...imageMetaCache.current[id], position: img.position };
        }
      }
      return prev.map(i => i.id === id ? { ...i, displayWidth, displayHeight } : i);
    });
    imageMetaCache.current[id] = { ...imageMetaCache.current[id], width: displayWidth, height: displayHeight };
    const position = imageMetaCache.current[id]?.position;
    if (position) {
      debouncedUpdatePosition(id, position, displayWidth, displayHeight);
    }
  }, [debouncedUpdatePosition]);

  const deleteImage = useCallback(async (id: string): Promise<boolean> => {
    if (!kb) return false;

    setImages(prev => prev.filter(img => img.id !== id));

    try {
      // Delete image file
      const res = await fetch(`/api/assets/${id}?kb=${encodeURIComponent(kb)}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);

      // Delete image position metadata
      await fetch(`/api/folders/images?kb=${encodeURIComponent(kb)}&path=${encodeURIComponent(path)}&id=${id}`, {
        method: 'DELETE'
      });

      delete imageMetaCache.current[id];
      return true;
    } catch (err) {
      console.error('Failed to delete image:', err);
      await fetchImages();
      return false;
    }
  }, [kb, path, fetchImages]);

  return { images, loading, uploadImage, updateImagePosition, updateImageSize, deleteImage };
}
