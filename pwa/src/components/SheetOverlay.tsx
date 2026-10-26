import { ReactNode } from "react";
import { createPortal } from "react-dom";

type Props = {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
};

export function SheetOverlay({ open, onClose, children }: Props) {
  if (!open) return null;
  return createPortal(
    <div className="sheet-overlay-root">
      <button type="button" className="sheet-backdrop" aria-label="Close" onClick={onClose} />
      {children}
    </div>,
    document.body,
  );
}
