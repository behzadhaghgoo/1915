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
- **Not in SF?** Teleport to the Palace of Fine Arts, the Ferry Building, Market & 4th, Mission Dolores or Crissy Field. Without a camera, a present-day photo of the Palace stands in for the live view.

No build step, no backend: one `index.html`, a 2 MB JSON index, and images served from the archive.

## Run it

```
python3 -m http.server 8000
```

Camera, GPS and compass need HTTPS (or localhost), so test on a phone through GitHub Pages or a tunnel.

## Data and credits

- Photographs: San Francisco Historical Photograph Collection, San Francisco Public Library. Geocoding and image hosting by [OldSF](https://www.oldsf.org) (Dan Vanderkam), whose `lat-lons.js` and `by-location/*.json` files were merged into `data/photos.json` (`[id, lat, lon, yearFrom, yearTo, title, width, height]`).
- Present-day Palace of Fine Arts photo: Carol M. Highsmith, Library of Congress (public domain).
- Facts in the narration: National Park Service (Golden Gate NRA), the Palace of Fine Arts history page, and Wikipedia's Panama-Pacific International Exposition article.

## Ideas for the weekend

- Align the archive photo to the live frame with feature matching instead of a full-screen overlay.
- Fill the gaps between photos with a labeled AI reconstruction of the missing parts of the frame.
- Add other city archives (OldNYC uses the same format).

Built for Cal Hacks 13.0 at the Palace of Fine Arts.
