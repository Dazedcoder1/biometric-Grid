// src/layouts/DashboardLayout.jsx
import React, { useState, useEffect } from 'react';
import Sidebar from '../components/Sidebar';
import Topbar from '../components/Topbar';
import { tenantApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { isSuperAdmin } from '../utils/roles';

// How a Super Admin is shown, wherever they are. Every tenant screen passes
// label="Tenant Admin" because that is who it was written for; a Super Admin
// working inside an organisation uses those same screens, and was being told
// they were its Tenant Admin. Overridden here, once, rather than in fourteen
// pages. A distinct colour too: acting inside someone else's organisation
// should never be mistaken for being its admin.
const SUPER_ADMIN_IDENTITY = {
  label: 'Super Admin',
  abbr: 'SA',
  color: '#ec4899',
  bgColor: 'rgba(236,72,153,0.15)',
};

const DashboardLayout = ({ children, title, role, label: labelProp, abbr: abbrProp, color: colorProp, bgColor: bgColorProp }) => {
  const { user, authType } = useAuth();
  const [tenantId, setTenantId] = useState(null);

  const identity = isSuperAdmin(user)
    ? SUPER_ADMIN_IDENTITY
    : { label: labelProp, abbr: abbrProp, color: colorProp, bgColor: bgColorProp };
  const { label, abbr, color, bgColor } = identity;

  // Fetch tenant ID for tenant admin
  useEffect(() => {
    if (role === 'superadmin' && authType === 'api_key') {
      fetchTenantId();
    }
  }, [role, authType]);

  const fetchTenantId = async () => {
    try {
      const profile = await tenantApi.getTenantProfile();
      setTenantId(profile?.id);
    } catch (err) {
      console.error('Failed to fetch tenant ID:', err);
    }
  };

  return (
    <div id="app">
      <div className="sb-backdrop" id="sb-backdrop"></div>
      
      <Sidebar 
        role={role} 
        label={label} 
        iconColor={color} 
      />

      <div className="main">
        <Topbar 
          title={title} 
          userAbbr={abbr} 
          bgColor={bgColor} 
          iconColor={color}
          role={role}
        />
        <div className="content">
          {children}
        </div>
        
        {/* Tenant ID Footer - Bottom Right */}
        {tenantId && role === 'superadmin' && (
          <div className="tenant-id-footer">
            <span className="tenant-id-label">Tenant ID:</span>
            <span className="tenant-id-value">{tenantId}</span>
          </div>
        )}
      </div>

      <style>{`
        .tenant-id-footer {
          position: fixed;
          bottom: 12px;
          right: 16px;
          background: var(--bg3);
          padding: 4px 12px;
          border-radius: 20px;
          font-size: 0.7rem;
          font-family: var(--mono);
          color: var(--text3);
          border: 1px solid var(--border);
          backdrop-filter: blur(4px);
          z-index: 99;
          display: flex;
          gap: 6px;
          align-items: center;
        }
        
        .tenant-id-label {
          color: var(--text3);
        }
        
        .tenant-id-value {
          color: var(--teal);
          font-weight: 600;
          background: var(--bg2);
          padding: 2px 6px;
          border-radius: 12px;
        }
        
        @media (max-width: 768px) {
          .tenant-id-footer {
            bottom: 8px;
            right: 8px;
            padding: 2px 8px;
            font-size: 0.6rem;
          }
        }
      `}</style>
    </div>
  );
};

export default DashboardLayout;