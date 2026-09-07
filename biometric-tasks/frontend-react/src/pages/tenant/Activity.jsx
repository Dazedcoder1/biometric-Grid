import React from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';

const Activity = () => {
  const activity = [
    { time: '09:42', actor: 'System', event: 'Device sync completed', dept: 'Engineering' },
    { time: '09:15', actor: 'head@nexus.com', event: 'Employee EMP-1234 created', dept: 'HR' },
    { time: '08:58', actor: 'System', event: 'Device FP-007 offline alert', dept: 'Ops' },
  ];

  return (
    <DashboardLayout 
      title="Activity Log" 
      role="superadmin" 
      label="Tenant Admin" 
      abbr="TA" 
      color="#a855f7" 
      bgColor="rgba(168,85,247,0.15)"
    >
      <div className="table-wrap">
        <div className="table-header"><span className="table-title">System Activity Log</span></div>
        <table>
          <thead>
            <tr><th>Time</th><th>Actor</th><th>Event</th><th>Department</th></tr>
          </thead>
          <tbody>
            {activity.map((a, idx) => (
              <tr key={idx}>
                <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>{a.time}</td>
                <td>{a.actor}</td>
                <td>{a.event}</td>
                <td>{a.dept}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </DashboardLayout>
  );
};

export default Activity;
