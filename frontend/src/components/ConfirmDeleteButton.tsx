import type { ReactNode } from "react";

import { ConfirmPopoverButton } from "./ConfirmPopoverButton";

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
  return (
    <ConfirmPopoverButton
      className={className}
      disabled={disabled}
      title="确认删除"
      message={`确定要删除“${itemName}”吗？删除后无法恢复。`}
      confirmText="确认删除"
      confirmingText="删除中..."
      onConfirm={onConfirm}
    >
      {children}
    </ConfirmPopoverButton>
  );
}
