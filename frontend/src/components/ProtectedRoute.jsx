// src/components/ProtectedRoute.jsx
import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { homePathFor } from '../utils/roles';
import { getActingTenantId } from '../services/api';

const ProtectedRoute = ({ children, allowedRoles }) => {
  const { user, token, authType, loading } = useAuth();
  const location = useLocation();

  // Show loading state while checking authentication
  if (loading) {
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh',
        background: 'var(--bg)',
        color: 'var(--text)'
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>Loading...</div>
          <div style={{ width: '40px', height: '40px', border: '3px solid var(--border)', borderTopColor: 'var(--teal)', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto' }}></div>
          <style>{`
            @keyframes spin {
              to { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      </div>
    );
  }

  // For API key auth there is no token — the key itself is the credential.
  const isAuthenticated = token || authType === 'api_key';

  if (!isAuthenticated || !user) {
    // Carry where they were going, so signing in returns them there instead of
    // dumping them on a dashboard and making them navigate again.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to={homePathFor(user.role)} replace />;
  }

  // A Super Admin has no organisation of their own, and every screen under
  // /super is tenant-scoped. Without a chosen organisation each of those pages
  // renders, fires its requests and shows an error — so send them to the
  // chooser first rather than letting them watch a dashboard fail.
  const needsOrganisation = (
    user.originalRole === 'super_admin'
    && !getActingTenantId()
    && location.pathname.startsWith('/super')
  );
  if (needsOrganisation) {
    return <Navigate to="/choose-organisation" replace state={{ from: location.pathname }} />;
  }

  return children;
};

export default ProtectedRoute;