# frontend

React (Vite + TypeScript) dashboard for stock-advisor — see the root
[`README.md`](../README.md)'s "Web UI" and "Deploying to Railway" sections for
how this gets run and shipped.

```bash
npm install
npm run dev     # :5173, proxies /auth /brokers /me /health to :8000
npm run build   # -> dist/, served by the FastAPI app in production
```
