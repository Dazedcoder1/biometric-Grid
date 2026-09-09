// src/pages/org/Settings.jsx
import React from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { Shield, AlertCircle, ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

const Settings = () => {
  return (
    <DashboardLayout title="Settings" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <style>{`
        .restricted-card {
          max-width: 500px;
          margin: 2rem auto;
          text-align: center;
          animation: fadeInUp 0.4s ease;
        }
        @keyframes fadeInUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .restricted-icon {
          width: 80px;
          height: 80px;
          background: rgba(239, 68, 68, 0.1);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 1.25rem;
        }
      `}</style>

      <div className="card-box restricted-card">
        <div className="restricted-icon">
          <Shield size={40} style={{ color: '#ef4444' }} />
        </div>
        
        <h3 style={{ fontSize: '1.3rem', fontWeight: 600, marginBottom: '0.5rem' }}>
          Access Restricted
        </h3>
        
        <p style={{ color: 'var(--text3)', marginBottom: '1rem', lineHeight: 1.5 }}>
          Department settings (working hours, late thresholds, and attendance rules) 
          can only be modified by <strong>Tenant Administrators</strong>.
        </p>
        
        <div style={{ 
          background: 'rgba(168,85,247,0.1)', 
          border: '1px solid rgba(168,85,247,0.2)',
          borderRadius: '10px',
          padding: '0.75rem',
          marginBottom: '1.5rem',
          fontSize: '0.8rem',
          color: 'var(--text2)'
        }}>
          <AlertCircle size={14} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'middle' }} />
          If you need to update organization-wide settings, please contact your Tenant Administrator.
        </div>
        
        <Link to="/org/dashboard">
          <button className="btn btn-teal" style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '0 auto' }}>
            <ArrowLeft size={16} />
            Return to Dashboard
          </button>
        </Link>
      </div>
    </DashboardLayout>
  );
};

export default Settings;