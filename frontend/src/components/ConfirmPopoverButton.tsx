import { useId, useState } from "react";
import type { ReactNode } from "react";

type ConfirmPopoverButtonProps = {
  children: ReactNode;
  message: ReactNode;
  onConfirm: () => void | Promise<void>;
  title?: string;
  confirmText?: string;
  cancelText?: string;
  confirmingText?: string;
  disabled?: boolean;
  className?: string;
};

type ConfirmPopoverPromptProps = {
  message: ReactNode;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
  title?: string;
  confirmText?: string;
  cancelText?: string;
  confirmingText?: string;
};

export function ConfirmPopoverButton({
  children,
  message,
  onConfirm,
  title = "确认操作",
  confirmText = "确定",
  cancelText = "取消",
  confirmingText = "处理中...",
  disabled = false,
  className,
}: ConfirmPopoverButtonProps) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const titleId = useId();
  const messageId = useId();

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
    <span className="confirm-popover-anchor">
      <button
        type="button"
        className={className}
        disabled={disabled || confirming}
        aria-expanded={open}
        aria-describedby={open ? messageId : undefined}
        onClick={() => setOpen((current) => !current)}
      >
        {children}
      </button>
      {open ? (
        <ConfirmPopoverPanel
          title={title}
          message={message}
          confirmText={confirmText}
          cancelText={cancelText}
          confirmingText={confirmingText}
          confirming={confirming}
          titleId={titleId}
          messageId={messageId}
          onCancel={() => setOpen(false)}
          onConfirm={handleConfirm}
        />
      ) : null}
    </span>
  );
}

export function ConfirmPopoverPrompt({
  message,
  onConfirm,
  onCancel,
  title = "确认操作",
  confirmText = "确定",
  cancelText = "取消",
  confirmingText = "处理中...",
}: ConfirmPopoverPromptProps) {
  const [confirming, setConfirming] = useState(false);
  const titleId = useId();
  const messageId = useId();

  async function handleConfirm() {
    setConfirming(true);
    try {
      await onConfirm();
    } finally {
      setConfirming(false);
    }
  }

  return (
    <span className="confirm-popover-anchor">
      <ConfirmPopoverPanel
        title={title}
        message={message}
        confirmText={confirmText}
        cancelText={cancelText}
        confirmingText={confirmingText}
        confirming={confirming}
        titleId={titleId}
        messageId={messageId}
        onCancel={onCancel}
        onConfirm={handleConfirm}
      />
    </span>
  );
}

type ConfirmPopoverPanelProps = {
  title: string;
  message: ReactNode;
  confirmText: string;
  cancelText: string;
  confirmingText: string;
  confirming: boolean;
  titleId: string;
  messageId: string;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
};

function ConfirmPopoverPanel({
  title,
  message,
  confirmText,
  cancelText,
  confirmingText,
  confirming,
  titleId,
  messageId,
  onCancel,
  onConfirm,
}: ConfirmPopoverPanelProps) {
  return (
    <span
      className="confirm-popover"
      role="alertdialog"
      aria-modal="false"
      aria-labelledby={titleId}
      aria-describedby={messageId}
    >
      <strong id={titleId} className="confirm-popover-title">
        <span aria-hidden="true">!</span>
        {title}
      </strong>
      <span id={messageId} className="confirm-popover-message">{message}</span>
      <span className="confirm-popover-actions">
        <button type="button" className="modal-secondary-button" disabled={confirming} onClick={onCancel}>
          {cancelText}
        </button>
        <button type="button" className="primary-action" disabled={confirming} onClick={() => void onConfirm()}>
          {confirming ? confirmingText : confirmText}
        </button>
      </span>
    </span>
  );
}
