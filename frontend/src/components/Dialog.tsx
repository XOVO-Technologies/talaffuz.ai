import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

interface ConfirmOptions {
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
}

interface PromptOptions {
  title: string;
  label: string;
  defaultValue?: string;
  confirmLabel?: string;
}

type Pending =
  | { kind: "confirm"; options: ConfirmOptions; resolve: (ok: boolean) => void }
  | { kind: "prompt"; options: PromptOptions; resolve: (value: string | null) => void };

interface DialogApi {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  prompt: (options: PromptOptions) => Promise<string | null>;
}

const Ctx = createContext<DialogApi | null>(null);

export function useDialog(): DialogApi {
  const api = useContext(Ctx);
  if (!api) throw new Error("useDialog must be used inside <DialogProvider>");
  return api;
}

export function DialogProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);

  const confirm = useCallback(
    (options: ConfirmOptions) => new Promise<boolean>((resolve) => setPending({ kind: "confirm", options, resolve })),
    [],
  );
  const prompt = useCallback(
    (options: PromptOptions) => new Promise<string | null>((resolve) => setPending({ kind: "prompt", options, resolve })),
    [],
  );
  const api = useMemo(() => ({ confirm, prompt }), [confirm, prompt]);

  return (
    <Ctx.Provider value={api}>
      {children}
      {pending && <Modal pending={pending} onClose={() => setPending(null)} />}
    </Ctx.Provider>
  );
}

function Modal({ pending, onClose }: { pending: Pending; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [text, setText] = useState(pending.kind === "prompt" ? (pending.options.defaultValue ?? "") : "");
  const danger = pending.kind === "confirm" && pending.options.danger;

  // The native <dialog> gives a focus trap, Escape to cancel and an inert page behind it.
  useEffect(() => {
    ref.current?.showModal();
  }, []);

  function finish(ok: boolean) {
    if (pending.kind === "confirm") pending.resolve(ok);
    else pending.resolve(ok && text.trim() ? text.trim() : null);
    onClose();
  }

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby="modal-title"
      onCancel={(e) => {
        e.preventDefault();
        finish(false);
      }}
      onClick={(e) => e.target === ref.current && finish(false)}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          finish(true);
        }}
      >
        <div className="modal-body">
          <h2 id="modal-title">{pending.options.title}</h2>
          {pending.kind === "confirm" && pending.options.message && <p className="muted">{pending.options.message}</p>}
          {pending.kind === "prompt" && (
            <label className="field">
              <span>{pending.options.label}</span>
              <input
                type="text"
                value={text}
                autoFocus
                onFocus={(e) => e.currentTarget.select()}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
          )}
        </div>
        <div className="modal-actions">
          <button type="button" onClick={() => finish(false)}>
            Cancel
          </button>
          <button type="submit" className={danger ? "danger solid" : "primary"} autoFocus={pending.kind === "confirm" && !danger}>
            {pending.options.confirmLabel ?? (pending.kind === "prompt" ? "Create" : "OK")}
          </button>
        </div>
      </form>
    </dialog>
  );
}
