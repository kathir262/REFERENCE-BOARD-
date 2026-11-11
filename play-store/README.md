# Publishing RefPad on Google Play

Everything needed for the Play Console, ready to copy. RefPad is **free, with no ads, no in-app purchases,
no accounts, no analytics and no Internet permission**.

| File | Use it for |
|---|---|
| `icon-512.png` | Store listing → App icon (512 × 512) |
| `feature-graphic-1024x500.png` | Store listing → Feature graphic |
| `screenshots/1-board.png` … `4-floating-window.png` | Store listing → 7-inch and 10-inch tablet screenshots (2560 × 1440, 16:9) |
| `screenshots/phone-1-board.png` … `phone-3-pdf-reader.png` | Store listing → Phone screenshots (1440 × 2560, 9:16) |
| `CREDITS.md` | Sources of the public-domain (CC0) artworks shown in the screenshots |
| `../docs/privacy-policy.html` | Privacy policy page (must be hosted at a public URL, see step 2) |
| `android/app/build/outputs/bundle/release/app-release.aab` | The file you upload (built with `gradlew bundleRelease`) |

---

## 1. Make your private upload key (once)

The old `release.keystore` and its password are committed to GitHub, so anyone who can see the repository
has them. Use a new, private key for Google Play:

```bash
cd android
keytool -genkeypair -v -keystore upload-key.jks -alias upload -keyalg RSA -keysize 4096 -validity 10000
```

Then create `android/keystore.properties` (it is git-ignored):

```properties
storeFile=../upload-key.jks
storePassword=YOUR_PASSWORD
keyAlias=upload
keyPassword=YOUR_PASSWORD
```

**Back up `upload-key.jks` and the password somewhere safe** (not in the repo). With Play App Signing, Google
holds the real app-signing key; if you ever lose the upload key, Play support can reset it.

Note: once the app is signed with the new key, the copy on your tablet (signed with the old test key)
must be uninstalled before installing the Play version. Your board is stored inside the app, so export
anything you need first.

## 2. Host the privacy policy

1. Open `docs/privacy-policy.html` and replace `[DEVELOPER NAME]` and `[CONTACT EMAIL]` (both appear in the Contact section).
2. Push to GitHub, then on GitHub open **Settings → Pages**, choose **Deploy from a branch**, branch `main`, folder `/docs`.
3. Your policy URL will be: `https://<your-github-username>.github.io/REFERENCE-BOARD-/privacy-policy.html`

The same policy text is also inside the app (menu ⋮ → **Privacy policy**).

## 3. Build the upload file

```bash
cd android
gradlew bundleRelease
```

Upload `android/app/build/outputs/bundle/release/app-release.aab`. The build already:
- targets **Android 16 (API 36)**, which Google Play requires for new apps since 31 August 2026,
- is optimised with R8 and includes a baseline profile (Play pre-compiles the app for smooth first launch),
- is version **1.2.0 (versionCode 3)**. Increase `versionCode` in `android/app/build.gradle` for every upload.

## 4. Play Console answers

**Create app**
- App name: `RefPad: Reference Board`
- Default language: English
- App or game: **App** · Free or paid: **Free**

**App content**
- Privacy policy: your URL from step 2
- Ads: **No, my app does not contain ads**
- App access: **All functionality is available without special access**
- Content rating (IARC questionnaire): category **Utility, Productivity, Communication or other**; answer **No** to
  every question (no violence, no user-to-user sharing, no purchases, no location). Expected rating: *Everyone / PEGI 3*.
- Target audience: choose **13 and over** (choosing under-13 adds Families-programme requirements you do not need).
- News app: **No** · Government app: **No** · Financial features: **None** · Health: **None**
- Data safety:
  - Does your app collect or share any of the required user data types? **No**
  - (The form then marks the app as *No data collected* and *No data shared*.)
- Foreground service permissions → **Special use**:
  - Description: *"RefPad shows a floating reference-image window on top of drawing apps while the artist draws.
    A foreground service with a visible notification keeps this window alive when the user switches to their
    drawing app. It only runs after the user taps 'Float over other apps', and the notification lets them close it."*
  - If asked for a video: record the screen while opening RefPad → tapping the float button → switching to a
    drawing app → closing the window from the notification (Samsung screen recorder works fine).

**Store listing**
- App category: **Art & Design** · Tags: drawing, reference, art
- Short description (77 characters):

  > Reference board, gesture timer & PDF reader that floats over your drawing app

- Full description:

  > RefPad keeps your references right next to your art.
  >
  > **Reference board** — Drop in photos, folders or PDF pages and arrange them on an endless board. Pinch to zoom, drag to move, resize from the corner, flip, rotate, view in black & white, copy and paste. Your board is saved automatically.
  >
  > **Float over any drawing app** — Open the board in a small floating window on top of Clip Studio Paint, ibisPaint, Infinite Painter, Krita or any other app. Move it, resize it, make it see-through, or shrink it to a bubble.
  >
  > **Gesture practice** — Timed figure-drawing sessions from your images or a whole PDF pose book: 30 seconds to 10 minutes per pose, swipe between poses, flip and greyscale to check your drawing.
  >
  > **PDF reader** — Read art books and tutorials with smooth scrolling and sharp zoom. Even huge books open instantly because pages load as you scroll. Send any page to your board or start a practice session from it.
  >
  > **Light and private** — Completely free, no ads, no accounts, no tracking. RefPad has no Internet access, so your files never leave your tablet.

- Graphics: upload `icon-512.png` and `feature-graphic-1024x500.png`.
- Screenshots: `screenshots/1-…` to `4-…` go in the **tablet** slots and `screenshots/phone-…` in the **phone**
  slot (Play needs at least 2 phone screenshots). They use only public-domain museum art
  (see `CREDITS.md`) and deliberately avoid nudity, which Play reviews strictly even in classical art.
  Never use pages from commercial art books in store images.

## 5. Testing before production

Personal developer accounts created after November 2023 must run a **closed test with at least 12 testers for
14 days** before they can publish to production. Upload the AAB to *Testing → Closed testing*, add your testers'
Google accounts, and apply for production access after the 14 days.
