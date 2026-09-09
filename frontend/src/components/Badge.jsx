import React from 'react';

const Badge = ({ type, children }) => {
  const classes = {
    active: 'badge active',
    present: 'badge present',
    success: 'badge active',
    absent: 'badge absent',
    alert: 'badge absent',
    late: 'badge late',
    suspended: 'badge late',
    pending: 'badge pending',
    online: 'badge online',
    offline: 'badge offline',
  };
  return <span className={classes[type] || 'badge'}>{children}</span>;
};

export default Badge;
