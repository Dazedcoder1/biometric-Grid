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

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

export default function VaultModal({ title, onClose, children, labelledBy }) {
  const dialogRef = useRef(null);
  const headingId = labelledBy || 'v-modal-title';

  // The latest onClose, without making it a reason to re-run the setup below.
  //
  // Every caller passes an inline arrow, so onClose is a new function on every
  // render of the page. The setup effect used to depend on it — so each
  // keystroke in a field inside the dialog re-rendered the page, re-ran the
  // setup, and moved focus back onto the dialog box. Typing a six-digit code
  // meant clicking back into the field after every digit.
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  // Where focus was before the dialog opened, so closing it can go back there
  // — otherwise focus drops onto <body> and a keyboard user restarts from the
  // top of the page. Captured on the first render, before anything inside the
  // dialog (an autoFocus field) has taken focus.
  const [restoreTo] = useState(() => document.activeElement);

  // Once, when the dialog opens.
  useEffect(() => {
    // Respect an autoFocus field inside the dialog: only take focus ourselves
    // if nothing in here has it. Focusing the dialog box unconditionally stole
    // the cursor from the very field the dialog exists to fill in.
    const dialog = dialogRef.current;
    if (dialog && !dialog.contains(document.activeElement)) dialog.focus();

    const onKey = (e) => { if (e.key === 'Escape') onCloseRef.current(); };
    document.addEventListener('keydown', onKey);

    // The page behind must not scroll while a modal is open — on touch it is
    // otherwise very easy to scroll the list instead of the dialog.
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      if (restoreTo instanceof HTMLElement && document.contains(restoreTo)) restoreTo.focus();
    };
  }, [restoreTo]);

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
