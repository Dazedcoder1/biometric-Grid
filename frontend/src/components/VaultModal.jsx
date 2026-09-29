// src/components/VaultModal.jsx
//
// One modal shell for the vault screens. Previously each page built its own
// overlay inline, and none of them handled Escape or a backdrop click — the
// only way out was the small X in the corner, which on a phone sits under the
// thumb's blind spot.
//
// Deliberately not a focus trap. A real trap needs to enumerate focusable
// descendants and handle Tab in both directions, and a half-built one is worse
// than none: it can strand focus outside the dialog with no way back. What is
// here — Escape, backdrop click, focus moved into the dialog on open, and
// aria-modal so screen readers treat the rest of the page as inert — covers
// the cases people actually hit. If a trap is wanted later it belongs in a
// library, not hand-rolled.

import React, { useCallback, useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export default function VaultModal({ title, onClose, children, labelledBy }) {
  const dialogRef = useRef(null);
  const headingId = labelledBy || 'v-modal-title';

  // Stored so focus can go back where it came from. Without this, dismissing a
  // modal drops focus onto <body> and a keyboard user restarts from the top of
  // the page.
  const restoreTo = useRef(null);

  useEffect(() => {
    restoreTo.current = document.activeElement;
    dialogRef.current?.focus();

    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);

    // The page behind must not scroll while a modal is open — on touch it is
    // otherwise very easy to scroll the list instead of the dialog.
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      if (restoreTo.current instanceof HTMLElement) restoreTo.current.focus();
    };
  }, [onClose]);

  // Only a click that both starts and ends on the backdrop closes. Checking
  // e.target alone closes the dialog when a drag-select of the text inside it
  // happens to release over the backdrop, which loses what was being typed.
  const downOnBackdrop = useRef(false);
  const onMouseDown = useCallback((e) => {
    downOnBackdrop.current = e.target === e.currentTarget;
  }, []);
  const onMouseUp = useCallback((e) => {
    if (downOnBackdrop.current && e.target === e.currentTarget) onClose();
    downOnBackdrop.current = false;
  }, [onClose]);

  return (
    <div className="v-overlay" onMouseDown={onMouseDown} onMouseUp={onMouseUp}>
      <div
        ref={dialogRef}
        className="v-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        tabIndex={-1}
      >
        <button
          type="button"
          className="v-modal-close"
          onClick={onClose}
          aria-label="Close"
        >
          <X size={18} />
        </button>
        {title && <h3 id={headingId}>{title}</h3>}
        {children}
      </div>
    </div>
  );
}
