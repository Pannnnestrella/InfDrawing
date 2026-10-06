/** Inline stroke icons (16px grid), sized via the `size` prop. */

interface IconProps {
  size?: number;
  className?: string;
}

function base(size?: number) {
  return {
    width: size ?? 16,
    height: size ?? 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
}

export function ImageIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="M3.5 17.5 9 12l4 4 3-3 4.5 4.5" />
    </svg>
  );
}

export function BrushIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="M20 4 9.5 14.5" />
      <path d="M7.5 13.5c-2 0-3.5 1.6-3.5 3.6 0 1.2-.8 2.2-2 2.4 1 1 2.4 1.5 3.8 1.5 2.5 0 4.7-2 4.7-4.5" />
    </svg>
  );
}

export function WandIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="M15 4v2" />
      <path d="M15 10v2" />
      <path d="M12 7h2" />
      <path d="M16 7h2" />
      <path d="m4.5 19.5 9-9" />
      <path d="m13.5 10.5 2 2" />
    </svg>
  );
}

export function LayersIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 13 9 5 9-5" />
    </svg>
  );
}

export function TypeIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="M5 6V4h14v2" />
      <path d="M12 4v16" />
      <path d="M9 20h6" />
    </svg>
  );
}

export function SendIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="m5 12 14-7-4 14-3.5-5L5 12Z" />
      <path d="M11.5 14 19 5" />
    </svg>
  );
}

export function SparklesIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="M12 4c.6 3.4 2.6 5.4 6 6-3.4.6-5.4 2.6-6 6-.6-3.4-2.6-5.4-6-6 3.4-.6 5.4-2.6 6-6Z" />
      <path d="M19 15.5c.3 1.5 1.2 2.4 2.7 2.7-1.5.3-2.4 1.2-2.7 2.7-.3-1.5-1.2-2.4-2.7-2.7 1.5-.3 2.4-1.2 2.7-2.7Z" />
    </svg>
  );
}

export function ChevronRightIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="m9 5 7 7-7 7" />
    </svg>
  );
}

export function AlertIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="M12 4 2.8 20h18.4L12 4Z" />
      <path d="M12 10v5" />
      <path d="M12 17.8v.2" />
    </svg>
  );
}

export function CheckIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  );
}

export function RefreshIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="M20 12a8 8 0 1 1-2.34-5.66" />
      <path d="M20 4v4.5h-4.5" />
    </svg>
  );
}

export function CloseIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <path d="M6 6 18 18" />
      <path d="M18 6 6 18" />
    </svg>
  );
}

export function GitBranchIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className} aria-hidden>
      <circle cx="6" cy="6" r="2.2" />
      <circle cx="6" cy="18" r="2.2" />
      <circle cx="18" cy="12" r="2.2" />
      <path d="M6 8.2v7.6" />
      <path d="M8.2 6h3.3c2.5 0 4.5 2 4.5 4.5V12" />
    </svg>
  );
}
