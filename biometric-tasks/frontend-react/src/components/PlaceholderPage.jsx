import React from 'react';
import DashboardLayout from '../layouts/DashboardLayout';

const PlaceholderPage = ({ title, role, label, abbr, color, bgColor }) => {
  return (
    <DashboardLayout 
      title={title} 
      role={role} 
      label={label} 
      abbr={abbr} 
      color={color} 
      bgColor={bgColor}
    >
      <div className="card-box" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
        <h2 className="section-title">{title}</h2>
        <p style={{ color: 'var(--text3)', maxWidth: '500px', margin: '1rem auto' }}>
          This administrative module is currently being migrated to the new React engine. All existing data and functionality will be restored shortly.
        </p>
        <div className="btn btn-teal" onClick={() => window.history.back()}>
          Return to Dashboard
        </div>
      </div>
    </DashboardLayout>
  );
};

export default PlaceholderPage;
