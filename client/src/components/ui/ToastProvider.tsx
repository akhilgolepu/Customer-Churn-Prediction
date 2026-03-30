import { createContext, useCallback, useContext, useMemo, useState } from "react";

export interface ToastItem {
  id: number;
  title: string;
  description?: string;
  variant?: "success" | "error" | "info";
}

interface ToastContextValue {
  pushToast: (input: Omit<ToastItem, "id">) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

function getVariantClasses(variant: ToastItem["variant"]) {
  if (variant === "error") return "border-danger/30 bg-danger/10 text-danger";
  if (variant === "success") return "border-success/30 bg-success/10 text-success";
  return "border-accent/30 bg-accent-soft text-accent";
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const pushToast = useCallback((input: Omit<ToastItem, "id">) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    const item: ToastItem = { id, ...input };
    setToasts((prev) => [...prev, item]);

    window.setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 3600);
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2"
        role="region"
        aria-label="Notifications"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto rounded-xl border px-4 py-3 shadow-lg ${getVariantClasses(toast.variant)}`}
            role="status"
            aria-live="polite"
          >
            <p className="text-sm font-bold">{toast.title}</p>
            {toast.description && <p className="mt-1 text-xs text-ink">{toast.description}</p>}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}
