# Adjutant Web Code Paths - Complete Reference

**Date**: March 17, 2026  
**Purpose**: Document every code execution path for debugging, optimization, and onboarding

---

## Table of Contents

1. [KB Discovery](#kb-discovery)
2. [Note Operations](#note-operations)
3. [Image Operations](#image-operations)
4. [Folder Operations](#folder-operations)
5. [Canvas Rendering](#canvas-rendering)
6. [User Interactions](#user-interactions)
7. [Configuration](#configuration)

---

## 1. KB Discovery

### 1.1 List All KBs

**Trigger**: App startup, Settings dialog open, `/` home page load

**Flow**:
```
Browser
  → GET /api/kbs
    → api/src/routes/kbs.ts:6
      → kbService.list()
        → api/src/services/kbService.ts:13
          → configService.getKbRoot()
            → api/src/services/configService.ts:76
              → configService.get()
                → api/src/services/configService.ts:14
                  → fs.readFile(~/.adjutant-web/config.json)
                  → AppConfigSchema.parse()
                  → return { kbRoot }
          → fs.readdir(kbRoot, { withFileTypes: true })
          → for each directory (not starting with .):
            → kbService.parseKbYaml(kbPath)
              → api/src/services/kbService.ts:80
                → fs.readFile(kb.yaml)
                → yaml.load(content)
                → KbYamlSchema.parse(raw)
                → return KbMeta { name, description, path, access, created }
          → sort KBs by name (localeCompare)
          → return KbMeta[]
    → Response: { kbs: KbMeta[], total: number }
```

**Key Files**:
- `api/src/routes/kbs.ts`
- `api/src/services/kbService.ts`
- `api/src/services/configService.ts`
- `api/src/types/kb.ts`

**Performance**:
- Time complexity: O(N) where N = number of directories in kbRoot
- Disk I/O: N+1 reads (1 config + N kb.yaml files)
- Typical duration: 10-50ms for 10 KBs

---

## 2. Note Operations

### 2.1 Create Note

**Trigger**: Click "New Note" on canvas, placement mode → click position

**Flow**:
```
Browser
  → POST /api/notes
    Body: { kb, folder, title, content?, tags?, position? }
    → api/src/routes/notes.ts:27
      → NoteCreateSchema.parse(req.body)
        → Validate + apply defaults
        → Returns: { kb, folder: '', filename?, title, content: '', tags: [], position? }
      → fileNoteService.create(input)
        → api/src/services/fileNoteService.ts:16
          → kbService.resolveKbPath(kb)
            → Validate kb name (no .., /, \)
            → Check kb.yaml exists
            → Return absolute path
          → Path traversal check (normalized folder path)
          → fs.mkdir(absFolderPath, { recursive: true })
          → Generate filename:
            - Use input.filename if provided
            - Else: slugify(title) + '.md'
          → ensureUniqueFilename(absFolderPath, filename)
            → api/src/services/fileNoteService.ts:233
              → Loop: fs.access(candidate) → if exists, try filename-2, filename-3, etc.
              → Return unique filename
          → Build markdown content:
            - If content doesn't start with "# ", prepend "# {title}\n\n"
          → fs.writeFile(absFilePath, content)
          → Update .adjutant-web.json:
            → folderService.updateMeta(kb, folderPath, { items: { [filename]: { tags, position, title } } })
              → api/src/services/folderService.ts:77
                → Read existing sidecar
                → Merge updates
                → Write sidecar
          → fs.stat(absFilePath) → get size, mtime
          → Return NoteFile { filename, path, kb, content, title, tags, position, size, mtime }
    → Response: NoteFile (201 Created)

Frontend
  → useNotes.createNote()
    → web/src/hooks/useNotes.ts:42
      → fetch('/api/notes', { method: 'POST', body })
      → setNotes(prev => [...prev, newNote])
      → return newNote
  → refetchFolder()
    → Re-fetch folder listing to include new note
  → prepareEditorOpen(originRect, note)
    → Store animation origin + note data in EditorContext
  → setFocusedNote(notePath)
    → Open NoteEditor overlay
```

**Key Files**:
- `api/src/routes/notes.ts`
- `api/src/services/fileNoteService.ts`
- `api/src/services/folderService.ts`
- `web/src/hooks/useNotes.ts`
- `web/src/App.tsx` (handleNoteCreate)

**Edge Cases**:
- Empty title → defaults to "Untitled Note" → slugified to "untitled-note.md"
- Duplicate filename → appends -2, -3, etc.
- Invalid KB → 400 error
- Folder doesn't exist → created recursively

### 2.2 Update Note

**Trigger**: Autosave in NoteEditor (1.5s debounce)

**Flow**:
```
Browser
  → PUT /api/notes?kb=X&path=Y
    Body: { content?, title?, tags?, position?, section? }
    → api/src/routes/notes.ts:52
      → NoteUpdateSchema.parse(req.body)
      → fileNoteService.update(kb, path, input)
        → api/src/services/fileNoteService.ts:77
          → kbService.resolveKbPath(kb)
          → Path traversal check
          → fs.access(absPath) → verify file exists
          → If content provided:
            → fs.writeFile(absPath, content)
          → Update metadata in .adjutant-web.json:
            → folderService.updateMeta(kb, folderPathRel, { items: { [filename]: { title?, tags?, position?, section? } } })
          → Return updated NoteFile (calls fileNoteService.get())
    → Response: NoteFile

Frontend
  → NoteEditor autosave (1.5s debounce)
    → web/src/components/NoteEditor/NoteEditor.tsx:140
      → onSave(kb, notePath, content, title, tags)
        → App.tsx handleNoteSave()
          → useNotes.updateNote(kb, notePath, { content, title, tags })
            → fetch('/api/notes?kb=X&path=Y', { method: 'PUT', body })
```

**Key Files**:
- `api/src/routes/notes.ts`
- `api/src/services/fileNoteService.ts`
- `web/src/components/NoteEditor/NoteEditor.tsx`
- `web/src/hooks/useNotes.ts`

**Edge Cases**:
- Empty content → writes empty file
- Section = null → removes section reference
- File deleted externally → 404 error

### 2.3 Delete Note

**Trigger**: Delete button in NoteEditor, context menu → Delete

**Flow**:
```
Browser
  → DELETE /api/notes?kb=X&path=Y
    → api/src/routes/notes.ts:71
      → fileNoteService.delete(kb, path)
        → api/src/services/fileNoteService.ts:121
          → kbService.resolveKbPath(kb)
          → Path traversal check
          → fs.unlink(absPath) → delete file
          → Remove metadata from .adjutant-web.json:
            → folderService.removeItemMeta(kb, folderPathRel, filename)
              → api/src/services/folderService.ts:97
                → Read sidecar
                → delete meta.items[itemName]
                → Write sidecar
          → return true
    → Response: 204 No Content

Frontend
  → onDelete(kb, notePath)
    → App.tsx handleNoteDelete()
      → useNotes.deleteNote(kb, notePath)
        → fetch('/api/notes?kb=X&path=Y', { method: 'DELETE' })
      → setFocusedNote(null)
      → clearEditorState()
      → refetchFolder()
```

**Key Files**:
- `api/src/routes/notes.ts`
- `api/src/services/fileNoteService.ts`
- `api/src/services/folderService.ts`
- `web/src/components/NoteEditor/NoteEditor.tsx`
- `web/src/hooks/useNotes.ts`

### 2.4 Search Notes

**Trigger**: Home page search bar, cross-KB search

**Flow**:
```
Browser
  → GET /api/notes/search?kb=X&q=query
    → api/src/routes/notes.ts:87
      → fileNoteService.search(kb, query)
        → api/src/services/fileNoteService.ts:194
          → kbService.resolveKbPath(kb)
          → queryLower = query.toLowerCase()
          → searchRecursive(kbRoot, kbRoot, kb, queryLower, results)
            → api/src/services/fileNoteService.ts:254
              → fs.readdir(dirPath, { withFileTypes: true })
              → folderService.getMeta(kb, folderPath)
              → for each entry:
                - If directory: recurse
                - If .md file:
                  → nameMatch = entry.name.includes(query)
                  → If not nameMatch:
                    → fs.readFile(entryPath) → content
                    → contentMatch = content.includes(query)
                  → If nameMatch OR contentMatch:
                    → fs.stat(entryPath) → size, mtime
                    → Extract metadata from sidecar
                    → results.push(NoteMeta)
          → return results[]
    → Response: { results: NoteMeta[], total: number }

Frontend (cross-KB search)
  → Home.tsx search input (debounced 300ms)
    → web/src/components/Home/Home.tsx:40
      → searchNotes(query)
        → useNotes.searchNotes(query)
          → web/src/hooks/useNotes.ts:84
            → for each KB:
              → fetch(`/api/notes/search?kb=${kb.name}&q=${query}`)
            → Aggregate results from all KBs
            → Deduplicate by path
            → Return combined results
```

**Key Files**:
- `api/src/routes/notes.ts`
- `api/src/services/fileNoteService.ts`
- `web/src/components/Home/Home.tsx`
- `web/src/hooks/useNotes.ts`

**Performance**:
- Time complexity: O(N * M) where N = number of files, M = average file size
- Disk I/O: N reads (all .md files)
- Typical duration: 10-50ms for 100 notes, 100-500ms for 1000 notes

---

## 3. Image Operations

### 3.1 Upload Image

**Trigger**: Paste image in NoteEditor, drop image on canvas, upload button

**Flow**:
```
Browser
  → POST /api/assets/upload
    Body: multipart/form-data { image: File, kb: string }
    → api/src/routes/assets.ts:23
      → multer.single('image')
        → Parses multipart, stores in memory (max 10MB)
        → req.file = { buffer, originalname, mimetype }
      → ZodSchema.parse(req.body) → validate kb
      → imageService.processAndSave(req.file.buffer, req.file.originalname, kb)
        → api/src/services/imageService.ts:39
          → resolveAssetsDir(kb)
            → kbService.resolveKbPath(kb)
            → assetsDir = <kb>/.adjutant-web/assets/
            → fs.mkdir(assetsDir, { recursive: true })
          → id = uuidv4()
          → sharp(buffer).metadata() → get width, height
          → sharp(buffer).webp({ quality: 80 }).toFile(<id>.webp)
          → sharp(buffer).resize(300, null).webp({ quality: 75 }).toFile(<id>-thumb.webp)
          → return { id, webpPath, thumbPath, width, height, kb }
      → imageService.getUrls(id, kb)
        → Build API URLs: /api/assets/{id}.webp?kb=X
      → return { id, webpUrl, thumbUrl, width, height, aspectRatio, kb }
    → Response: ImageMetadata (201 Created)

Frontend
  → Editor image paste/drop
    → web/src/components/Editor/Editor.tsx:45
      → Extract image from clipboard/dataTransfer
      → Convert to Blob
      → FormData: append('image', blob), append('kb', currentKb)
      → fetch('/api/assets/upload', { method: 'POST', body: formData })
      → Insert TipTap image node: editor.chain().setImage({ src: webpUrl })
  
  → Canvas image upload
    → web/src/hooks/useImages.ts:28
      → FormData: append('image', file), append('kb', kb)
      → fetch('/api/assets/upload', { method: 'POST', body: formData })
      → Store position in localStorage:
        - localStorage.setItem('adjutant-web-image-positions', JSON.stringify({ [id]: position }))
      → setImages(prev => [...prev, newImage])
```

**Key Files**:
- `api/src/routes/assets.ts`
- `api/src/services/imageService.ts`
- `web/src/components/Editor/Editor.tsx`
- `web/src/hooks/useImages.ts`

**Edge Cases**:
- Non-image file → Sharp throws error → 500 response
- File > 10MB → multer rejects → 413 Payload Too Large
- Invalid KB → 400 error

### 3.2 Serve Image

**Trigger**: Browser loads image node on canvas, TipTap displays image in editor

**Flow**:
```
Browser
  → GET /api/assets/{id}.webp?kb=X
    → api/src/routes/assets.ts:51
      → imageService.get(filename, kb)
        → api/src/services/imageService.ts:70
          → resolveAssetsDir(kb)
          → base = path.basename(filename) → prevent path traversal
          → filePath = path.join(assetsDir, base)
          → fs.readFile(filePath) → buffer
          → return { buffer, contentType: 'image/webp' }
      → Set cache headers:
        - Cache-Control: public, max-age=31536000, immutable (1 year)
      → res.set('Content-Type', 'image/webp')
      → res.send(buffer)
```

**Key Files**:
- `api/src/routes/assets.ts`
- `api/src/services/imageService.ts`

### 3.3 Delete Image

**Trigger**: Context menu → Delete, Delete key on selected image node

**Flow**:
```
Browser
  → DELETE /api/assets/{id}?kb=X
    → api/src/routes/assets.ts:86
      → imageService.delete(id, kb)
        → api/src/services/imageService.ts:89
          → resolveAssetsDir(kb)
          → fs.readdir(assetsDir)
          → matchingFiles = files.filter(f => f.startsWith(id))
            → Matches: {id}.webp, {id}-thumb.webp
          → for each matchingFile:
            → fs.unlink(path.join(assetsDir, file))
          → return true
    → Response: 204 No Content

Frontend
  → useImages.deleteImage(id)
    → web/src/hooks/useImages.ts:54
      → fetch(`/api/assets/${id}?kb=${kb}`, { method: 'DELETE' })
      → setImages(prev => prev.filter(img => img.id !== id))
      → (BUG: doesn't clean up localStorage positions)
```

**Key Files**:
- `api/src/routes/assets.ts`
- `api/src/services/imageService.ts`
- `web/src/hooks/useImages.ts`

---

## 4. Folder Operations

### 4.1 List Folder Contents

**Trigger**: Navigate to KB/folder in sidebar, URL change to `/:kb/:path`

**Flow**:
```
Browser
  → GET /api/folders?kb=X&path=Y
    → api/src/routes/folders.ts:12
      → folderService.list(kb, path)
        → api/src/services/folderService.ts:14
          → resolveFolder(kb, path)
            → kbService.resolveKbPath(kb)
            → Normalize + validate path (prevent traversal)
            → Check directory exists
            → Return absolute path
          → fs.readdir(absPath, { withFileTypes: true })
          → for each entry (skip hidden):
            - If directory: entries.push({ name, type: 'folder' })
            - If file: entries.push({ name, type: 'file', size, mtime })
          → Sort: folders first, then files, alphabetically
          → readSidecar(absPath)
            → api/src/services/folderService.ts:225
              → fs.readFile(.adjutant-web.json)
              → Adjutant WebSidecarSchema.parse(JSON.parse(content))
              → If error: return defaults { items: {}, sections: {}, stickies: {}, nextSectionId: 1, nextStickyId: 1 }
          → return { kb, path, entries, meta }
    → Response: FolderListing

Frontend
  → useFolder({ kb, path })
    → web/src/hooks/useFolder.ts:20
      → fetch(`/api/folders?kb=${kb}&path=${path}`)
      → setEntries(data.entries)
      → setMeta(data.meta)
      → Extract sections, stickies from meta
```

**Key Files**:
- `api/src/routes/folders.ts`
- `api/src/services/folderService.ts`
- `web/src/hooks/useFolder.ts`

### 4.2 Update Sidecar Metadata

**Trigger**: Drag note on canvas, resize section, edit sticky text

**Flow**:
```
Browser
  → PUT /api/folders/meta?kb=X&path=Y
    Body: { items?, sections?, stickies?, nextSectionId?, nextStickyId? }
    → api/src/routes/folders.ts:37
      → folderService.updateMeta(kb, path, req.body)
        → api/src/services/folderService.ts:77
          → resolveFolder(kb, path)
          → readSidecar(absPath) → existing
          → Merge updates:
            - items: { ...existing.items, ...update.items }
            - sections: { ...existing.sections, ...update.sections }
            - stickies: { ...existing.stickies, ...update.stickies }
            - nextSectionId: update.nextSectionId ?? existing.nextSectionId
            - nextStickyId: update.nextStickyId ?? existing.nextStickyId
          → writeSidecar(absPath, merged)
            → api/src/services/folderService.ts:236
              → fs.writeFile(.adjutant-web.json, JSON.stringify(data, null, 2))
          → return merged
    → Response: Adjutant WebSidecar

Frontend
  → useFolder.updateItemPosition(name, position)
    → web/src/hooks/useFolder.ts:62
      → Optimistic update: setMeta(prev => { ...prev, items: { ...prev.items, [name]: { ...prev.items[name], position } } })
      → Debounced API call (300ms): fetch('/api/folders/meta', { method: 'PUT', body })
```

**Key Files**:
- `api/src/routes/folders.ts`
- `api/src/services/folderService.ts`
- `web/src/hooks/useFolder.ts`

### 4.3 Create Section

**Trigger**: Placement mode (press S) → click position on canvas

**Flow**:
```
Browser
  → POST /api/folders/sections?kb=X&path=Y
    Body: { name?, position?, width?, height?, color? }
    → api/src/routes/folders.ts:57
      → folderService.createSection(kb, path, req.body)
        → api/src/services/folderService.ts:111
          → resolveFolder(kb, path)
          → readSidecar(absPath) → meta
          → id = `section-${meta.nextSectionId}`
          → section = {
              name: input.name || 'Section',
              position: input.position,
              width: input.width || 500,
              height: input.height || 400,
              color: input.color,
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString()
            }
          → meta.sections[id] = section
          → meta.nextSectionId++
          → writeSidecar(absPath, meta)
          → return { id, section }
    → Response: { id, section } (201 Created)

Frontend
  → useFolder.createSection({ position })
    → web/src/hooks/useFolder.ts:89
      → Optimistic update: setSections(prev => ({ ...prev, [tempId]: section }))
      → fetch('/api/folders/sections', { method: 'POST', body })
      → Replace tempId with real ID from response
```

**Key Files**:
- `api/src/routes/folders.ts`
- `api/src/services/folderService.ts`
- `web/src/hooks/useFolder.ts`

### 4.4 Delete Section

**Trigger**: Context menu → Delete, Delete key on selected section

**Flow**:
```
Browser
  → DELETE /api/folders/sections?kb=X&path=Y&id=section-1
    → api/src/routes/folders.ts:80
      → folderService.deleteSection(kb, path, id)
        → api/src/services/folderService.ts:136
          → resolveFolder(kb, path)
          → readSidecar(absPath) → meta
          → If section doesn't exist: return false
          → delete meta.sections[id]
          → Clear section references from items:
            - for each item in meta.items:
              → if item.section === id: delete item.section
          → writeSidecar(absPath, meta)
          → return true
    → Response: 204 No Content

Frontend
  → useFolder.deleteSection(id)
    → web/src/hooks/useFolder.ts:121
      → Optimistic update: setSections(prev => { const next = {...prev}; delete next[id]; return next })
      → fetch('/api/folders/sections?id=${id}', { method: 'DELETE' })
```

**Key Files**:
- `api/src/routes/folders.ts`
- `api/src/services/folderService.ts`
- `web/src/hooks/useFolder.ts`

---

## 5. Canvas Rendering

### 5.1 Build Canvas Nodes

**Trigger**: Folder data loaded, notes/sections/stickies/images fetched

**Flow**:
```
App.tsx
  → useFolder({ kb, path })
    → Returns: { entries, meta, sections, stickies }
  → useImages({ kb })
    → Returns: { images }
  
  → Build canvasNotes (useMemo)
    → web/src/App.tsx:84
      → Filter entries: type === 'file' && name.endsWith('.md')
      → Map to NoteFile:
        - filename = entry.name
        - path = currentPath ? `${currentPath}/${entry.name}` : entry.name
        - itemMeta = meta.items[entry.name] || {}
        - title = itemMeta.title || entry.name.replace(/\.md$/, '')
        - tags = itemMeta.tags || []
        - position = itemMeta.position
        - section = itemMeta.section
        - size = entry.size || 0
        - mtime = entry.mtime || ''
  
  → Pass to Canvas component:
    - notes: canvasNotes
    - images: images
    - sections: sections
    - stickies: stickies
```

### 5.2 React Flow Node Rendering

**Flow**:
```
Canvas.tsx
  → web/src/components/Canvas/Canvas.tsx:40
    → Build React Flow nodes:
      - For each note:
        → { id: `note-${filename}`, type: 'note', position, data: { filename, title, tags, section } }
      - For each image:
        → { id: `image-${id}`, type: 'image', position, data: { id, webpUrl, thumbUrl, width, height } }
      - For each section:
        → { id: sectionId, type: 'section', position, data: { name, color, width, height } }
      - For each sticky:
        → { id: stickyId, type: 'sticky', position, data: { text, color } }
  
  → ReactFlow component:
    → nodes={reactFlowNodes}
    → nodeTypes={ note: NoteNode, image: ImageNode, section: SectionNode, sticky: StickyNode }
    → onNodeDragStop={handleNodeDragStop}
    → onNodeClick={handleNodeClick}
    → onNodeDoubleClick={handleNodeDoubleClick}
  
  → React Flow renders custom node components:
    - NoteNode.tsx: Title + markdown preview
    - ImageNode.tsx: <img> + resize handle
    - SectionNode.tsx: Rectangle + label + resize handles
    - StickyNode.tsx: Colored square + contentEditable text
```

**Key Files**:
- `web/src/App.tsx` (canvasNotes building)
- `web/src/components/Canvas/Canvas.tsx` (React Flow setup)
- `web/src/components/nodes/NoteNode.tsx`
- `web/src/components/nodes/ImageNode.tsx`
- `web/src/components/nodes/SectionNode.tsx`
- `web/src/components/nodes/StickyNode.tsx`

---

## 6. User Interactions

### 6.1 Drag Node on Canvas

**Trigger**: Mouse down on node → drag → mouse up

**Flow**:
```
Canvas.tsx
  → onNodeDragStart={(event, node) => handleNodeDragStart(event, node)}
    → useCanvasNodeDrag.handleNodeDragStart()
      → web/src/hooks/useCanvasNodeDrag.ts:20
        → If node not selected: setSelectedNodes([node.id])
        → Store initial positions in ref
  
  → onNodeDrag={(event, node) => handleNodeDrag(event, node)}
    → useCanvasNodeDrag.handleNodeDrag()
      → web/src/hooks/useCanvasNodeDrag.ts:28
        → Calculate snap guides (8px threshold)
        → Update node position in local state
  
  → onNodeDragStop={(event, node) => handleNodeDragStop(event, node)}
    → useCanvasNodeDrag.handleNodeDragStop()
      → web/src/hooks/useCanvasNodeDrag.ts:40
        → Detect section membership:
          - If node center is inside section bounds:
            → Assign node to section
        → Persist position (debounced 300ms):
          - If note: onNotePositionChange(nodeId, position)
            → App.tsx handleItemPositionChange()
              → useFolder.updateItemPosition(filename, position)
                → PUT /api/folders/meta
          - If image: onImagePositionChange(id, position)
            → localStorage.setItem('adjutant-web-image-positions', ...)
          - If section: onSectionPositionChange(id, position)
            → useFolder.updateSection(id, { position })
              → PUT /api/folders/meta
          - If sticky: onStickyPositionChange(id, position)
            → useFolder.updateSticky(id, { position })
              → PUT /api/folders/meta
```

**Key Files**:
- `web/src/hooks/useCanvasNodeDrag.ts`
- `web/src/components/Canvas/Canvas.tsx`
- `web/src/App.tsx`

### 6.2 Open Note Editor

**Trigger**: Double-click note on canvas, sidebar → click note, Enter key on selected note

**Flow**:
```
Canvas.tsx
  → onNodeDoubleClick={(event, node) => {
      if (node.type === 'note') {
        onNoteOpen(notePath, getBoundingClientRect(node));
      }
    }}
    → App.tsx handleNoteOpen()
      → web/src/App.tsx:107
        → getNote(kb, notePath)
          → useNotes.getNote()
            → GET /api/notes?kb=X&path=Y
            → fileNoteService.get()
            → Return NoteFile (with full content)
        → prepareEditorOpen(rect, note)
          → EditorContext.prepareEditorOpen()
            → web/src/contexts/EditorContext.tsx:20
              → setOriginRect(rect) → for animation
              → setInitialNoteForEditor(note) → pre-load data
        → setFocusedNote(notePath)
          → Canvas.tsx useCanvas()
            → Navigate to `/:kb/:path?note=filename`

App.tsx
  → {focusedNote && currentKb && (
      <NoteEditor
        kb={currentKb}
        notePath={focusedNote}
        originRect={originRect}
        initialNote={initialNoteForEditor}
        onClose={handleNoteClose}
        onSave={handleNoteSave}
        onDelete={handleNoteDelete}
        getNote={getNote}
      />
    )}

NoteEditor.tsx
  → web/src/components/NoteEditor/NoteEditor.tsx
    → useEffect: Load note if not pre-loaded
    → Expand animation: transform from originRect to full-screen
    → TipTap Editor: initialContent = note.content
    → Autosave: debounce 1.5s after content change
      → onSave(kb, notePath, content, title, tags)
        → PUT /api/notes
```

**Key Files**:
- `web/src/components/Canvas/Canvas.tsx`
- `web/src/App.tsx`
- `web/src/contexts/EditorContext.tsx`
- `web/src/components/NoteEditor/NoteEditor.tsx`
- `web/src/hooks/useNotes.ts`

### 6.3 Keyboard Shortcuts

**Trigger**: Keydown event on canvas

**Flow**:
```
Canvas.tsx
  → useCanvasKeyboard({ selectedNodes, ... })
    → web/src/hooks/useCanvasKeyboard.ts:20
      → useEffect: addEventListener('keydown', handleKeyDown)
      
      → handleKeyDown(event)
        - Cmd/Ctrl+Z: undo()
        - Cmd/Ctrl+Shift+Z: redo()
        - Cmd/Ctrl+C: copy selected nodes
          → useCanvasClipboard.copyToClipboard()
            → Serialize nodes to JSON
            → navigator.clipboard.writeText()
        - Cmd/Ctrl+V: paste nodes
          → useCanvasClipboard.pasteFromClipboard()
            → navigator.clipboard.readText()
            → Deserialize JSON
            → Create new nodes at offset position
        - Delete/Backspace: delete selected nodes
          → onNotesDelete(noteIds)
          → onImagesDelete(imageIds)
          → onSectionsDelete(sectionIds)
          → onStickiesDelete(stickyIds)
        - Escape: clear selection, exit placement mode
          → setSelectedNodes([])
          → exitPlacementMode()
        - S: enter section placement mode
          → onEnterPlacementMode('section')
        - T: enter sticky placement mode
          → onEnterPlacementMode('sticky')
        - Enter (on selected note): open note
          → onNoteOpen(notePath, rect)
```

**Key Files**:
- `web/src/hooks/useCanvasKeyboard.ts`
- `web/src/hooks/useCanvasClipboard.ts`
- `web/src/hooks/useCanvasHistory.ts`

### 6.4 Context Menu

**Trigger**: Right-click on canvas/node, long-press on touch device

**Flow**:
```
Canvas.tsx
  → onContextMenu={(event) => {
      event.preventDefault();
      const { clientX, clientY } = event;
      const position = screenToFlowPosition({ x: clientX, y: clientY });
      showContextMenu({ x: clientX, y: clientY }, position);
    }}

  → useCanvasContextMenu({ ... })
    → web/src/hooks/useCanvasContextMenu.tsx:20
      → Build menu items based on target:
        - Canvas:
          → "Add Note Here"
          → "Add Section"
          → "Add Sticky"
        - Note:
          → "Open"
          → "Duplicate"
          → "Delete"
        - Section:
          → "Rename"
          → "Change Color" (submenu)
          → "Delete"
        - Sticky:
          → "Change Color" (submenu)
          → "Delete"
        - Image:
          → "Duplicate"
          → "Delete"
        - Multi-selection:
          → "Delete All"

ContextMenu.tsx
  → web/src/components/ContextMenu/ContextMenu.tsx
    → Render menu at click position
    → Handle item clicks:
      - Execute action
      - Close menu
```

**Key Files**:
- `web/src/hooks/useCanvasContextMenu.tsx`
- `web/src/components/ContextMenu/ContextMenu.tsx`
- `web/src/components/Canvas/Canvas.tsx`

---

## 7. Configuration

### 7.1 Set KB Root

**Trigger**: Settings dialog → Browse → select folder

**Flow**:
```
SettingsDialog.tsx
  → web/src/components/SettingsDialog/SettingsDialog.tsx:40
    → handleBrowse()
      → fetch('/api/config/browse', { method: 'POST' })
        → api/src/routes/config.ts:32
          → Detect platform
          → If macOS:
            → exec('osascript -e "choose folder"')
            → Wait for user selection
            → Return selected path
          → If Linux:
            → exec('zenity --file-selection --directory')
        → Response: { path, cancelled }
      
      → If not cancelled:
        → handleKbRootSave(selectedPath)
          → fetch('/api/config', { method: 'PUT', body: { kbRoot: path } })
            → api/src/routes/config.ts:18
              → configService.update({ kbRoot: path })
                → Validate directory exists
                → Validate contains at least one KB
                → Write to ~/.adjutant-web/config.json
          → onKbRootSaved() → refetch KB list
```

**Key Files**:
- `web/src/components/SettingsDialog/SettingsDialog.tsx`
- `api/src/routes/config.ts`
- `api/src/services/configService.ts`

---

## Summary

This document provides a complete reference for all major code paths in Adjutant Web. Use it to:
- Debug issues by tracing execution flow
- Identify performance bottlenecks
- Understand component interactions
- Onboard new developers

**Maintenance**: Update this document when adding new features or refactoring existing flows.
