// src/context/AuthContext.jsx
import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('access_token'));
  const [authType, setAuthType] = useState(localStorage.getItem('auth_type'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    console.log('🔍 AuthContext initializing...');
    console.log('Auth type from localStorage:', authType);
    console.log('Has API key:', !!localStorage.getItem('api_key'));
    console.log('Has Bearer token:', !!localStorage.getItem('access_token'));
    
    const initAuth = () => {
      if (authType === 'api_key') {
        // API key based auth (tenant)
        const apiKey = localStorage.getItem('api_key');
        if (apiKey) {
          console.log('✅ Setting up Tenant Admin user from API key');
          const userData = {
            id: null,
            role: 'tenant_admin',
            name: 'Tenant Admin',
            email: null,
          };
          setUser(userData);
          console.log('👤 User set:', userData);
        } else {
          console.warn('⚠️ Auth type is api_key but no API key found');
          performLogout();
        }
      } else if (token) {
        try {
          const payload = JSON.parse(atob(token.split('.')[1]));
          console.log('📦 Token payload:', payload);
          
          let frontendRole = payload.role;
          if (payload.role === 'tenant_admin' || payload.role === 'superadmin') {
            frontendRole = 'tenant_admin';
          } else if (payload.role === 'org_admin' || payload.role === 'department_admin') {
            frontendRole = 'org_admin';
          } else if (payload.role === 'employee' || payload.role === 'user') {
            frontendRole = 'employee';
          }
          
          const userData = {
            id: payload.sub || payload.user_id || payload.id,
            role: frontendRole,
            originalRole: payload.role,
            name: payload.name,
            email: payload.email || payload.sub,
          };
          setUser(userData);
          console.log('👤 User set from Bearer token:', userData);
        } catch (e) {
          console.error('❌ Invalid token:', e);
          performLogout();
        }
      } else {
        console.log('ℹ️ No auth credentials found');
        setUser(null);
      }
      setLoading(false);
    };
    
    initAuth();
  }, [token, authType]);

  const login = (accessToken, userData, isApiKeyAuth = false) => {
    console.log('🔐 Login called, isApiKeyAuth:', isApiKeyAuth);
    console.log('📝 User data:', userData);
    
    if (isApiKeyAuth) {
      // For API key auth, we don't store token
      localStorage.setItem('auth_type', 'api_key');
      localStorage.setItem('user', JSON.stringify(userData));
      setAuthType('api_key');
      setUser(userData);
      console.log('✅ API Key auth user set:', userData);
      console.log('✅ auth_type set to:', localStorage.getItem('auth_type'));
    } else {
      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('auth_type', 'bearer');
      localStorage.setItem('user', JSON.stringify(userData));
      setToken(accessToken);
      setAuthType('bearer');
      setUser(userData);
      console.log('✅ Bearer token auth user set:', userData);
    }
  };

  const performLogout = () => {
    console.log('🔓 Performing logout - clearing all localStorage...');
    
    // Clear ALL auth-related items from localStorage
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('api_key');
    localStorage.removeItem('auth_type');
    localStorage.removeItem('user');
    
    // Clear any other potential auth items
    localStorage.removeItem('token');
    localStorage.removeItem('userData');
    localStorage.removeItem('user_role');
    localStorage.removeItem('username');
    localStorage.removeItem('password');
    
    // Reset state
    setToken(null);
    setAuthType(null);
    setUser(null);
    
    console.log('✅ All auth data cleared from localStorage');
  };

  const logout = () => {
    performLogout();
    // Force a hard redirect to completely reset the app state
    window.location.href = '/';
  };

  const hasRole = (allowedRoles) => {
    if (!user) return false;
    const hasRole = allowedRoles.includes(user.role);
    console.log('🔍 hasRole check:', { userRole: user.role, allowedRoles, hasRole });
    return hasRole;
  };

  return (
    <AuthContext.Provider value={{ user, token, authType, login, logout, loading, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);