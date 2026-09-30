// src/components/ProtectedRoute.jsx
import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { homePathForUser, isSuperAdmin, PLATFORM_HOME } from '../utils/roles';
import { getActingTenantId } from '../services/api';

/**
 * @param allowedRoles    normalised roles that may open the screen
 * @param superAdminOnly  platform screens: a Super Admin and nobody else. The
 *                        role list cannot express this, because a Super Admin
 *                        normalises to tenant_admin.
 */
const ProtectedRoute = ({ children, allowedRoles, superAdminOnly = false }) => {
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
    return <Navigate to={homePathForUser(user)} replace />;
  }

  if (superAdminOnly && !isSuperAdmin(user)) {
    return <Navigate to={homePathForUser(user)} replace />;
  }

  const superAdmin = isSuperAdmin(user);

  // No vault for the platform operator. Every vault query is scoped to the
  // caller's own organisation, and a Super Admin has none, so the screens
  // showed empty lists and would have failed on the first save. And the vault
  // holds people's credentials inside one organisation — not something the
  // platform operator should be browsing. The sidebar hides the links; this
  // covers a typed or bookmarked URL.
  if (superAdmin && location.pathname.startsWith('/vault')) {
    return <Navigate to={PLATFORM_HOME} replace />;
  }

  // A Super Admin has no organisation of their own, and every screen under
  // /super is tenant-scoped. Without a chosen organisation each of those pages
  // renders, fires its requests and shows an error — so send them to the
  // chooser first rather than letting them watch a dashboard fail.
  const needsOrganisation = (
    superAdmin
    && !getActingTenantId()
    && location.pathname.startsWith('/super')
  );
  if (needsOrganisation) {
    return <Navigate to="/choose-organisation" replace state={{ from: location.pathname }} />;
  }

  return children;
};

export default ProtectedRoute;
