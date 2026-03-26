import { useState, useCallback } from 'react';
import type { KbMeta, NoteMeta } from '../../types';
import { AnimatedBackground } from './AnimatedBackground';
import styles from './Home.module.css';

interface HomeProps {
  kbs: KbMeta[];
  loadingKbs: boolean;
  kbRootConfigured: boolean;
  onKbSelect: (kbName: string) => void;
  onNoteSelect: (note: { kb: string; path: string }) => void;
  onSettingsClick: () => void;
  searchNotes: (kb: string, query: string) => Promise<NoteMeta[]>;
  searching: boolean;
}

export function Home({
  kbs,
  loadingKbs,
  kbRootConfigured,
  onKbSelect,
  onNoteSelect,
  onSettingsClick,
  searchNotes,
  searching,
}: HomeProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<NoteMeta[]>([]);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return;
    setHasSearched(true);
    const allResults: NoteMeta[] = [];
    for (const kb of kbs) {
      const results = await searchNotes(kb.name, searchQuery.trim());
      allResults.push(...results);
    }
    setSearchResults(allResults);
  }, [searchQuery, kbs, searchNotes]);

  const handleSearchKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
    if (e.key === 'Escape') {
      setSearchQuery('');
      setSearchResults([]);
      setHasSearched(false);
    }
  }, [handleSearch]);

  if (!kbRootConfigured) {
    return (
      <div className={styles.home}>
        <AnimatedBackground />
        <div className={styles.content}>
          <h1 className={styles.title}>
            <span className={styles.titleBracket}>&lt;</span>
            Adjutant Web
            <span className={styles.titleBracket}>&gt;</span>
          </h1>
          <p className={styles.subtitle}>KB Explorer</p>
          <div className={styles.setupCard}>
            <p className={styles.setupText}>No knowledge base directory configured.</p>
            <button className={styles.setupButton} onClick={onSettingsClick}>
              Configure KB Root
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.home}>
      <AnimatedBackground />
      <div className={styles.content}>
        <h1 className={styles.title}>
          <span className={styles.titleBracket}>&lt;</span>
          Adjutant Web
          <span className={styles.titleBracket}>&gt;</span>
        </h1>
        <p className={styles.subtitle}>KB Explorer</p>

        {/* Search bar */}
        <div className={styles.searchWrapper}>
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Search across all knowledge bases..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
          />
        </div>

        {/* Search results */}
        {hasSearched && (
          <div className={styles.searchResults}>
            {searching ? (
              <p className={styles.searchStatus}>Searching...</p>
            ) : searchResults.length === 0 ? (
              <p className={styles.searchStatus}>No results found</p>
            ) : (
              searchResults.map((note, i) => (
                <button
                  key={`${note.kb}-${note.path}-${i}`}
                  className={styles.searchResult}
                  onClick={() => onNoteSelect({ kb: note.kb, path: note.path })}
                >
                  <span className={styles.searchResultTitle}>{note.title}</span>
                  <span className={styles.searchResultPath}>{note.kb}/{note.path}</span>
                </button>
              ))
            )}
          </div>
        )}

        {/* KB cards */}
        {!hasSearched && (
          <div className={styles.kbGrid}>
            {loadingKbs ? (
              <p className={styles.loadingText}>Discovering knowledge bases...</p>
            ) : kbs.length === 0 ? (
              <p className={styles.emptyText}>No knowledge bases found in the configured directory.</p>
            ) : (
              kbs.map(kb => (
                <button
                  key={kb.name}
                  className={styles.kbCard}
                  onClick={() => onKbSelect(kb.name)}
                >
                  <h3 className={styles.kbName}>{kb.name}</h3>
                  <p className={styles.kbDescription}>{kb.description || 'No description'}</p>
                  {kb.created && (
                    <span className={styles.kbDate}>Created {kb.created}</span>
                  )}
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
