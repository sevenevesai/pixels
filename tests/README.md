# Workspace regression tests

Run `npm ci`, then `npx playwright install chromium` once. `npm test` starts Vite on port
1422 and runs the browser suite; success means every test passes. `npm run build` checks
frontend types and production bundling. `cargo check --locked --manifest-path src-tauri/Cargo.toml`
checks the desktop code and capability configuration.

The browser suite uses real React components and Tauri JavaScript APIs with native IO mocked
at the IPC boundary. It covers folder scope, nested paths, cache/link exclusion, stale loads,
native drop events, bulk cancellation, and shared outline-color persistence. Mocked settings
use browser storage to simulate database persistence across reloads.

Native OS drag delivery is outside this suite. For a desktop smoke check, run `npm run tauri dev`,
drop a test folder and image from the file manager, and restart after choosing an outline color.
Use disposable images when checking bulk processing and Revert All.
