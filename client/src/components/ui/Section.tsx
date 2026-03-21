interface SectionProps {
  children: React.ReactNode;
  className?: string;
}

export default function Section({ children, className = "" }: SectionProps) {
  return (
    <section 
      className={`rounded-2xl border border-border bg-surface/90 p-6 shadow-[0_10px_30px_rgba(31,42,42,0.08)] backdrop-blur-sm ${className}`}
    >
      {children}
    </section>
  );
}
