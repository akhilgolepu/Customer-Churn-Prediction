import { useState } from "react";

interface FeedbackWidgetProps {
  onSubmit: (message: string) => void;
}

export default function FeedbackWidget({ onSubmit }: FeedbackWidgetProps) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");

  return (
    <div className="fixed bottom-4 right-4 z-30">
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-full border border-border bg-surface px-4 py-2 text-sm font-semibold text-ink shadow-lg hover:border-accent"
        >
          Feedback
        </button>
      )}

      {open && (
        <div className="w-80 rounded-2xl border border-border bg-surface p-4 shadow-2xl">
          <div className="flex items-center justify-between">
            <p className="text-sm font-bold text-ink">Share feedback</p>
            <button type="button" onClick={() => setOpen(false)} className="text-xs text-muted">Close</button>
          </div>

          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            rows={4}
            placeholder="What worked well? What felt confusing?"
            className="mt-3 w-full rounded-xl border border-border bg-base px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
          />

          <button
            type="button"
            onClick={() => {
              const trimmed = message.trim();
              if (!trimmed) return;
              onSubmit(trimmed);
              setMessage("");
              setOpen(false);
            }}
            className="mt-3 w-full rounded-xl bg-accent px-3 py-2 text-sm font-semibold text-white"
          >
            Send feedback
          </button>
        </div>
      )}
    </div>
  );
}
