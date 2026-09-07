// src/pages/org/ChangePassword.jsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, CheckCircle, AlertCircle, Eye, EyeOff, ArrowLeft } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { orgApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const OrgChangePassword = () => {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [formData, setFormData] = useState({
    old_password: '',
    new_password: '',
    confirm_password: '',
  });
  const [showOldPassword, setShowOldPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const validatePassword = (password) => {
    if (password.length < 8) {
      return 'Password must be at least 8 characters';
    }
    if (!/[A-Z]/.test(password)) {
      return 'Password must contain at least one uppercase letter';
    }
    if (!/[a-z]/.test(password)) {
      return 'Password must contain at least one lowercase letter';
    }
    if (!/[0-9]/.test(password)) {
      return 'Password must contain at least one number';
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    // Validate new password
    const validationError = validatePassword(formData.new_password);
    if (validationError) {
      setError(validationError);
      return;
    }

    // Check if passwords match
    if (formData.new_password !== formData.confirm_password) {
      setError('New passwords do not match');
      return;
    }

    setLoading(true);

    try {
      await orgApi.changePassword({
        old_password: formData.old_password,
        new_password: formData.new_password,
      });
      
      setSuccess('Password changed successfully!');
      
      // Clear form
      setFormData({
        old_password: '',
        new_password: '',
        confirm_password: '',
      });
      
      setTimeout(() => {
        setSuccess('');
      }, 5000);
      
    } catch (err) {
      console.error('Change password error:', err);
      setError(err.message || 'Failed to change password. Please check your current password.');
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
      title="Change Password"
      role="orgadmin"
      label="Department Admin"
      abbr="DA"
      color="#00d4aa"
      bgColor="rgba(0,212,170,0.15)"
    >
      <style>{`
        .password-card {
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

      <div className="card-box password-card">
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
            background: 'rgba(0,212,170,0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Lock size={24} style={{ color: '#00d4aa' }} />
          </div>
          <div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '4px' }}>Change Password</h3>
            <p style={{ color: 'var(--text3)', fontSize: '0.8rem' }}>
              Update your department admin account password
            </p>
          </div>
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
          {/* Old Password Field */}
          <div className="form-group">
            <label className="form-label">Current Password</label>
            <div className="input-with-icon">
              <input
                type={showOldPassword ? 'text' : 'password'}
                name="old_password"
                className="form-input"
                placeholder="Enter your current password"
                value={formData.old_password}
                onChange={handleInputChange}
                required
                disabled={loading}
              />
              <button
                type="button"
                className="toggle-visibility"
                onClick={() => setShowOldPassword(!showOldPassword)}
              >
                {showOldPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* New Password Field */}
          <div className="form-group" style={{ marginTop: '1rem' }}>
            <label className="form-label">New Password</label>
            <div className="input-with-icon">
              <input
                type={showNewPassword ? 'text' : 'password'}
                name="new_password"
                className="form-input"
                placeholder="Enter new password"
                value={formData.new_password}
                onChange={handleInputChange}
                required
                disabled={loading}
              />
              <button
                type="button"
                className="toggle-visibility"
                onClick={() => setShowNewPassword(!showNewPassword)}
              >
                {showNewPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Confirm Password Field */}
          <div className="form-group" style={{ marginTop: '1rem' }}>
            <label className="form-label">Confirm New Password</label>
            <div className="input-with-icon">
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                name="confirm_password"
                className="form-input"
                placeholder="Confirm new password"
                value={formData.confirm_password}
                onChange={handleInputChange}
                required
                disabled={loading}
              />
              <button
                type="button"
                className="toggle-visibility"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              >
                {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Requirements */}
          <div className="requirements">
            <strong>Password Requirements:</strong>
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
              {loading ? 'Changing Password...' : 'Change Password'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate('/org/dashboard')}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <ArrowLeft size={16} /> Cancel
            </button>
          </div>
        </form>

        {/* Security Note */}
        <div style={{
          marginTop: '1.5rem',
          padding: '0.75rem',
          background: 'rgba(0,212,170,0.05)',
          borderRadius: '8px',
          fontSize: '0.7rem',
          color: 'var(--text3)',
          textAlign: 'center'
        }}>
          🔒 For security, you'll need to login again after changing your password.
        </div>
      </div>
    </DashboardLayout>
  );
};

export default OrgChangePassword;