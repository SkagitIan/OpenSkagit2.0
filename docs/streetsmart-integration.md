# Street Smart comparison investigation

## Status

The supplied `streetsmart.cyclomedia.com.har` was not present in the workspace or Downloads during this investigation. The notes below combine the request's HAR observations with direct endpoint checks and Cyclomedia's public Recording Locations Service documentation. No HAR credential, browser cookie, captured API key, or recording ID is stored in the project.

## Authentication boundary

Cyclomedia documents the Recording Locations Service at:

`https://atlasapi.cyclomedia.com/api/recording/wfs`

The service requires Basic Authentication or OAuth. Direct unauthenticated requests from this environment returned HTTP 401 for both the WFS and the supplied panorama tile pattern. Being signed into Street Smart in Chrome does not give the Django process Chrome's cookies or in-memory authorization state. Two tabs in the same Chrome session help only if the browser itself makes the cross-origin request and Cyclomedia permits credentialed CORS; they do not make browser cookies available to a Railway/Django request.

The HAR adds a browser OAuth detail: Street Smart exchanges an Authorization Code + PKCE verifier at `https://identity.cyclomedia.com/connect/token` using the public client ID and login redirect. The resulting OAuth token is not the same thing as the Atlas `apiKey` query parameter observed on WFS and tile requests. The Atlas key is an integration credential and must be provisioned through Cyclomedia; it is not derived safely from the redacted HAR value.

The standalone proof of concept therefore accepts only one of these explicit, legitimate inputs at runtime:

- `CYCLOMEDIA_BEARER_TOKEN` for a short-lived OAuth token.
- `CYCLOMEDIA_USERNAME` and `CYCLOMEDIA_PASSWORD` for an approved Cyclomedia integration account.
- `CYCLOMEDIA_API_KEY` for an approved Atlas/Street Smart integration key.

It does not scrape browser storage, copy HAR tokens, or attempt to reproduce a browser-only login flow. The POC exposes an in-memory `exchange_authorization_code()` helper for a caller that already owns a fresh PKCE code; it does not persist tokens. Until Cyclomedia confirms an approved server-to-server credential flow, or we implement a first-party OAuth redirect for the routing app with approved CORS/API-key terms, the Django app should fail closed with `StreetSmartAuthError` and keep the assessor image usable.

## Requests mapped so far

1. Street Smart navigation accepts an address or coordinate in `q`.
2. The recording search is a WFS `GetFeature` request using a spatial `DWithin` filter around an EPSG:3857 point.
3. Recording metadata includes `imageId`, `recordedAt`, location, orientation, `recorderDirection`, authorization state, product type, and panorama tile schema. The supplied WFS payload uses XML `GetFeature`, `typeName=atlas:Recording`, `Recording/location`, a 100m/30m `DWithin`, and an `expiredAt IS NULL` filter.
4. Panorama tiles follow the observed pattern `/image/panorama/tiles/Tile/{imageId}/{zoom}/{face}/{x}/{y}` on `atlasapi2.cyclomedia.com`, with `apiKey` and `nameVersion` query parameters. The supplied observations indicate zoom 2, a 3x3 grid, and 512px tiles.
5. The supplied observations are not enough to prove how `F/R/B/L/U/D` map to recorder-forward and compass headings. The POC keeps that mapping explicit and reports a provisional warning instead of silently treating `F` as forward.

## Proof of concept

Run `scripts/streetsmart_poc.py`. It converts parcel coordinates to EPSG:3857, searches nearby recordings, prefers an authorized Cyclorama with the newest timestamp and shortest distance, calculates the parcel bearing, fetches the selected cube face, projects it to a normal rectangular JPEG, and prints the recording ID/date.

The current environment can validate the no-credential failure path only. A complete image test requires an approved Cyclomedia OAuth session plus integration API key. The supplied HAR now confirms request shape and metadata, but it still does not prove the cube-face orientation mapping; that must be verified against a visible Street Smart view before production use.

## Integration gate

Do not integrate this into the Photo Compare modal until the POC produces a visually correct image for a real Skagit parcel. Once authenticated and verified, the Django integration can cache generated files by parcel and recording ID/date, then render the assessor image and generated Street Smart image side by side.

References: [Cyclomedia Recording Locations Service](https://developer.cyclomedia.com/our-apis/recording-locations-service/), [Cyclomedia Panorama Rendering API](https://developer.cyclomedia.com/our-apis/panorama-rendering-api).
