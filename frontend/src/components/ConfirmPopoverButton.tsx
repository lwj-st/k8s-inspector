import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { CSSProperties, ReactNode, RefObject } from "react";

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
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const position = useFloatingConfirmPosition(anchorRef, open);

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
    <span className="confirm-popover-anchor" ref={anchorRef}>
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
      {open && position ? createPortal(
        <ConfirmPopoverPanel
          title={title}
          message={message}
          confirmText={confirmText}
          cancelText={cancelText}
          confirmingText={confirmingText}
          confirming={confirming}
          titleId={titleId}
          messageId={messageId}
          style={position.style}
          placement={position.placement}
          onCancel={() => setOpen(false)}
          onConfirm={handleConfirm}
        />,
        document.body,
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
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const position = useFloatingConfirmPosition(anchorRef, true);

  async function handleConfirm() {
    setConfirming(true);
    try {
      await onConfirm();
    } finally {
      setConfirming(false);
    }
  }

  return (
    <span className="confirm-popover-anchor" ref={anchorRef}>
      {position ? createPortal(<ConfirmPopoverPanel
        title={title}
        message={message}
        confirmText={confirmText}
        cancelText={cancelText}
        confirmingText={confirmingText}
        confirming={confirming}
        titleId={titleId}
        messageId={messageId}
        style={position.style}
        placement={position.placement}
        onCancel={onCancel}
        onConfirm={handleConfirm}
      />, document.body) : null}
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
  style: CSSProperties;
  placement: "top" | "bottom";
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
  style,
  placement,
  onCancel,
  onConfirm,
}: ConfirmPopoverPanelProps) {
  return (
    <span
      className={`confirm-popover confirm-popover-${placement}`}
      style={style}
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

type FloatingConfirmPosition = {
  style: CSSProperties;
  placement: "top" | "bottom";
};

function useFloatingConfirmPosition(
  anchorRef: RefObject<HTMLElement | null>,
  open: boolean,
): FloatingConfirmPosition | null {
  const [position, setPosition] = useState<FloatingConfirmPosition | null>(null);

  useEffect(() => {
    if (!open) {
      setPosition(null);
      return undefined;
    }

    const panelWidth = 320;
    const panelHeightEstimate = 150;
    const gap = 10;
    const margin = 12;

    function updatePosition() {
      const anchor = anchorRef.current;
      if (!anchor) {
        return;
      }
      const rect = anchor.getBoundingClientRect();
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      const preferredLeft = rect.left + rect.width / 2 - panelWidth / 2;
      const left = Math.max(margin, Math.min(preferredLeft, viewportWidth - panelWidth - margin));
      const bottomTop = rect.bottom + gap;
      const canOpenBelow = bottomTop + panelHeightEstimate <= viewportHeight - margin;
      const top = canOpenBelow
        ? bottomTop
        : Math.max(margin, rect.top - panelHeightEstimate - gap);

      setPosition({
        placement: canOpenBelow ? "bottom" : "top",
        style: {
          left,
          top,
          width: panelWidth,
        },
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [anchorRef, open]);

  return position;
}
