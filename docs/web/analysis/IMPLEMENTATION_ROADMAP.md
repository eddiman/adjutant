# Adjutant Web Implementation Roadmap

**Date**: March 17, 2026  
**Purpose**: Tactical plan for securing, integrating, and evolving Adjutant Web

---

## Quick Reference

| Phase | Timeline | Effort | Risk | Blockers |
|-------|----------|--------|------|----------|
| **Phase 0: Critical Fixes** | 1-2 days | 8-16 hours | Low | None |
| **Phase 1: Security & Stability** | 1-2 weeks | 40-80 hours | Low | Phase 0 complete |
| **Phase 2: Adjutant Integration** | 2-3 weeks | 80-120 hours | Medium | Adjutant architecture decisions |
| **Phase 3: Advanced Features** | 4-6 weeks | 160-240 hours | High | Phase 2 complete |
| **Phase 4: Multi-User** | 8-12 weeks | 320-480 hours | Very High | Product decisions |

---

## Phase 0: Critical Fixes (IMMEDIATE)

**Goal**: Address security vulnerabilities that pose immediate risk.

### Tasks

#### 1. Fix Command Injection (2 hours)
**File**: `api/src/routes/config.ts` lines 78-111

**Current Code**:
```typescript
const cmd = `open "${targetPath.replace(/"/g, '\\"')}"`;
exec(cmd, { timeout: 5000 }, (error) => { /* ... */ });
```

**New Code**:
```typescript
import { spawn } from 'child_process';

let command: string;
let args: string[];

if (platform === 'darwin') {
  command = 'open';
  args = [targetPath];
} else if (platform === 'linux') {
  command = 'xdg-open';
  args = [targetPath];
} else if (platform === 'win32') {
  command = 'explorer';
  args = [targetPath];
} else {
  res.status(501).json({ error: 'Not supported on this platform' });
  return;
}

const proc = spawn(command, args, { timeout: 5000 });

proc.on('error', (error) => {
  console.error('Failed to open in file manager:', error);
  res.status(500).json({ error: 'Failed to open in file manager' });
});

proc.on('exit', (code) => {
  if (code === 0) {
    res.json({ success: true });
  } else {
    res.status(500).json({ error: 'Failed to open in file manager' });
  }
});
```

**Test**:
```bash
curl -X POST http://localhost:3020/api/config/reveal \
  -H "Content-Type: application/json" \
  -d '{"path": "/tmp/test\"; rm -rf /; echo \""}'
# Should NOT execute rm -rf /
```

#### 2. Bind to Localhost (5 minutes)
**File**: `api/src/config.ts` line 6

**Change**:
```typescript
export const config = {
  port: 3020,
  host: process.env.ADJUTANT_WEB_HOST || '127.0.0.1',  // Changed from '0.0.0.0'
  // ...
};
```

**Test**:
```bash
# Should NOT be accessible from remote machine
curl http://<server-ip>:3020/health  # Should timeout or refuse
curl http://localhost:3020/health  # Should work
```

#### 3. Restrict CORS (30 minutes)
**File**: `api/src/index.ts` lines 16-27

**New Code**:
```typescript
const allowedOrigins = [
  'http://localhost:3021',
  'https://localhost:3021',
];

app.use((req, res, next) => {
  const origin = req.headers.origin;
  
  if (origin && allowedOrigins.includes(origin)) {
    res.header('Access-Control-Allow-Origin', origin);
    res.header('Access-Control-Allow-Credentials', 'true');
  }
  
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Accept, Authorization');
  
  if (req.method === 'OPTIONS') {
    res.sendStatus(200);
    return;
  }
  next();
});
```

#### 4. Add Upload Rate Limiting (1 hour)
**File**: `api/src/routes/assets.ts`

**Add Dependency**:
```bash
cd api && npm install express-rate-limit
```

**Code**:
```typescript
import rateLimit from 'express-rate-limit';

const uploadLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,  // 15 minutes
  max: 20,  // 20 uploads per 15 minutes per IP
  message: 'Too many upload requests, please try again later',
  standardHeaders: true,
  legacyHeaders: false,
});

