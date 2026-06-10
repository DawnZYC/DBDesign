# EcoTEA WP1 Import Frontend

React + Vite + TypeScript single-page app for uploading Excel files and viewing import results.

## Start

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

The Vite dev server proxies all `/api/*` requests to http://localhost:8000, so no CORS setup or absolute API URLs are required.

## Structure

```text
frontend/
├── index.html
├── package.json
├── vite.config.ts
└── src/
    ├── main.tsx                   # Entry point
    ├── App.tsx                    # Root component
    ├── api.ts                     # Backend API calls
    ├── types.ts                   # Types synchronized with backend schemas
    ├── styles.css                 # All styles
    └── components/
        ├── FileUpload.tsx         # Drag-and-drop upload
        └── ImportResultPanel.tsx  # Import result display
```

## Production Build

```bash
npm run build
# Serve dist/ from any static web server.
```
