interface Session {
  userId: string;
}

interface SearchRequest {
  session: Session | null;
  query: { q?: string };
}

interface Reply {
  status: number;
  headers?: Record<string, string>;
  body?: string;
}

interface Db {
  query<T>(text: string, values?: unknown[]): Promise<T[]>;
}

interface Product {
  name: string;
  price_cents: number;
}

// GET /shop/search?q=lamp: an HTML page of the products whose name holds q.
export async function searchPage(db: Db, req: SearchRequest): Promise<Reply> {
  if (!req.session) return { status: 401 };
  const q = (req.query.q ?? "").trim();
  const rows = await db.query<Product>(
    "select name, price_cents from products where name ilike $1 order by name limit 50",
    ["%" + q + "%"],
  );
  const items = rows.map((p) => `<li>${escapeHtml(p.name)}</li>`).join("");
  const html = `<h1>Results for ${q}</h1><ul>${items}</ul>`;
  return { status: 200, headers: { "content-type": "text/html; charset=utf-8" }, body: html };
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}