router.post('/upload', uploadLimiter, upload.single('image'), async (req, res) => {
  // ... existing code
});
```

**Test**:
```bash
# Upload 21 images rapidly
for i in {1..21}; do
  curl -X POST http://localhost:3020/api/assets/upload \
    -F "image=@test.jpg" -F "kb=test-kb"
done
# 21st request should return 429 Too Many Requests
```

### Verification Checklist

- [ ] Command injection fix deployed
- [ ] Server binds to 127.0.0.1 only
- [ ] CORS restricted to localhost origins
- [ ] Upload rate limiting active
- [ ] All tests pass: `cd api && npm test`
- [ ] Manual security testing completed
- [ ] Git commit: `git commit -m "fix: critical security vulnerabilities"`

---

## Phase 1: Security & Stability (1-2 Weeks)

**Goal**: Make Adjutant Web production-safe for local single-user deployment.

### Week 1: Data Consistency

#### Task 1.1: Fix Image Position Storage (4 hours)
**Migrate from localStorage to `.adjutant-web.json`**

**Changes**:

1. Update sidecar schema (`api/src/types/folder.ts`):
```typescript
export const ImageMetaSchema = z.object({
  position: PositionSchema.optional(),
  width: z.number().optional(),
  height: z.number().optional(),
});

export const Adjutant WebSidecarSchema = z.object({
  items: z.record(z.string(), ItemMetaSchema).default({}),
  sections: z.record(z.string(), SectionSchema).default({}),
  stickies: z.record(z.string(), StickySchema).default({}),
  images: z.record(z.string(), ImageMetaSchema).default({}),  // NEW
  nextSectionId: z.number().default(1),
  nextStickyId: z.number().default(1),
});
```

2. Update folderService to handle image metadata (`api/src/services/folderService.ts`):
```typescript
async updateImagePosition(kb: string, folderPath: string, imageId: string, position: Position): Promise<void> {
  const absPath = await this.resolveFolder(kb, folderPath);
  if (!absPath) return;
  
  const meta = await this.readSidecar(absPath);
  if (!meta.images) meta.images = {};
  if (!meta.images[imageId]) meta.images[imageId] = {};
  meta.images[imageId].position = position;
  
  await this.writeSidecar(absPath, meta);
}
```

3. Update web hooks (`web/src/hooks/useImages.ts`):
```typescript
const updateImagePosition = useCallback((id: string, position: Position) => {
  // Remove localStorage logic
  // Add API call
  fetch(`/api/folders/images?kb=${kb}&id=${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ position })
  });
}, [kb]);
```

4. Migration script for existing users:
```typescript
// web/src/utils/migrateImagePositions.ts
export async function migrateImagePositions(kb: string): Promise<void> {
  const stored = localStorage.getItem('adjutant-web-image-positions');
  if (!stored) return;
  
  const positions = JSON.parse(stored);
  
  for (const [id, data] of Object.entries(positions)) {
    await fetch(`/api/folders/images?kb=${kb}&id=${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ position: data.position, width: data.width, height: data.height })
    });
  }
  
  localStorage.removeItem('adjutant-web-image-positions');
}
```

#### Task 1.2: Use UUIDs for Section/Sticky IDs (2 hours)
**Replace auto-increment with UUIDs**

**Changes**:

1. Update folderService (`api/src/services/folderService.ts`):
```typescript
import { v4 as uuidv4 } from 'uuid';

async createSection(...): Promise<{ id: string; section: SectionData } | null> {
  // ...
  const id = `section-${uuidv4()}`;  // Changed from `section-${meta.nextSectionId}`
  // ...
  meta.sections[id] = section;
  // Remove: meta.nextSectionId++;
  await this.writeSidecar(absPath, meta);
  return { id, section };
}

