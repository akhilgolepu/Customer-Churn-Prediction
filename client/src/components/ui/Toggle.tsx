interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export default function Toggle({ label, checked, onChange, disabled = false }: ToggleProps) {
  return (
    <div 
      className={`flex items-center justify-between p-3 border rounded-lg bg-paper transition-all
        ${checked ? 'border-steel/50 bg-steel/5' : 'border-sand'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-steel'}
      `}
      onClick={() => !disabled && onChange(!checked)}
    >
      <span className="text-sm font-medium text-ink">{label}</span>
      
      <div className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-steel focus:ring-offset-2 
        ${checked ? "bg-steel" : "bg-sand"}
      `}>
        <span
          className={`${
            checked ? "translate-x-6" : "translate-x-1"
          } inline-block h-4 w-4 transform rounded-full bg-paper transition-transform`}
        />
      </div>
    </div>
  );
}
