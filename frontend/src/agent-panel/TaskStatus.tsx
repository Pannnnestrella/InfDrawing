import { theme } from "@/lib/theme";

interface TaskStatusProps {
  status: string;
  error: string | null;
  imageUrl: string | null;
}

export function TaskStatus({ status, error, imageUrl }: TaskStatusProps) {
  return (
    <div className="mt-4 space-y-2 rounded-md border p-3 text-sm" style={{ borderColor: theme.border }}>
      <div style={{ color: theme.textMuted }}>状态：{status}</div>
      {error ? <div className="text-red-400">{error}</div> : null}
      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imageUrl} alt="generated" className="mt-2 max-h-48 rounded-md border" style={{ borderColor: theme.border }} />
      ) : null}
    </div>
  );
}
