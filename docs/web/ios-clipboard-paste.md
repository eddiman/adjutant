# iOS Safari Clipboard Paste Issue

## Problem

Image paste from the clipboard does not work on iOS Safari when using the `navigator.clipboard.read()` API, even when called during a user-activated event (e.g., clicking a "Paste" button).

The API fails with `NotAllowedError` despite `navigator.userActivation.isActive` returning `true`.

## Root Cause

iOS Safari has stricter requirements for clipboard access than other browsers:

1. **User Activation Requirements**: The Clipboard API requires "transient user activation" - a short-lived state triggered by user interaction (click, tap, keypress). See [The User Activation API - WebKit Blog](https://webkit.org/blog/13862/the-user-activation-api/).

2. **Activation Consumption**: Some APIs "consume" the user activation, resetting the transient activation timer. Once consumed, subsequent API calls requiring activation will fail.

3. **iOS-Specific Behavior**: Even with valid user activation, `navigator.clipboard.read()` for images fails on iOS Safari. The activation chain appears to break between the menu click and the async clipboard read.

4. **URI Instead of Blob**: When copying images on iOS (e.g., from Photos app), the clipboard often contains `text/uri-list` (a URL reference to the image) rather than raw image blob data.

## Solution

The fix involves two parts:

### 1. Native Paste UI Approach

Instead of programmatically reading the clipboard, we trigger iOS's native paste popup:

```typescript
// Position a visible input on-screen
setPasteInputPosition({ x: screenPos.x, y: screenPos.y, visible: true });

// Focus and select the input
pasteTargetRef.current.focus();
pasteTargetRef.current.select();

// iOS shows native "Paste" popup - user taps it
// This triggers a paste event with clipboardData
```

The input must be:
- Positioned on-screen (not at `-9999px`)
- Large enough for iOS to show the paste popup
- Visible (opacity > 0)

### 2. Handle `text/uri-list`

When iOS provides a URL instead of image data, fetch the image:

```typescript
const uriList = e.clipboardData?.getData('text/uri-list');
if (uriList) {
  const urls = uriList.split('\n').filter(url => url.trim() && !url.startsWith('#'));
  const imageUrl = urls.find(url => 
    /\.(jpg|jpeg|png|gif|webp|heic|heif)(\?|$)/i.test(url) ||
    url.includes('image') ||
    url.startsWith('data:image/')
  ) || urls[0];
  
  if (imageUrl) {
    fetch(imageUrl)
      .then(response => response.blob())
      .then(blob => {
        const file = new File([blob], 'pasted-image.png', { type: blob.type });
        onImagePaste(file, pastePosition);
      });
  }
}
```

## Key Learnings

1. **`navigator.clipboard.read()` is unreliable on iOS** for images - prefer native paste events
2. **User activation is consumed** by certain API calls - can't chain multiple activation-requiring calls
3. **iOS provides URIs, not blobs** - must fetch the image from the URL
4. **Hidden inputs don't trigger paste popup** - input must be visible and on-screen
5. **`document.execCommand('paste')` returns false** on iOS - cannot programmatically trigger paste

## References

- [The User Activation API - WebKit Blog](https://webkit.org/blog/13862/the-user-activation-api/)
- [Clipboard API - MDN](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API)
- [Activation Triggering Input Events - HTML Spec](https://html.spec.whatwg.org/#activation-triggering-input-event)

## Files Modified

- `web/src/components/Canvas.tsx` - Paste handling with iOS workarounds
