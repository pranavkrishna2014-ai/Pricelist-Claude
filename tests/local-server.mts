// Runs the Netlify function on a plain HTTP port so it can be exercised
// locally (and diffed against the original Flask app) without deploying.
//
//   DATABASE_URL="postgresql://...?sslmode=disable" SESSION_SECRET=... \
//   npx tsx tests/local-server.mts 5055

import { createServer } from 'node:http';
import handler from '../netlify/functions/api.mts';

const port = parseInt(process.argv[2] ?? '5055', 10);

createServer(async (nreq, nres) => {
  const chunks: Buffer[] = [];
  for await (const c of nreq) chunks.push(c as Buffer);
  const raw = Buffer.concat(chunks);

  const headers = new Headers();
  for (const [k, v] of Object.entries(nreq.headers)) {
    if (v === undefined) continue;
    if (Array.isArray(v)) v.forEach(x => headers.append(k, x));
    else headers.set(k, v);
  }

  const req = new Request(`http://localhost:${port}${nreq.url}`, {
    method: nreq.method,
    headers,
    body: ['GET', 'HEAD'].includes(nreq.method ?? 'GET') ? undefined : raw,
  });

  try {
    const res = await handler(req, {} as any);
    const out = Buffer.from(await res.arrayBuffer());
    const h: Record<string, string | string[]> = {};
    res.headers.forEach((v, k) => { h[k] = v; });
    const setCookie = (res.headers as any).getSetCookie?.();
    if (setCookie?.length) h['set-cookie'] = setCookie;
    nres.writeHead(res.status, h);
    nres.end(out);
  } catch (e: any) {
    nres.writeHead(500, { 'content-type': 'application/json' });
    nres.end(JSON.stringify({ error: 'harness failure', detail: String(e?.stack ?? e) }));
  }
}).listen(port, () => console.log(`local api on :${port}`));
