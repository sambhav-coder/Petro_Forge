# PetroForge 3D Frontend

Next.js 14 + React 18 + TypeScript + React Three Fiber + Three.js + Tailwind CSS.
Interactive 3D Digital Twin for SIH26120 (routes: `/` landing, `/twin` full twin).

## Environment

| Variable | Default (development) | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | FastAPI backend base URL |

No secrets required. For future Vercel deployment, set
`NEXT_PUBLIC_API_BASE_URL` to the deployed backend URL in the Vercel
project settings — no source change needed. Copy `.env.example` to `.env`
for local overrides (never commit `.env`).

## Scripts

```powershell
npm install
npm run dev      # local dev server
npm run build    # production build (must pass for deploy)
npm run lint     # ESLint (must pass)
npm start        # serve the production build
```

## Notes

- The landing page (`/`) renders fully without the backend.
- The twin (`/twin`) requires the FastAPI backend; it shows explicit
  connection state and never fabricates engineering values.
- All geometry is stylized prototype visualization (relative units).
  Engineering numbers always come from the backend.
