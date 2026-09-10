# Street Smart comparison investigation

## Status

The supplied `streetsmart.cyclomedia.com.har` was retrieved from the user's Drive file and inspected locally. The HAR is not stored in the project. No token, browser cookie, captured API key, or recording ID is stored in the project.

## Authentication boundary

Cyclomedia documents the Recording Locations Service at:

`https://atlasapi.cyclomedia.com/api/recording/wfs`

The service requires Basic Authentication or OAuth. Direct unauthenticated requests from this environment returned HTTP 401 for both the WFS and the supplied panorama tile pattern. Being signed into Street Smart in Chrome does not give the Django process Chrome's cookies or in-memory authorization state. Two tabs in the same Chrome session help only if the browser itself makes the cross-origin request and Cyclomedia permits credentialed CORS; they do not make browser cookies available to a Railway/Django request.

The HAR adds a browser OAuth detail: Street Smart exchanges an Authorization Code + PKCE verifier at `https://identity.cyclomedia.com/connect/token` using the public client ID and `https://streetsmart.cyclomedia.com/login` redirect. The response contains `id_token`, `access_token`, a one-hour lifetime, and scopes including `openid email roles profile accounts`. The OAuth token is not the same thing as the Atlas `apiKey` query parameter observed on WFS and tile requests. The Atlas key is supplied to the web application as configuration and must be treated as an integration credential; it is not derived safely from a captured HAR value.

The browser's bundled request helper supports `Authorization: Bearer ...` (and also Basic/TID modes). The HAR's preflight requests explicitly request the `authorization` header, while the exported actual-request header lists omit sensitive authorization values. That is consistent with the app using the OAuth session for protected configuration/metadata calls; it is not evidence that an OpenSkagit backend can reuse the Chrome session.

The HAR also shows the practical CORS boundary: successful Atlas responses return `Access-Control-Allow-Origin: https://streetsmart.cyclomedia.com` and `Access-Control-Allow-Credentials: true`. The preflight allows `authorization,content-type`, but only for the Street Smart origin. A browser tab at OpenSkagit cannot safely assume it can call these endpoints directly, and the Railway backend cannot see the other Chrome tab's in-memory token.

The standalone proof of concept therefore accepts only one of these explicit, legitimate inputs at runtime:

- `CYCLOMEDIA_BEARER_TOKEN` for a short-lived OAuth token.
- `CYCLOMEDIA_USERNAME` and `CYCLOMEDIA_PASSWORD` for an approved Cyclomedia integration account.
- `CYCLOMEDIA_API_KEY` for an approved Atlas/Street Smart integration key.

It does not scrape browser storage, copy HAR tokens, or attempt to reproduce a browser-only login flow. The POC exposes an in-memory `exchange_authorization_code()` helper for a caller that already owns a fresh PKCE code; it does not persist tokens. Until Cyclomedia confirms an approved server-to-server credential flow, or we implement a first-party OAuth redirect for the routing app with approved CORS/API-key terms, the Django app should fail closed with `StreetSmartAuthError` and keep the assessor image usable.

## Requests mapped so far

1. Street Smart navigation accepts an address or coordinate in `q`.
2. The recording search is a WFS `GetFeature` request using a spatial `DWithin` filter around an EPSG:3857 point.
3. Recording metadata includes `imageId`, `recordedAt`, location, orientation, `recorderDirection`, authorization state, product type, and panorama tile schema. The supplied WFS payload uses XML `GetFeature`, `typeName=atlas:Recording`, `Recording/location`, a 100m/30m `DWithin`, and an `expiredAt IS NULL` filter.
4. Panorama tiles follow `/image/panorama/tiles/Tile/{imageId}/{zoom}/{face}/{x}/{y}` on a load-balanced Atlas tile host (`atlasapi`, `atlasapi1`, `atlasapi2`, `atlasapi3`, and `atlasapi4` appeared in the HAR), with `apiKey` and `nameVersion` query parameters. The HAR confirms zoom 2, 512px tiles, and a 3x3 grid for a complete cube face. It also shows an initial zoom-0 `A` tile and lower-resolution zoom-1 face requests, so the service is not limited to the zoom-2 path.
5. The HAR requests all six faces (`F/R/B/L/U/D`) for the initial panorama. The complete captured zoom-2 `F` face stitches cleanly into a normal residential street-facing image when projected. The HAR alone does not prove how `F/R/B/L/U/D` map to recorder-forward and compass headings, because it does not capture a trustworthy viewer camera pose alongside each tile batch. The POC keeps that mapping explicit and reports a provisional warning instead of silently treating `F` as forward.

## Proof of concept

Run `scripts/streetsmart_poc.py`. It converts parcel coordinates to EPSG:3857, searches nearby recordings, prefers an authorized Cyclorama with the newest timestamp and shortest distance, calculates the parcel bearing, fetches the selected cube face, projects it to a normal rectangular JPEG, and prints the recording ID/date.

The current environment can validate the no-credential failure path and the image reconstruction path using the HAR's captured JPEG tiles. The resulting projected test image is a normal 1024x768 property view, not a square cube face. A live end-to-end test still requires an approved Cyclomedia OAuth/session strategy plus integration API key. The HAR confirms the request shape, metadata, CORS behavior, and tile stitching, but it does not prove the cube-face orientation mapping; that must be verified against a visible Street Smart view before production use.

## Integration gate

Do not integrate this into the Photo Compare modal until the POC produces a visually correct live image for a real Skagit parcel. The safe next step is to ask Cyclomedia for an approved server-side API key/OAuth client or a supported browser-embedded integration origin that includes the deployed OpenSkagit origin. Do not scrape Chrome storage, copy temporary HAR tokens, or fetch and parse the Street Smart page's embedded web key as a backend authentication workaround. Once the credential boundary is approved and orientation is verified, the Django integration can cache generated files by parcel and recording ID/date, then render the assessor image and generated Street Smart image side by side.

References: [Cyclomedia Recording Locations Service](https://developer.cyclomedia.com/our-apis/recording-locations-service/), [Cyclomedia Panorama Rendering API](https://developer.cyclomedia.com/our-apis/panorama-rendering-api).
