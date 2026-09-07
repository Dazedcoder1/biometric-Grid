// src/components/ProtectedRoute.jsx
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const ProtectedRoute = ({ children, allowedRoles }) => {
  const { user, token, authType, loading } = useAuth();

  console.log('🛡️ ProtectedRoute check:', { user, token, authType, loading, allowedRoles });

  // Show loading state while checking authentication
  if (loading) {
    console.log('⏳ Still loading...');
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

  // Check if user is authenticated
  // For API key auth, we don't have a token but we have authType === 'api_key' and user
  const isAuthenticated = token || authType === 'api_key';
  
  if (!isAuthenticated || !user) {
    console.log('❌ Not authenticated, redirecting to home');
    return <Navigate to="/" replace />;
  }

  // Check if user has required role
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    console.log('❌ Role not allowed, redirecting to appropriate dashboard');
    // Redirect to appropriate dashboard based on role
    if (user.role === 'tenant_admin') {
      return <Navigate to="/super/dashboard" replace />;
    } else if (user.role === 'org_admin') {
      return <Navigate to="/org/dashboard" replace />;
    } else if (user.role === 'employee') {
      return <Navigate to="/emp/dashboard" replace />;
    }
    return <Navigate to="/" replace />;
  }

  console.log('✅ Access granted to protected route');
  return children;
};

export default ProtectedRoute;