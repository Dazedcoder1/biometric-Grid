// src/pages/tenant/ChangeApiKey.jsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Key, CheckCircle, AlertCircle, Eye, EyeOff, ArrowLeft } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const ChangeApiKey = () => {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [formData, setFormData] = useState({
    api_key: '',
    confirm_api_key: '',
  });
  const [showApiKey, setShowApiKey] = useState(false);
  const [showConfirmApiKey, setShowConfirmApiKey] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const validateApiKey = (key) => {
    if (key.length < 8) {
      return 'API key must be at least 8 characters';
    }
    if (!/[A-Z]/.test(key)) {
      return 'API key must contain at least one uppercase letter';
    }
    if (!/[a-z]/.test(key)) {
      return 'API key must contain at least one lowercase letter';
    }
    if (!/[0-9]/.test(key)) {
      return 'API key must contain at least one number';
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    // Validate API key
    const validationError = validateApiKey(formData.api_key);
    if (validationError) {
      setError(validationError);
      return;
    }

    // Check if API keys match
    if (formData.api_key !== formData.confirm_api_key) {
      setError('API keys do not match');
      return;
    }

    setLoading(true);

    try {
      // Call the change API key endpoint
      await tenantApi.changeApiKey(formData.api_key);
      
      setSuccess('API key changed successfully!');
      
      // Clear form
      setFormData({ api_key: '', confirm_api_key: '' });
      
      // Optional: Show warning that old API key no longer works
      setTimeout(() => {
        setSuccess('');
      }, 5000);
      
    } catch (err) {
      console.error('Change API key error:', err);
      setError(err.message || 'Failed to change API key');
      if (err?.response?.status === 401) {
        logout();
        navigate('/');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    // Clear errors when user starts typing
    if (error) setError('');
    if (success) setSuccess('');
  };

  return (
    <DashboardLayout
      title="Change API Key"
      role="superadmin"
      label="Tenant Admin"
      abbr="TA"
      color="#a855f7"
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        .api-key-card {
          max-width: 560px;
          margin: 0 auto;
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
        .warning-box {
          background: rgba(245,158,11,0.1);
          border: 1px solid rgba(245,158,11,0.3);
          border-radius: 12px;
          padding: 1rem;
          margin-bottom: 1.5rem;
        }
        .success-box {
          background: rgba(34,197,94,0.1);
          border: 1px solid rgba(34,197,94,0.3);
          border-radius: 12px;
          padding: 1rem;
          margin-bottom: 1.5rem;
          color: #4ade80;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .error-box {
          background: rgba(239,68,68,0.1);
          border: 1px solid rgba(239,68,68,0.3);
          border-radius: 12px;
          padding: 1rem;
          margin-bottom: 1.5rem;
          color: #f87171;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .input-with-icon {
          position: relative;
        }
        .input-with-icon input {
          width: 100%;
          padding-right: 40px;
        }
        .toggle-visibility {
          position: absolute;
          right: 12px;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          color: var(--text3);
          cursor: pointer;
          padding: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .toggle-visibility:hover {
          color: var(--text);
        }
        .requirements {
          margin-top: 0.5rem;
          padding: 0.75rem;
          background: var(--bg3);
          border-radius: 8px;
          font-size: 0.7rem;
          color: var(--text3);
        }
        .requirements ul {
          margin: 0.25rem 0 0 1rem;
          padding: 0;
        }
        .requirements li {
          margin: 0.25rem 0;
        }
      `}</style>

      <div className="card-box api-key-card">
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '12px', 
          marginBottom: '1.5rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid var(--border)'
        }}>
          <div style={{
            width: '48px',
            height: '48px',
            borderRadius: '12px',
            background: 'rgba(168,85,247,0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Key size={24} style={{ color: '#a855f7' }} />
          </div>
          <div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '4px' }}>Change API Key</h3>
            <p style={{ color: 'var(--text3)', fontSize: '0.8rem' }}>
              Update your organization's API authentication key
            </p>
          </div>
        </div>

        {/* Warning Box */}
        <div className="warning-box">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <AlertCircle size={18} style={{ color: '#f59e0b' }} />
            <strong style={{ fontSize: '0.85rem' }}>Important Notice</strong>
          </div>
          <p style={{ fontSize: '0.8rem', margin: 0, color: 'var(--text2)' }}>
            Changing your API key will immediately invalidate the old key. 
            All services and integrations using the old key will stop working until updated with the new key.
          </p>
        </div>

        {/* Success Message */}
        {success && (
          <div className="success-box">
            <CheckCircle size={18} />
            {success}
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="error-box">
            <AlertCircle size={18} />
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* New API Key Field */}
          <div className="form-group">
            <label className="form-label">New API Key</label>
            <div className="input-with-icon">
              <input
                type={showApiKey ? 'text' : 'password'}
                name="api_key"
                className="form-input"
                placeholder="Enter new API key"
                value={formData.api_key}
                onChange={handleInputChange}
                required
                disabled={loading}
              />
              <button
                type="button"
                className="toggle-visibility"
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Confirm API Key Field */}
          <div className="form-group" style={{ marginTop: '1rem' }}>
            <label className="form-label">Confirm New API Key</label>
            <div className="input-with-icon">
              <input
                type={showConfirmApiKey ? 'text' : 'password'}
                name="confirm_api_key"
                className="form-input"
                placeholder="Confirm new API key"
                value={formData.confirm_api_key}
                onChange={handleInputChange}
                required
                disabled={loading}
              />
              <button
                type="button"
                className="toggle-visibility"
                onClick={() => setShowConfirmApiKey(!showConfirmApiKey)}
              >
                {showConfirmApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Requirements */}
          <div className="requirements">
            <strong>Requirements:</strong>
            <ul>
              <li>✓ Minimum 8 characters</li>
              <li>✓ At least one uppercase letter (A-Z)</li>
              <li>✓ At least one lowercase letter (a-z)</li>
              <li>✓ At least one number (0-9)</li>
            </ul>
          </div>

          {/* Buttons */}
          <div style={{ 
            display: 'flex', 
            gap: '1rem', 
            marginTop: '1.5rem',
            paddingTop: '1rem',
            borderTop: '1px solid var(--border)'
          }}>
            <button
              type="submit"
              className="btn btn-teal"
              disabled={loading}
              style={{ flex: 1, padding: '0.75rem' }}
            >
              {loading ? 'Changing API Key...' : 'Change API Key'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate('/super/settings')}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <ArrowLeft size={16} /> Cancel
            </button>
          </div>
        </form>

        {/* Additional Info */}
        <div style={{
          marginTop: '1.5rem',
          padding: '0.75rem',
          background: 'rgba(168,85,247,0.05)',
          borderRadius: '8px',
          fontSize: '0.7rem',
          color: 'var(--text3)',
          textAlign: 'center'
        }}>
          💡 After changing your API key, update it in all connected devices and applications immediately.
        </div>
      </div>
    </DashboardLayout>
  );
};

export default ChangeApiKey;