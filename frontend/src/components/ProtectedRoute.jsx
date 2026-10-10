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

  // A temporary password from an administrator. Nothing else until they pick
  // their own — the server refuses every other request anyway, so letting them
  // reach a dashboard would only show a screen full of errors.
  // The reverse — sending someone WITHOUT the flag away from that screen — is
  // deliberately absent. A tab signed in before the reset holds a token with
  // no flag, the server refuses its requests, and api.js sends it here; a
  // redirect back out would bounce between the two forever.
  const onChangeScreen = location.pathname === '/change-password';
  if (user.mustChangePassword && !onChangeScreen) {
    return <Navigate to="/change-password" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to={homePathForUser(user)} replace />;
  }

  if (superAdminOnly && !isSuperAdmin(user)) {
    return <Navigate to={homePathForUser(user)} replace />;
  }

  const superAdmin = isSuperAdmin(user);

  // The Super Admin's vault screens are People (everyone's vaults), the
  // Dependency Map and the Audit Log. What they do NOT have is a vault of
  // their own — a vault belongs to an organisation and they have none — so
  // the personal vault page and single-credential pages send them to People.
  const superAdminVaultPages = ['/vault/people', '/vault/dependencies', '/vault/audit'];
  if (superAdmin && location.pathname.startsWith('/vault')
      && !superAdminVaultPages.includes(location.pathname)) {
    return <Navigate to={getActingTenantId() ? '/vault/people' : PLATFORM_HOME} replace />;
  }

  // A Super Admin has no organisation of their own, and every screen under
  // /super — plus People and the Dependency Map — is scoped to one. Without a
  // chosen organisation each of those pages renders, fires its requests and
  // shows an error — so send them to the chooser first rather than letting
  // them watch a page fail. The Audit Log is the exception: with no
  // organisation chosen it shows all of them.
  const needsOrganisation = (
    superAdmin
    && !getActingTenantId()
    && (location.pathname.startsWith('/super')
      || location.pathname === '/vault/people'
      || location.pathname === '/vault/dependencies')
  );
  if (needsOrganisation) {
    return <Navigate to="/choose-organisation" replace state={{ from: location.pathname }} />;
  }

  return children;
};

export default ProtectedRoute;
