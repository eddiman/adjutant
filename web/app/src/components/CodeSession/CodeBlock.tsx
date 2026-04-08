/**
 * Shiki-powered code block with lazy-loaded syntax highlighting.
 *
 * Shows plain <pre> until the highlighter initializes, then replaces
 * with highlighted HTML. Uses tokyo-night theme.
 */

import { memo, useEffect, useState, useRef } from 'react';
import type { BundledLanguage } from 'shiki';

// Lazy-load shiki to keep initial bundle small
let highlighterPromise: ReturnType<typeof import('shiki').then> | null = null;

function getHighlighter() {
  if (!highlighterPromise) {
    highlighterPromise = import('shiki').then(async (shiki) => {
      return shiki.createHighlighter({
        themes: ['tokyo-night'],
        langs: [
          'typescript', 'javascript', 'python', 'bash', 'json',
          'yaml', 'css', 'html', 'go', 'rust', 'markdown',
          'tsx', 'jsx', 'sql', 'shell', 'diff',
        ],
      });
    });
  }
  return highlighterPromise;
}

interface CodeBlockProps {
  code: string;
  language?: string;
}

export const CodeBlock = memo(function CodeBlock({ code, language }: CodeBlockProps) {
  const [html, setHtml] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    getHighlighter().then(highlighter => {
      if (cancelled) return;

      const langs = highlighter.getLoadedLanguages();
      const lang = (language && langs.includes(language as BundledLanguage))
        ? language as BundledLanguage
        : 'text';

      try {
        const result = highlighter.codeToHtml(code, {
          lang: lang === 'text' ? 'javascript' : lang,
          theme: 'tokyo-night',
        });
        setHtml(result);
      } catch {
        // Fallback to plain text
        setHtml(null);
      }
    }).catch(() => {
      // Shiki failed to load — keep plain pre
    });

    return () => { cancelled = true; };
  }, [code, language]);

  if (html) {
    return (
      <div
        ref={containerRef}
        dangerouslySetInnerHTML={{ __html: html }}
        style={{
          fontSize: '0.8125rem',
          lineHeight: '1.5',
          borderRadius: '0.375rem',
          overflow: 'auto',
        }}
      />
    );
  }

  // Fallback: plain pre
  return (
    <pre style={{
      background: '#0d0d14',
      border: '1px solid var(--color-border)',
      borderRadius: '0.375rem',
      padding: '0.75rem 1rem',
      overflow: 'auto',
      fontSize: '0.8125rem',
      lineHeight: '1.5',
      fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
    }}>
      <code>{code}</code>
    </pre>
  );
});
