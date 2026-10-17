export function formatTime(seconds: number | null | undefined): string {
  if (seconds == null) return "";
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

export function parseTime(value: string): number | null | undefined {
  const text = value.trim();
  if (!text) return null;
  const parts = text.split(":").map(Number);
  if (parts.some((part) => Number.isNaN(part) || part < 0) || parts.length > 3) return undefined;
  return parts.reduce((total, part) => total * 60 + part, 0);
}
