export interface Health {
  status: string;
  source: string;
  last_refresh: string | null;
  ts: string;
}

export async function fetchHealth(): Promise<Health> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(`health: ${res.status}`);
  return res.json();
}