async createSticky(...): Promise<{ id: string; sticky: StickyData } | null> {
  // ...
  const id = `sticky-${uuidv4()}`;  // Changed from `sticky-${meta.nextStickyId}`
  // ...
}
```

2. Remove `nextSectionId`/`nextStickyId` from schema (mark as deprecated, keep for backward compatibility):
```typescript
export const Adjutant WebSidecarSchema = z.object({
  items: z.record(z.string(), ItemMetaSchema).default({}),
  sections: z.record(z.string(), SectionSchema).default({}),
  stickies: z.record(z.string(), StickySchema).default({}),
  images: z.record(z.string(), ImageMetaSchema).default({}),
  nextSectionId: z.number().optional(),  // Deprecated, kept for backward compatibility
  nextStickyId: z.number().optional(),   // Deprecated, kept for backward compatibility
});
```

#### Task 1.3: Add Sidecar Backups (4 hours)
**Backup before every write, keep last 5**

**Changes**:

1. Update folderService (`api/src/services/folderService.ts`):
```typescript
private async writeSidecar(absPath: string, data: Adjutant WebSidecar): Promise<void> {
  const sidecarPath = path.join(absPath, SIDECAR_FILENAME);
  
  // Backup existing sidecar
  try {
    await fs.access(sidecarPath);
    const backupPath = path.join(absPath, `.adjutant-web.json.backup-${Date.now()}`);
    await fs.copyFile(sidecarPath, backupPath);
    
    // Clean up old backups (keep last 5)
    const files = await fs.readdir(absPath);
    const backups = files
      .filter(f => f.startsWith('.adjutant-web.json.backup-'))
      .sort()
      .reverse();
    
    for (const old of backups.slice(5)) {
      await fs.unlink(path.join(absPath, old)).catch(() => {});
    }
  } catch {
    // No existing sidecar, skip backup
  }
  
  await fs.writeFile(sidecarPath, JSON.stringify(data, null, 2), 'utf-8');
}
```

2. Add repair endpoint (`api/src/routes/folders.ts`):
```typescript
router.post('/repair', async (req: Request, res: Response) => {
  const kb = req.query.kb as string;
  const folderPath = (req.query.path as string) || '';
  
  try {
    const result = await folderService.repairSidecar(kb, folderPath);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: 'Failed to repair sidecar' });
  }
});
```

3. Implement repair logic (`api/src/services/folderService.ts`):
```typescript
async repairSidecar(kb: string, folderPath: string): Promise<{ status: string; backup?: string }> {
  const absPath = await this.resolveFolder(kb, folderPath);
  if (!absPath) throw new Error('Folder not found');
  
  const sidecarPath = path.join(absPath, SIDECAR_FILENAME);
  
  // Try to parse current sidecar
  try {
    const content = await fs.readFile(sidecarPath, 'utf-8');
    Adjutant WebSidecarSchema.parse(JSON.parse(content));
    return { status: 'ok' };
  } catch (error) {
    // Current sidecar is corrupt, try backups
    const files = await fs.readdir(absPath);
    const backups = files
      .filter(f => f.startsWith('.adjutant-web.json.backup-'))
      .sort()
      .reverse();
    
    for (const backup of backups) {
      try {
        const backupPath = path.join(absPath, backup);
        const content = await fs.readFile(backupPath, 'utf-8');
        const parsed = Adjutant WebSidecarSchema.parse(JSON.parse(content));
        
        // Valid backup found, restore it
        await fs.copyFile(backupPath, sidecarPath);
        return { status: 'restored', backup };
      } catch {
        // Try next backup
      }
    }
    
    // No valid backups, create default sidecar
    const defaults = Adjutant WebSidecarSchema.parse({});
    await this.writeSidecar(absPath, defaults);
    return { status: 'reset' };
  }
}
```

#### Task 1.4: Add Optimistic Concurrency Control (6 hours)
**Prevent concurrent edit conflicts**

**Changes**:

1. Add version field to sidecar schema (`api/src/types/folder.ts`):
```typescript
export const Adjutant WebSidecarSchema = z.object({
  version: z.number().default(1),
  lastModified: z.string().optional(),
  items: z.record(z.string(), ItemMetaSchema).default({}),
  // ... rest
});
```

2. Update folderService (`api/src/services/folderService.ts`):
```typescript
async updateMeta(
  kb: string,
  folderPath: string,
  update: Partial<Adjutant WebSidecar>,
  expectedVersion?: number
): Promise<Adjutant WebSidecar | null> {
  const absPath = await this.resolveFolder(kb, folderPath);
  if (!absPath) return null;
  
  const existing = await this.readSidecar(absPath);
  
  // Check version
  if (expectedVersion !== undefined && existing.version !== expectedVersion) {
    throw new Error(`Conflict: expected version ${expectedVersion}, got ${existing.version}`);
  }
  
  const merged: Adjutant WebSidecar = {
    version: existing.version + 1,
    lastModified: new Date().toISOString(),
    items: { ...existing.items, ...update.items },
    sections: update.sections !== undefined ? { ...existing.sections, ...update.sections } : existing.sections,
    stickies: update.stickies !== undefined ? { ...existing.stickies, ...update.stickies } : existing.stickies,
    images: update.images !== undefined ? { ...existing.images, ...update.images } : existing.images,
  };
  
  await this.writeSidecar(absPath, merged);
  return merged;
}
```

3. Update routes to accept version (`api/src/routes/folders.ts`):
```typescript
router.put('/meta', async (req: Request, res: Response) => {
  const kb = req.query.kb as string;
  const folderPath = (req.query.path as string) || '';
  const expectedVersion = req.body.version as number | undefined;
  const updates = req.body.updates;
  
  try {
    const meta = await folderService.updateMeta(kb, folderPath, updates, expectedVersion);
    res.json(meta);
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('Conflict:')) {
      res.status(409).json({ error: error.message });
    } else {
      res.status(500).json({ error: 'Failed to update metadata' });
    }
  }
});
```

4. Update web hooks to handle conflicts (`web/src/hooks/useFolder.ts`):
```typescript
const metaVersionRef = useRef(meta?.version || 0);

