# Street Smart comparison investigation

## Status

The supplied `streetsmart.cyclomedia.com.har` was not present in the workspace or Downloads during this investigation. The notes below combine the request's HAR observations with direct endpoint checks and Cyclomedia's public Recording Locations Service documentation. No HAR credential, browser cookie, captured API key, or recording ID is stored in the project.

## Authentication boundary

Cyclomedia documents the Recording Locations Service at:

`https://atlasapi.cyclomedia.com/api/recording/wfs`

The service requires Basic Authentication or OAuth. Direct unauthenticated requests from this environment returned HTTP 401 for both the WFS and the supplied panorama tile pattern. Being signed into Street Smart in Chrome does not give the Django process Chrome's cookies or in-memory authorization state.

The standalone proof of concept therefore accepts only one of these explicit, legitimate inputs at runtime:

- `CYCLOMEDIA_BEARER_TOKEN` for a short-lived OAuth token.
- `CYCLOMEDIA_USERNAME` and `CYCLOMEDIA_PASSWORD` for an approved Cyclomedia integration account.

It does not scrape browser storage, copy HAR tokens, or attempt to reproduce a browser-only login flow. Until Cyclomedia confirms an approved server-to-server credential flow or the missing HAR documents a supported exchange, the Django app should fail closed with `StreetSmartAuthError` and keep the assessor image usable.

## Requests mapped so far

1. Street Smart navigation accepts an address or coordinate in `q`.
2. The recording search is a WFS `GetFeature` request using a spatial `DWithin` filter around an EPSG:3857 point.
3. Recording metadata includes `imageId`, `recordedAt`, location, orientation, `recorderDirection`, authorization state, product type, and panorama tile schema.
4. Panorama tiles follow the observed pattern `/image/panorama/tiles/Tile/{imageId}/{zoom}/{face}/{x}/{y}`. The supplied observations indicate zoom 2, a 3x3 grid, and 512px tiles.
5. The supplied observations are not enough to prove how `F/R/B/L/U/D` map to recorder-forward and compass headings. The POC keeps that mapping explicit and reports a provisional warning instead of silently treating `F` as forward.

## Proof of concept

Run `scripts/streetsmart_poc.py`. It converts parcel coordinates to EPSG:3857, searches nearby recordings, prefers an authorized Cyclorama with the newest timestamp and shortest distance, calculates the parcel bearing, fetches the selected cube face, projects it to a normal rectangular JPEG, and prints the recording ID/date.

The current environment can validate the no-credential failure path only. A complete image test requires an approved Cyclomedia token or Basic Auth credentials and the missing HAR (or another authoritative confirmation of face orientation and request headers).

## Integration gate

Do not integrate this into the Photo Compare modal until the POC produces a visually correct image for a real Skagit parcel. Once authenticated and verified, the Django integration can cache generated files by parcel and recording ID/date, then render the assessor image and generated Street Smart image side by side.

References: [Cyclomedia Recording Locations Service](https://developer.cyclomedia.com/our-apis/recording-locations-service/), [Cyclomedia Panorama Rendering API](https://developer.cyclomedia.com/our-apis/panorama-rendering-api).
