import { useState } from "react";
import type { ReactNode } from "react";

type ConfirmDeleteButtonProps = {
  children: ReactNode;
  itemName: string;
  onConfirm: () => void | Promise<void>;
  disabled?: boolean;
  className?: string;
};

export function ConfirmDeleteButton({
  children,
  itemName,
  onConfirm,
  disabled = false,
  className = "mini-button button-danger",
}: ConfirmDeleteButtonProps) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function handleConfirm() {
    setConfirming(true);
    try {
      await onConfirm();
      setOpen(false);
    } finally {
      setConfirming(false);
    }
  }

  return (
    <>
      <button type="button" className={className} disabled={disabled} onClick={() => setOpen(true)}>
        {children}
      </button>
      {open ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => !confirming && setOpen(false)}>
          <section
            className="modal-card modal-card-polished confirm-delete-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-label="确认删除"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h3>确认删除</h3>
            <p>确定要删除“{itemName}”吗？删除后无法恢复。</p>
            <div className="button-row modal-action-row">
              <button type="button" className="button-danger" disabled={confirming} onClick={() => void handleConfirm()}>
                {confirming ? "删除中..." : "确认删除"}
              </button>
              <button type="button" className="modal-secondary-button" disabled={confirming} onClick={() => setOpen(false)}>
                取消
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
