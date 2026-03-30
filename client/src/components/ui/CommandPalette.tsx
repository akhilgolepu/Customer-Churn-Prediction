import { useEffect, useMemo, useState } from "react";

export interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  action: () => void;
}

interface CommandPaletteProps {
  commands: CommandItem[];
  onOpenChange?: (open: boolean) => void;
  onExecute?: (commandId: string) => void;
}

export default function CommandPalette({ commands, onOpenChange, onExecute }: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    onOpenChange?.(open);
  }, [onOpenChange, open]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return commands;
    return commands.filter((command) => command.label.toLowerCase().includes(normalized));
  }, [commands, query]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-ink/45 px-4 pt-24" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="w-full max-w-xl rounded-2xl border border-border bg-surface p-4 shadow-2xl">
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search actions..."
          className="w-full rounded-xl border border-border bg-base px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
        />
        <div className="mt-3 max-h-72 overflow-auto">
          {filtered.map((command) => (
            <button
              key={command.id}
              type="button"
              onClick={() => {
                onExecute?.(command.id);
                command.action();
                setOpen(false);
              }}
              className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-accent-soft"
            >
              <span className="font-medium text-ink">{command.label}</span>
              {command.hint && <span className="text-xs text-muted">{command.hint}</span>}
            </button>
          ))}
          {filtered.length === 0 && <p className="px-3 py-2 text-sm text-muted">No matching commands.</p>}
        </div>
      </div>
    </div>
  );
}
