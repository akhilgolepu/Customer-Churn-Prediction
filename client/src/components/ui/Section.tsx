interface SectionProps {
  children: React.ReactNode;
  className?: string;
}

export default function Section({ children, className = "" }: SectionProps) {
  return (
    <section 
      className={`rounded-2xl border border-sand bg-paper p-6 shadow-sm ${className}`}
    >
      {children}
    </section>
  );
}
