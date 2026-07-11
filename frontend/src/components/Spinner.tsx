interface SpinnerProps {
  size?: number;
  className?: string;
}

export function Spinner({ size = 14, className }: SpinnerProps) {
  return (
    <span
      aria-hidden
      className={`inline-block shrink-0 animate-spin rounded-full border-2 border-line-strong border-t-accent ${className ?? ""}`}
      style={{ width: size, height: size }}
    />
  );
}
