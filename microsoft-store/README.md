# Publishing RefPad on the Microsoft Store

Everything needed for Partner Center, ready to copy. RefPad for Windows goes to the Store as an **MSIX package**
that Microsoft signs for you, so you need **no code-signing certificate**, and Windows' "unknown publisher"
warning goes away for Store users.

| File | Use it for |
|---|---|
| `dist/RefPad-<version>.msix` | The package you upload (built in step 3) |
| `screenshots/1-board.png` … `4-board-grey.png` | Store listing → Screenshots (1602 × 932, desktop) |
| `../play-store/icon-512.png` | Store listing → Store logo, if asked (the package has its own icons) |
| `../docs/privacy-policy.html` | Privacy policy URL (the same page as for Google Play) |

The screenshots show only public-domain museum art (see `../play-store/CREDITS.md`).

**How the Store copy differs from the GitHub copy**
- It updates through the Microsoft Store. RefPad notices that it runs as a Store package and switches its own
  GitHub updater off (no update check, no *Check for updates* menu entry).
- Both copies keep the board and settings in the same place (`%LOCALAPPDATA%\RefPad`), so someone who moves
  from the GitHub version to the Store version keeps their board.
- Keep publishing GitHub releases as before for people who don't use the Store.

---

## 1. Create your developer account (once, free)

1. Go to <https://storedeveloper.microsoft.com> and choose **Individual developer**.
2. Sign in with your Microsoft account and finish the identity check (a photo ID and a selfie).
   Registration is free for individual developers (no card needed).

## 2. Reserve the name and copy the package identity (once)

1. In Partner Center: **Apps and games → New product → MSIX or PWA app**.
2. Reserve a name. Try `RefPad`; if it is taken, `RefPad – Reference Board` or `RefPad for Artists`.
3. Open the new app → **Product management → Product identity**. Copy three values into a new file
   `tools/windows/store.json` (it is git-ignored, because it holds your publisher name):

   ```json
   {
     "identity_name": "<Package/Identity/Name>",
     "publisher": "<Package/Identity/Publisher, starts with CN=>",
     "publisher_display_name": "<Package/Properties/PublisherDisplayName>",
     "display_name": "<the name you reserved>"
   }
   ```

## 3. Build the package

```bash
py -3.12 tools/build_windows.py
```

```bash
py -3.12 tools/build_msix.py
```

This writes `dist/RefPad-<version>.msix` (about 34 MB). The package version is the app version plus `.0`
(`1.3.0` → `1.3.0.0`); the Store needs a higher version for every update.

`py -3.12 tools/build_msix.py --test` builds `RefPad-<version>-TEST.msix` with placeholder values: only for
checking that packaging works. **Don't upload a TEST package.**

Optional local check (needs Windows *Developer Mode*): `Add-AppxPackage -Register build\msix\AppxManifest.xml`
installs the unpacked package for your account; start it from the Start menu, then remove it with
`Get-AppxPackage *RefPad* | Remove-AppxPackage`.

## 4. Partner Center answers

**Pricing and availability**
- Markets: all · Visibility: public · Pricing: **Free** · Free trial: none

**Properties**
- Category: **Productivity** (or *Photo & video*)
- Privacy policy URL: the same one as for Google Play, for example
  `https://<your-github-username>.github.io/REFERENCE-BOARD-/privacy-policy.html` (GitHub Pages from `/docs`)
- Website: `https://github.com/kathir262/REFERENCE-BOARD-`
- Product declarations: tick **"This app has been tested to meet accessibility guidelines"** only if you have
  checked it; leave the rest as they are.
- System requirements: keyboard and mouse recommended; touch works too.

**Age ratings** (IARC questionnaire)
- Category: *Productivity / utility*. Answer **No** to every question (no violence, no user-to-user
  communication, no purchases, no location sharing). Expected rating: *Everyone / PEGI 3*.

**Packages**
- Upload `dist/RefPad-<version>.msix`. Device family: **Desktop** only.

**Store listing (English)**
- Description:

  > RefPad keeps your references right next to your art.
  >
  > **Reference board** — Drop in pictures, folders or PDF pages and arrange them on an endless board. Zoom, move, resize, flip, rotate, crop, lock and add notes. Study values with black & white, 2–5 value steps or a squint blur, put a grid over a picture, pick colours, and export the board as a picture. Undo everything.
  >
  > **Float on top** — Turn RefPad into a small window that stays above Clip Studio Paint, Krita, Photoshop or any other app, with adjustable see-through. Pin a single picture on top of everything.
  >
  > **Gesture practice** — Timed poses from a PDF art book, a folder or your board, from 30 seconds to 10 minutes. Run a whole class (warm-up, 30 or 60 minutes, or your own), try memory mode, and follow your practice history and streak.
  >
  > **PDF reader** — Smooth scrolling and sharp zoom, even for huge books. Two pages side by side, a page list, bookmarks and text search. Snip part of a page straight onto the board.
  >
  > **Boards as files** — Keep one board per project in a .refpad file, with the pictures inside. Boards open on RefPad for Android too.
  >
  > **Free and private** — No ads, no accounts, no tracking. Your files stay on your PC.

- Short description: `Reference board, gesture timer and PDF reader for artists`
- What's new in this version: use the release notes of the version you upload.
- Product features (one per line):
  - Endless reference board with crop, notes, lock and undo
  - Value steps, squint blur, grid and colour picker
  - Floating always-on-top window
  - Timed gesture practice, classes and memory mode
  - PDF reader with two-page view, bookmarks, search and snipping
  - Boards saved as files, shared with RefPad for Android
- Screenshots: upload `screenshots/1-board.png` to `4-board-grey.png` (in that order).
- Search terms: `reference`, `gesture drawing`, `artist`, `pose`, `PDF`, `drawing reference`, `figure drawing`

**Submission options → Notes for certification**

> RefPad is a desktop (Win32, Qt) app packaged as MSIX. It needs runFullTrust like every packaged desktop app.
> No account or sign-in is needed: open RefPad, press Image to add pictures to the board, or open a PDF in the
> PDF tab. The GitHub version's own updater is switched off when RefPad runs as the Store package.

If Partner Center asks why the package uses the restricted capability **runFullTrust**, use the first sentence above.

## 5. Updating

1. Raise `__version__` in `refpad/__init__.py`.
2. Build again (step 3) and upload the new `.msix` in a new submission (*Packages*; replace the old one).
3. Publish the same version on GitHub as usual for people who use the installer.
