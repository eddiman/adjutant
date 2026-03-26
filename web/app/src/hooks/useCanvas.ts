import { useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';

interface UseCanvasReturn {
  currentKb: string | null;
  currentPath: string;
  focusedNote: string | null;  // query param ?note=path/to/file.md
  setCurrentKb: (kb: string | null) => void;
  navigateToFolder: (kb: string, folderPath: string) => void;
  setFocusedNote: (notePath: string | null) => void;
}

export function useCanvas(): UseCanvasReturn {
  const { kb, '*': wildcardPath } = useParams<{ kb?: string; '*'?: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const currentKb = kb || null;
  const currentPath = wildcardPath || '';

  // Extract ?note= query param
  const searchParams = new URLSearchParams(location.search);
  const focusedNote = searchParams.get('note');

  const setCurrentKb = useCallback((newKb: string | null) => {
    if (newKb === null) {
      navigate('/');
    } else {
      navigate(`/${newKb}`);
    }
  }, [navigate]);

  const navigateToFolder = useCallback((navKb: string, folderPath: string) => {
    if (folderPath) {
      navigate(`/${navKb}/${folderPath}`);
    } else {
      navigate(`/${navKb}`);
    }
  }, [navigate]);

  const setFocusedNote = useCallback((notePath: string | null) => {
    const basePath = currentKb
      ? (currentPath ? `/${currentKb}/${currentPath}` : `/${currentKb}`)
      : '/';

    if (notePath) {
      navigate(`${basePath}?note=${encodeURIComponent(notePath)}`);
    } else {
      navigate(basePath);
    }
  }, [navigate, currentKb, currentPath]);

  return {
    currentKb,
    currentPath,
    focusedNote,
    setCurrentKb,
    navigateToFolder,
    setFocusedNote,
  };
}
