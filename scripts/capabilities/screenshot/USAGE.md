# Screenshot capability — usage notes

## Cookie banner dismissal
`playwright_screenshot.mjs` automatically dismisses cookie banners by scanning all frames for common accept button labels (NO + EN). No manual intervention needed.

## Behavior when sending screenshots

- **Just take and send the screenshot.** Don't add an unsolicited summary of what's on the page.
- **If the user explicitly asks** "what are the headlines?" / "what's on this page?" — then describe the content.
- **Photo caption context:** When summarizing a screenshot, frame the response as a direct answer to what was asked — not a generic description of the page. E.g. if the user asked "go to aftenbladet.no", just send the screenshot. If they asked "what are the top stories?", answer that question specifically.
