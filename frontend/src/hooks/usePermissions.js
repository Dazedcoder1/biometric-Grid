// src/hooks/usePermissions.js
//
// What the signed-in caller may do, fetched once per mount.
//
// This is for rendering only. Hiding a button is not access control — every
// route checks its own permission server-side, and a client that ignores this
// still gets a 403. What it prevents is the interface promising something the
// server will refuse, which is how "This action requires the 'audit.verify'
// permission" ended up in front of a Tenant Admin who could never have run it.
//
// While loading, `can()` returns false. Showing a control and then removing it
// a moment later is worse than showing it slightly late, and an action that
// appears only once its permission is confirmed can never flash and vanish.

import { useEffect, useState } from 'react';
import { vaultApi } from '../services/api';

export default function usePermissions() {
  const [state, setState] = useState({
    loading: true,
    codes: new Set(),
    grantsAll: false,
    stepUp: new Set(),
    error: '',
  });

  useEffect(() => {
    let cancelled = false;

    vaultApi.myPermissions()
      .then((data) => {
        if (cancelled) return;
        setState({
          loading: false,
          codes: new Set(data.permissions || []),
          grantsAll: !!data.grants_all,
          stepUp: new Set(data.step_up_required || []),
          error: '',
        });
      })
      .catch((err) => {
        if (cancelled) return;
        // Fail closed. If we cannot establish what the caller may do, offering
        // everything guarantees the exact error this hook exists to prevent.
        setState({
          loading: false,
          codes: new Set(),
          grantsAll: false,
          stepUp: new Set(),
          error: err.message || 'Could not load your permissions.',
        });
      });

    return () => { cancelled = true; };
  }, []);

  return {
    ...state,
    can: (code) => state.grantsAll || state.codes.has(code),
    needsStepUp: (code) => state.stepUp.has(code),
  };
}
