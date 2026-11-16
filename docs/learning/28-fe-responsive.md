# 28 · Phone and tablet layout (`feature/fe-responsive`)

## Layout
- **≤ 900 px:** the sidebar becomes an **off-canvas drawer** (`position: fixed` + `transform: translateX(-100%)`, slides in with a transition). A ☰ button in the header opens it; a dimmed backdrop closes it; picking or creating a chat closes it. The drawer is opaque on mobile (the desktop panel is translucent and let the chat show through).
- **Screen pinned to the viewport:** `height: 100dvh`. **dvh** (dynamic viewport height) follows mobile browser toolbars appearing/disappearing; `100vh` doesn't, which hides the input behind the toolbar. Messages scroll inside; the composer stays visible.
- **≤ 640 px:** compact header and composer (dropdowns side by side, labels hidden, Send next to the input), a smaller status pill. It's kept, because "reconnecting" matters most on mobile networks.
- **`@media (hover: none)`:** touch screens can't hover, so chat actions (rename, export, delete) are always visible there.
- The status banner only renders when there's a message.

## Two CSS bugs found from screenshots (functional checks all passed)
1. **Tables split words mid-word** ("Pyth|on"): `word-break: break-word` inherited from the message body. Table cells now use `white-space: nowrap`, and the table scrolls sideways inside its own wrapper.
2. **Mobile composer rules had no effect:** **cascade order.** With equal specificity, the rule *later in the file* wins. The base composer styles were added later in the file than the media query, so they overrode it. The phone composer block now sits at the end of `styles.css`, with a comment explaining why.

**Lesson:** for layout work, automated checks ("nothing overflows", "button visible") aren't enough. Look at the screenshot.

## Verified (Playwright, iPhone 13 emulation + desktop regression)
- **Phone:** login fits; ☰ visible, sidebar hidden; drawer opens with backdrop; new chat closes the drawer; composer and Send visible; after a wide table reply, no page overflow and the composer is still visible; backdrop tap closes; row actions visible on touch; memory drawer fits.
- **Desktop:** sidebar on the left, ☰ hidden, no overflow. No page errors.
