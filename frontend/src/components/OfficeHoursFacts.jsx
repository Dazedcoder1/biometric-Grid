// src/components/OfficeHoursFacts.jsx
//
// The three office-hours facts — start/end, late threshold, minimum hours —
// rendered as icon + label pairs.
//
// This is the fragment only, not the banner around it. Each page frames it
// differently (amber on the employee dashboard, purple on tenant attendance),
// and pushing that styling in here would mean a `variant` prop that exists
// only to undo the component's own opinion.
//
// It lives in one file because the same three facts were written out three
// times, each with its own emoji. Emoji render at the mercy of the platform
// font: the same character is a flat glyph on one machine and a full-colour
// cartoon on another, and none of them inherit `currentColor`. Lucide icons
// are inline SVG — they take the surrounding text colour and stay at the
// weight the rest of the interface uses.

import React from 'react';
import { AlertTriangle, Clock, Timer } from 'lucide-react';

const ICON = { size: 13, strokeWidth: 1.75, style: { verticalAlign: -2, marginRight: 5, opacity: 0.8 } };

const hhmm = (t) => (t ? String(t).slice(0, 5) : '--:--');

export default function OfficeHoursFacts({ settings }) {
  if (!settings) return null;

  return (
    <>
      <span>
        <Clock {...ICON} />
        Office hours: {hhmm(settings.office_start_time)} – {hhmm(settings.office_end_time)}
      </span>
      <span>
        <AlertTriangle {...ICON} />
        Late after: +{settings.late_threshold_minutes} min
      </span>
      <span>
        <Timer {...ICON} />
        Minimum hours: {settings.min_working_hours}h
      </span>
    </>
  );
}
