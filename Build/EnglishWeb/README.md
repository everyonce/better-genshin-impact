# English embedded frontend assets

`build.ps1` reproduces both embedded web frontends from pinned upstream commits with the local English patches. Run from the repository root:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File Build/EnglishWeb/build.ps1
```

Requires Git, Node.js, and npm. It uses clean npm installs and production builds, then writes:

- `Build/EnglishWeb/dist/Map/Editor/index.html`
- `Build/EnglishWeb/dist/Web/ScriptRepo/index.html`

Each run uses a fresh GUID-named temporary checkout under `Build/EnglishWeb/.work`. The builder never deletes existing work directories; remove a specific old run manually when no longer needed. `source.json` records source pins and known artifact metadata. The generated `dist` files are the inputs to the parent portable packaging script.

The patches localize built-in frontend chrome, force the script repository UI to English even if an older browser preference requested Chinese, and translate common repository/map category labels for display. User-authored scripts, API contracts, stored identifiers, and game data remain unchanged. Map region/floor display labels use an explicit display-only dictionary; noncanonical descriptive renderings are documented in `floor-name-notes.md`.
