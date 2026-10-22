# 1915

**Point your phone at San Francisco and see the same spot a hundred years ago.**

1915 drops 13,256 historical photographs from the San Francisco Public Library onto the city map. Open it on your phone, look around, and the archive photo of whatever is in front of you fades in over your live camera. Drag across the screen to wipe between then and now.

It is named for the Panama-Pacific International Exposition, the 1915 world's fair held on 636 acres of filled bay shore in what is now the Marina. The Palace of Fine Arts is the only building from the fair still standing, and about a hundred of the library's photos were taken right around its lagoon.

**Live:** https://behzadhaghgoo.github.io/1915/

## How it works

- **Where you are and where you're facing.** GPS gives position; the compass (`webkitCompassHeading` on iOS, `deviceorientationabsolute` elsewhere) gives heading.
- **What's in front of you.** Every photo has the location of its subject. 1915 computes distance and bearing to each one and ranks photos inside a 70 degree view cone first, then by distance. Turn around and the photo changes.
- **Then and now.** The archive photo sits over the rear camera feed with a draggable wipe. A small radar shows where the other photos around you are.
- **Narration.** Five photos at the Palace of Fine Arts have recorded narration (ElevenLabs). Every other photo can be read aloud with the browser's speech engine.
- **Map.** Every photo location on a dark street map, sized by how many photos were taken there and filtered by era. Tap a spot to preview its photos, then "Look from here" to stand there.
- **Camera.** The compass permission is requested first (iOS needs it from the tap), then the camera, then location. If the camera fails, the app says why (blocked, none found, busy) with a one-tap retry instead of silently falling back.
- **Not in SF?** Teleport to the Palace of Fine Arts, the Ferry Building, Market & 4th, Mission Dolores or Crissy Field. Without a camera, the present-day side is the official Google Street View panorama nearest the photo, turned to face it, with its capture date; drag that side to look around.

No build step, no backend: one `index.html` (plus Leaflet from a CDN), a 2 MB JSON index, and images served from the archive.

## Run it

```
python3 -m http.server 8000
```

Camera, GPS and compass need HTTPS (or localhost), so test on a phone through GitHub Pages or a tunnel.

## Data and credits

- Photographs: San Francisco Historical Photograph Collection, San Francisco Public Library. Geocoding and image hosting by [OldSF](https://www.oldsf.org) (Dan Vanderkam), whose `lat-lons.js` and `by-location/*.json` files were merged into `data/photos.json` (`[id, lat, lon, yearFrom, yearTo, title, width, height]`).
- Present-day views: Google Street View, embedded through Google's standard Maps embed. `data/streetview.json` maps each photo location to the nearest official Google panorama (Street View car imagery only, user-uploaded 360s excluded): `[panoId, lat, lon, headingToSubject, captureDate]`. It covers 2,125 of the 2,133 locations and was built offline with the `streetlevel` Python package. The Palace lagoon uses a hand-picked viewpoint across the water to the rotunda.
- Facts in the narration: National Park Service (Golden Gate NRA), the Palace of Fine Arts history page, and Wikipedia's Panama-Pacific International Exposition article.

## Ideas for the weekend

- Align the archive photo to the live frame with feature matching instead of a full-screen overlay.
- Fill the gaps between photos with a labeled AI reconstruction of the missing parts of the frame.
- Add other city archives (OldNYC uses the same format).

Built for Cal Hacks 13.0 at the Palace of Fine Arts.

## Same camera angle, today

For each archive photo, `rephoto.py` finds where the photographer stood and how they framed the shot, then shows the modern Street View from that exact angle.

1. Candidates: every official Google panorama within 150 m (Street View car imagery only).
2. Coarse search: DINOv2 similarity between the (grayscale) archive photo and perspective crops of each panorama every 20°.
3. Fine match: DISK features + LightGlue on the best crops at three fields of view; MAGSAC homography.
4. Solve: the homography maps the photo's center and edges to rays in the panorama, giving heading, pitch and horizontal field of view; refined twice.
5. Accept only with 40+ geometric inliers. Results: `data/rephoto.json` = `{photoId: [panoId, lat, lon, heading, pitch, hfov, inliers, date]}`.

In the app, the embed is zoomed so its focal length matches the archive photo as displayed (`object-fit: cover`): Google's embed uses focal = width/2 · 2^(zoom−1). Matched photos show “same angle”; the rest fall back to the nearest panorama, labeled “not matched”. The matcher runs in the background and keeps adding photos.
