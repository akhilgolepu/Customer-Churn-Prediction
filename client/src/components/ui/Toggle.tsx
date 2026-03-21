interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export default function Toggle({ label, checked, onChange, disabled = false }: ToggleProps) {
  return (
    <div 
      className={`flex items-center justify-between rounded-xl border p-3 transition-all duration-200
        ${checked ? 'border-accent/45 bg-accent-soft/40' : 'border-border bg-surface'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-accent/40'}
      `}
      onClick={() => !disabled && onChange(!checked)}
    >
      <span className="text-sm font-medium text-ink">{label}</span>
      
      <div className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors 
        ${checked ? "bg-accent" : "bg-border"}
      `}>
        <span
          className={`${
            checked ? "translate-x-6" : "translate-x-1"
          } inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform`}
        />
      </div>
    </div>
  );
}
