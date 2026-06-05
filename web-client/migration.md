# Vite Migration Plan (web-client)

Date: 2026-05-17  
Scope: Migrate CRA to Vite, keep JS, keep React Router v5, keep Jest, move assets to src/assets, add Vite proxy.

## Goals
- Replace CRA tooling with Vite.
- Keep current app structure and runtime behavior.
- Remove CRA artifacts.
- Enable local dev proxy to backend.
- Make API base configurable via env.

## Decisions
- Build tool: Vite
- Language: JavaScript (no TS yet)
- Router: React Router v5 (no upgrade in this pass)
- Tests: Keep Jest for now
- Assets: Move from public/images to src/assets, import in components
- Dev proxy: Enable /api -> http://localhost:8000

## Migration Steps

### 1) Package & Scripts
- Remove CRA deps: `react-scripts`, `cra-template`.
- Add Vite deps: `vite`, `@vitejs/plugin-react`.
- Replace scripts:
  - `start` -> `vite`
  - `build` -> `vite build`
  - `test` -> keep Jest setup as-is

### 2) Vite Config
- Add `vite.config.js`:
  - `@vitejs/plugin-react`
  - `server.proxy` for `/api` → `http://localhost:8000`

### 3) HTML Entry
- Move `public/index.html` to project root as `index.html`.
- Update script tag to Vite entry:
  - `<script type="module" src="/src/index.js"></script>`

### 4) Entry Point
- Ensure React 18 entry uses `createRoot` in `src/index.js` (if not already).

### 5) Assets
- Move `public/images/*` -> `src/assets/*`.
- Update components to import images:
  - `import logo from "../assets/fact-check.png";`
  - `<img src={logo} ... />`

### 6) API Base
- Switch from hardcoded URL to env:
  - Add `.env` with `VITE_API_BASE=/api` (default for dev via proxy).
  - Update API usage to `import.meta.env.VITE_API_BASE`.

### 7) Cleanup
- Remove CRA public files not needed (manifest, robots) if unused.
- Update README to reflect Vite commands.

## Files Expected to Change
- package.json
- vite.config.js (new)
- index.html (new root)
- src/index.js
- src/components/*.jsx (image imports)
- src/store/actions/factcheckActions.js (API base)
- public/ (cleanup)
- README.md (web-client)

## Validation Checklist
- `npm install` succeeds.
- `npm run dev` starts Vite server.
- App loads at http://localhost:5173
- Verify `POST /api/v1/verify` works via proxy.
- Verify images render.
- `npm test` runs as before.

---

# Post-Migration Improvements (Optional)

- [ ] 1.Upgrade React Router v5 → v6 (separate pass).
- [X] 2. Switch Jest → Vitest for faster tests. 
- [ ] 3. Add ESLint config independent of CRA.
- [X] 4. Add `@mui/icons-material` where needed and update imports.
- [X] 5. Add Vite aliases (e.g., `@/` → `src/`) to simplify imports.