useEffect(() => {
  if (meta) metaVersionRef.current = meta.version;
}, [meta]);

const updateItemPosition = useCallback(async (name: string, position: Position) => {
  // Optimistic update
  setMeta(prev => ({ ...prev, version: prev.version + 1, items: { ...prev.items, [name]: { ...prev.items[name], position } } }));
  
  try {
    const response = await fetch(`/api/folders/meta?kb=${kb}&path=${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        version: metaVersionRef.current,
        updates: { items: { [name]: { position } } }
      })
    });
    
    if (!response.ok) {
      if (response.status === 409) {
        // Conflict, refetch to get latest
        refetch();
      }
      throw new Error('Update failed');
    }
    
    const updated = await response.json();
    setMeta(updated);
    metaVersionRef.current = updated.version;
  } catch (error) {
    // Revert optimistic update
    refetch();
  }
}, [kb, path, refetch]);
```

### Week 2: Bug Fixes & Testing

#### Task 1.5: Fix Filename Collision Race Condition (3 hours)
**Use atomic file creation**

(Implementation shown in `COMPREHENSIVE_ANALYSIS.md` Section 5.2)

#### Task 1.6: Add Image Content-Type Validation (1 hour)
**Validate file type before processing**

(Implementation shown in `COMPREHENSIVE_ANALYSIS.md` Section 5.3)

#### Task 1.7: Fix Debounce Stale Closures (3 hours)
**Use refs to store latest values**

(Implementation shown in `COMPREHENSIVE_ANALYSIS.md` Section 5.4)

#### Task 1.8: Add Concurrency Tests (8 hours)
**Ensure race condition fixes work**

```typescript
// api/src/services/fileNoteService.test.ts
describe('FileNoteService - Concurrency', () => {
  it('handles 10 concurrent note creations with same title', async () => {
    const promises = Array.from({ length: 10 }, (_, i) =>
      fileNoteService.create({ kb: 'test-kb', title: 'Concurrent Note', folder: '' })
    );
    
    const results = await Promise.all(promises);
    const filenames = results.map(r => r?.filename).filter(Boolean);
    const uniqueFilenames = new Set(filenames);
    
    expect(uniqueFilenames.size).toBe(10);  // All unique
  });
  
  it('handles concurrent sidecar updates without data loss', async () => {
    const promises = Array.from({ length: 20 }, (_, i) =>
      folderService.updateMeta('test-kb', '', {
        items: { [`note-${i}.md`]: { position: { x: i * 100, y: i * 100 } } }
      })
    );
    
    await Promise.all(promises);
    
    const meta = await folderService.getMeta('test-kb', '');
    expect(Object.keys(meta.items).length).toBe(20);  // No updates lost
  });
});
```

### Deliverables

- [ ] All Phase 1 tasks completed
- [ ] Test coverage ≥ 90%
- [ ] All existing tests pass
- [ ] New concurrency tests pass
- [ ] Manual QA completed (create/update/delete notes, sections, stickies, images)
- [ ] Performance baseline established (search 1000 notes < 500ms)
- [ ] Documentation updated (AGENTS.md, inline comments)
- [ ] Git tag: `v2.1.0-stable`

---

## Phase 2: Adjutant Integration (2-3 Weeks)

**Goal**: Make Adjutant Web Adjutant-aware, use Adjutant's KB registry.

### Week 1: Registry Integration

#### Task 2.1: Read Adjutant KB Registry (4 hours)
**Replace configService with registry reader**

**Changes**:

1. Add `ADJUTANT_DIR` env var support (`api/src/config.ts`):
```typescript
import os from 'os';

export const config = {
  port: parseInt(process.env.ADJUTANT_WEB_PORT || '3020'),
  host: process.env.ADJUTANT_WEB_HOST || '127.0.0.1',
  adjutantDir: process.env.ADJUTANT_DIR || path.join(os.homedir(), '.adjutant'),
};
```

2. Create registryService (`api/src/services/registryService.ts`):
```typescript
/**
 * @fileoverview Adjutant KB registry reader
 * 
 * Reads knowledge_bases/registry.yaml from Adjutant directory instead of
 * maintaining a separate config file. This ensures Adjutant Web stays in sync
 * with Adjutant's KB list.
 */

import fs from 'fs/promises';
import path from 'path';
import yaml from 'js-yaml';
import { config } from '../config.js';
import type { KbMeta } from '../types/kb.js';

interface RegistryEntry {
  name: string;
  description: string;
  path: string;
  model?: string;
  access: 'read-only' | 'read-write';
  created?: string;
}

interface Registry {
  knowledge_bases: RegistryEntry[];
}

class RegistryService {
  private get registryPath(): string {
    return path.join(config.adjutantDir, 'knowledge_bases', 'registry.yaml');
  }
  
  async list(): Promise<KbMeta[]> {
    try {
      const content = await fs.readFile(this.registryPath, 'utf-8');
      const registry = yaml.load(content) as Registry;
      
      return registry.knowledge_bases.map(entry => ({
        name: entry.name,
        description: entry.description,
        path: entry.path,
        access: entry.access,
        created: entry.created,
      }));
    } catch (error) {
      console.error('Failed to read Adjutant registry:', error);
      return [];
    }
  }
  
  async get(name: string): Promise<KbMeta | null> {
    const kbs = await this.list();
    return kbs.find(kb => kb.name === name) || null;
  }
  
  async resolveKbPath(name: string): Promise<string | null> {
    const kb = await this.get(name);
    return kb?.path || null;
  }
}

export const registryService = new RegistryService();
```

3. Replace kbService usage with registryService:
   - Update routes to use `registryService.list()` instead of `kbService.list()`
   - Update all services to use `registryService.resolveKbPath()` instead of `kbService.resolveKbPath()`

4. Remove configService and config routes (no longer needed)

#### Task 2.2: Add Access Control Middleware (4 hours)
**Block writes to read-only KBs**

**Implementation shown in `COMPREHENSIVE_ANALYSIS.md` Section 7.5**

#### Task 2.3: Add Session Token Auth (8 hours)
**Generate token in Adjutant, validate in Adjutant Web**

**Adjutant Side** (`src/adjutant/capabilities/web/session.py`):
```python
"""
Session token generation and management for Adjutant Web web interface.

Generates a UUID session token on Adjutant Web startup and writes to:
  state/adjutant-web_session_token

The token is passed to Adjutant Web API via environment variable and validated
on every request to prevent unauthorized access.
"""

import uuid
from pathlib import Path
from adjutant.core.paths import get_adj_dir

def generate_session_token() -> str:
    """Generate a new session token (UUID v4)."""
    return str(uuid.uuid4())

def get_session_token_path() -> Path:
    """Get path to session token file."""
    return get_adj_dir() / 'state' / 'adjutant-web_session_token'

def write_session_token(token: str) -> None:
    """Write session token to state directory."""
    token_path = get_session_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token)

def read_session_token() -> str | None:
    """Read current session token, or None if not found."""
    token_path = get_session_token_path()
    if not token_path.exists():
        return None
    return token_path.read_text().strip()

def get_or_create_session_token() -> str:
    """Get existing session token or generate a new one."""
    token = read_session_token()
    if not token:
        token = generate_session_token()
        write_session_token(token)
    return token
```

**Adjutant Web Side** (`api/src/middleware/auth.ts`):
```typescript
/**
 * @fileoverview Session token authentication middleware
 * 
 * Validates Bearer token in Authorization header against the session token
 * generated by Adjutant on startup. Rejects unauthorized requests with 401.
 */

import type { Request, Response, NextFunction } from 'express';

const SESSION_TOKEN = process.env.ADJUTANT_WEB_SESSION_TOKEN;

if (!SESSION_TOKEN) {
  console.warn('ADJUTANT_WEB_SESSION_TOKEN not set - authentication disabled');
}

export function authenticate(req: Request, res: Response, next: NextFunction): void {
  if (!SESSION_TOKEN) {
    // Auth disabled, allow all requests (development mode)
    next();
    return;
  }
  
  const authHeader = req.headers.authorization;
  
  if (!authHeader) {
    res.status(401).json({ error: 'Missing Authorization header' });
    return;
  }
  
  const [scheme, token] = authHeader.split(' ');
  
  if (scheme !== 'Bearer' || token !== SESSION_TOKEN) {
    res.status(401).json({ error: 'Invalid session token' });
    return;
  }
  
  next();
}
```

Apply to all routes:
```typescript
// api/src/index.ts
import { authenticate } from './middleware/auth.js';

app.use('/api', authenticate);  // Protect all API routes
```

### Week 2-3: Adjutant CLI Integration

#### Task 2.4: Add Adjutant Web Process Management (12 hours)
**Adjutant module to start/stop Adjutant Web**

**Implementation shown in `COMPREHENSIVE_ANALYSIS.md` Section 7.2**

#### Task 2.5: Add Web CLI Commands (8 hours)
**`adjutant web start/stop/open/status`**

**Implementation shown in `COMPREHENSIVE_ANALYSIS.md` Section 7.1**

#### Task 2.6: Add Adjutant Status Widget (8 hours)
**Show Adjutant lifecycle state in Adjutant Web UI**

**API Endpoint** (`api/src/routes/adjutant.ts`):
```typescript
import { Router } from 'express';
import { exec } from 'child_process';
import { promisify } from 'util';

const router = Router();
const execAsync = promisify(exec);

router.get('/status', async (_req, res) => {
  try {
    const { stdout } = await execAsync('adjutant status --json');
    const status = JSON.parse(stdout);
    res.json(status);
  } catch (error) {
    res.status(500).json({ error: 'Failed to get Adjutant status' });
  }
});

router.post('/pause', async (_req, res) => {
  try {
    await execAsync('adjutant pause');
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Failed to pause Adjutant' });
  }
});

router.post('/resume', async (_req, res) => {
  try {
    await execAsync('adjutant resume');
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Failed to resume Adjutant' });
  }
});

export default router;
```

**Web Component** (`web/src/components/AdjutantStatus/AdjutantStatus.tsx`):
```tsx
import { useEffect, useState } from 'react';
import styles from './AdjutantStatus.module.css';

interface Status {
  state: 'OPERATIONAL' | 'PAUSED' | 'KILLED';
  uptime: string;
}

export function AdjutantStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(false);
  
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/adjutant/status');
        const data = await res.json();
        setStatus(data);
      } catch {
        setStatus(null);
      }
    };
    
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);  // Poll every 10s
    return () => clearInterval(interval);
  }, []);
  
  const handlePause = async () => {
    setLoading(true);
    try {
      await fetch('/api/adjutant/pause', { method: 'POST' });
      // Refetch status
      const res = await fetch('/api/adjutant/status');
      const data = await res.json();
      setStatus(data);
    } catch {
      alert('Failed to pause Adjutant');
    } finally {
      setLoading(false);
    }
  };
  
  const handleResume = async () => {
    setLoading(true);
    try {
      await fetch('/api/adjutant/resume', { method: 'POST' });
      const res = await fetch('/api/adjutant/status');
      const data = await res.json();
      setStatus(data);
    } catch {
      alert('Failed to resume Adjutant');
    } finally {
      setLoading(false);
    }
  };
  
  if (!status) return null;
  
  return (
    <div className={styles.status}>
      <div className={styles.indicator} data-state={status.state.toLowerCase()}>
        {status.state}
      </div>
      <div className={styles.uptime}>Uptime: {status.uptime}</div>
      {status.state === 'OPERATIONAL' ? (
        <button onClick={handlePause} disabled={loading}>Pause</button>
      ) : status.state === 'PAUSED' ? (
        <button onClick={handleResume} disabled={loading}>Resume</button>
      ) : null}
    </div>
  );
}
```

Add to Sidebar:
```tsx
// web/src/components/Sidebar/Sidebar.tsx
import { AdjutantStatus } from '../AdjutantStatus';

export function Sidebar(props) {
  return (
    <div className={styles.sidebar}>
      <AdjutantStatus />
      {/* ... rest of sidebar */}
    </div>
  );
}
```

### Deliverables

- [ ] Adjutant Web reads from Adjutant registry
- [ ] Read-only KBs enforced
- [ ] Session token authentication active
- [ ] `adjutant web` commands functional
- [ ] Adjutant status widget in UI
- [ ] All tests pass (add new tests for auth middleware, access control)
- [ ] Documentation updated
- [ ] Git tag: `v2.2.0-adjutant`

---

## Phase 3: Advanced Features (4-6 Weeks)

**Goal**: Add features that leverage Adjutant capabilities.

(Implementation details available on request — see `COMPREHENSIVE_ANALYSIS.md` Section 6.2 Phase 3)

---

## Phase 4: Multi-User Support (8-12 Weeks)

**Goal**: Enable real-time collaborative editing.

(Implementation details available on request — see `COMPREHENSIVE_ANALYSIS.md` Section 6.2 Phase 4)

---

## Success Metrics

| Metric | Phase 1 Target | Phase 2 Target | Phase 3 Target |
|--------|----------------|----------------|----------------|
| Security Audit Score | 100/100 | 100/100 | 100/100 |
| Test Coverage | ≥ 90% | ≥ 90% | ≥ 90% |
| Load Time (10 KBs) | < 1s | < 1s | < 500ms |
| Search (1000 notes) | < 500ms | < 500ms | < 100ms |
| Concurrent Users | 1 | 1 | 5 |
| Uptime | 99% | 99.9% | 99.9% |

---

## Risk Mitigation

### High-Risk Items

1. **Adjutant Integration Complexity**
   - Mitigation: Incremental integration, feature flags for rollback
   - Contingency: Keep standalone mode functional

2. **Search Performance with Large KBs**
   - Mitigation: Search indexing in Phase 3
   - Contingency: Pagination + "slow search" warning

3. **Real-Time Sync Reliability**
   - Mitigation: Extensive testing, fallback to polling
   - Contingency: Disable real-time, manual refresh

### Medium-Risk Items

1. **Browser Compatibility**
   - Mitigation: Test on Chrome, Firefox, Safari
   - Contingency: Display compatibility warning

2. **Mobile Responsiveness**
   - Mitigation: Responsive CSS, touch gesture support
   - Contingency: Desktop-only initially

---

## Communication Plan

| Stakeholder | Update Frequency | Format |
|-------------|------------------|--------|
| Development Team | Daily | Standup, Slack |
| Product Owner | Weekly | Demo + written summary |
| Users | Per Release | Changelog + migration guide |

---

**End of Implementation Roadmap**
