// src/pages/Login.jsx
import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ShieldCheck, User, Lock, ArrowRight, ChevronLeft, Eye, EyeOff, Key } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { authApi } from '../services/api';

const Login = () => {
  const { role } = useParams();
  const navigate = useNavigate();
  const { login } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  // Form state
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    apiKey: '',
    remember: true, // Default to true for auto-login
  });

  // Configuration based on role
  const roleConfigs = {
    tenant: {
      title: 'Tenant Admin',
      subtitle: 'API Key Authentication',
      color: 'var(--purple)',
      bgColor: 'rgba(168,85,247,0.1)',
      btnText: 'Login with API Key',
      dashPath: '/super/dashboard',
      apiRole: 'tenant_admin',
      icon: '⬡',
      useApiKey: true,
      placeholder: 'Enter your API Key',
      helpText: 'Use the API key provided by your system administrator'
    },
    org: {
      title: 'Org Admin',
      subtitle: 'Department Admin Portal',
      color: 'var(--teal)',
      bgColor: 'rgba(0,212,170,0.1)',
      btnText: 'Login as Org Admin',
      dashPath: '/org/dashboard',
      apiRole: 'org_admin',
      icon: '◈',
      useApiKey: false,
      placeholder: 'Enter your email or employee code',
      helpText: 'Use your organization email or employee ID'
    },
    employee: {
      title: 'Employee',
      subtitle: 'Personal Identity Hub',
      color: 'var(--amber)',
      bgColor: 'rgba(245,158,11,0.1)',
      btnText: 'Login as Employee',
      dashPath: '/emp/dashboard',
      apiRole: 'employee',
      icon: '◉',
      useApiKey: false,
      placeholder: 'Enter your employee code or email',
      helpText: 'Use your employee ID or registered email'
    }
  };

  const config = roleConfigs[role] || roleConfigs.employee;

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      let response;
      let isApiKeyAuth = false;
      let usernameToStore = null;
      let passwordToStore = null;
      
      if (config.useApiKey) {
        // Tenant login with API key
        console.log('🔑 Attempting tenant login with API key...');
        response = await authApi.tenantLogin(formData.apiKey);
        isApiKeyAuth = true;
        usernameToStore = formData.apiKey;
        console.log('✅ Tenant login response:', response);
      } else {
        // Regular login with username/password
        console.log('👤 Attempting regular login...');
        response = await authApi.login(formData.username, formData.password);
        usernameToStore = formData.username;
        passwordToStore = formData.password;
        console.log('✅ Regular login response:', response);
      }

      // Store the token and user info
      if (isApiKeyAuth) {
        const userData = {
          id: response.tenant?.id,
          role: config.apiRole,
          name: response.tenant?.name || 'Tenant Admin',
          email: response.tenant?.email,
        };
        // Pass username (API key) for storage
        await login(null, userData, true, usernameToStore, null);
        console.log('🔐 Login called with userData:', userData);
      } else {
        const userData = {
          id: response.user_id || response.id,
          role: config.apiRole,
          name: response.name || formData.username,
          username: formData.username,
          email: response.email,
        };
        await login(response.access_token, userData, false, usernameToStore, passwordToStore);
        console.log('🔐 Login called with userData:', userData);
      }
      
      // Navigate to dashboard
      console.log('🚀 Navigating to:', config.dashPath);
      navigate(config.dashPath);
      
    } catch (err) {
      console.error('❌ Login error:', err);
      setError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  return (
    <div className="login-page">
      <div className="grid-bg"></div>
      
      <div className="login-container">
        <Link to="/" className="login-back">
          <ChevronLeft size={18} /> Back to Gateway
        </Link>

        <div className="login-card">
          <div className="login-header">
            <div className="login-logo-circle" style={{ background: config.bgColor, color: config.color }}>
              <ShieldCheck size={32} />
            </div>
            <h2 className="login-title">{config.title} Login</h2>
            <p className="login-subtitle">{config.subtitle}</p>
          </div>

          {/* Error Message */}
          {error && (
            <div style={{ 
              background: 'rgba(239,68,68,0.1)', 
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: '8px',
              padding: '0.75rem',
              marginBottom: '1rem',
              color: '#f87171',
              fontSize: '0.85rem',
              textAlign: 'center'
            }}>
              {error}
            </div>
          )}

          <form className="login-form" onSubmit={handleLogin}>
            {config.useApiKey ? (
              <div className="form-group">
                <label className="form-label">API Key</label>
                <div className="input-wrap">
                  <Key className="input-icon" size={18} />
                  <input 
                    type="text" 
                    name="apiKey"
                    className="form-input" 
                    placeholder={config.placeholder}
                    value={formData.apiKey}
                    onChange={handleInputChange}
                    required
                    autoComplete="off"
                  />
                </div>
                <p style={{ fontSize: '0.7rem', color: 'var(--text3)', marginTop: '0.5rem' }}>
                  {config.helpText}
                </p>
              </div>
            ) : (
              <>
                <div className="form-group">
                  <label className="form-label">Username / Employee ID</label>
                  <div className="input-wrap">
                    <User className="input-icon" size={18} />
                    <input 
                      type="text" 
                      name="username"
                      className="form-input" 
                      placeholder={config.placeholder}
                      value={formData.username}
                      onChange={handleInputChange}
                      required
                      autoComplete="username"
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Password</label>
                  <div className="input-wrap">
                    <Lock className="input-icon" size={18} />
                    <input 
                      type={showPassword ? 'text' : 'password'} 
                      name="password"
                      className="form-input" 
                      placeholder="Enter your password" 
                      value={formData.password}
                      onChange={handleInputChange}
                      required
                      autoComplete="current-password"
                    />
                    <button 
                      type="button" 
                      className="password-toggle"
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
              </>
            )}

            <div className="login-options">
              <label className="checkbox-wrap" style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input 
                  type="checkbox" 
                  name="remember"
                  checked={formData.remember}
                  onChange={handleInputChange}
                  style={{ cursor: 'pointer' }} 
                />
                <span>Stay signed in</span>
              </label>
              {!config.useApiKey && (
                <a href="#" className="forgot-link" style={{ color: config.color }}>Forgot Password?</a>
              )}
            </div>

            <button 
              type="submit" 
              className={`login-btn ${loading ? 'loading' : ''}`}
              style={{ background: config.color }}
              disabled={loading}
            >
              {loading ? 'Authenticating...' : (
                <>{config.btnText} <ArrowRight size={18} /></>
              )}
            </button>
          </form>

          <div className="login-footer">
            <p>Authorized access only. All actions are logged under the AES-256 security protocol.</p>
          </div>
        </div>

        <div className="login-status-badges">
          <div className="status-badge"><div className="dot"></div> System Online</div>
          <div className="status-badge"><div className="dot" style={{ background: config.color }}></div> {config.title} Node</div>
        </div>
      </div>
    </div>
  );
};

export default Login;