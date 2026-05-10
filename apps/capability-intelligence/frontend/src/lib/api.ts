// Thin fetch wrapper. Real auth wired in Batch 1.

const DEV_TOKEN = 'dev-dev@zennify.com';

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${DEV_TOKEN}` },
  });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return (await res.json()) as T;
}
