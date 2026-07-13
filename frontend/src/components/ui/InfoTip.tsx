interface InfoTipProps {
  content: string;
}

export default function InfoTip({ content }: InfoTipProps) {
  return (
    <span className="group relative ml-1 inline-flex align-middle">
      <span
        aria-label="More information"
        className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-accent/40 bg-accent-soft text-[10px] font-bold text-accent"
      >
        i
      </span>
      <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-2 hidden w-64 -translate-x-1/2 rounded-lg border border-border bg-surface px-3 py-2 text-xs font-medium leading-relaxed text-muted shadow-lg group-hover:block">
        {content}
      </span>
    </span>
  );
}
