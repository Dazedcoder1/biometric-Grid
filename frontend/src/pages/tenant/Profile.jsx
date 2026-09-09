// src/pages/tenant/Profile.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { 
  Building2, 
  Calendar, 
  Shield, 
  Key, 
  RefreshCw, 
  AlertCircle, 
  CheckCircle,
  Copy,
  Eye,
  EyeOff,
  User,
  Mail,
  Clock
} from 'lucide-react';

const TenantProfile = () => {
  const { logout } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchProfile();
  }, []);

  const fetchProfile = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await tenantApi.getTenantProfile();
      console.log("Tenant profile:", data);
      setProfile(data);
    } catch (err) {
      console.error('Failed to fetch profile:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load profile information');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text, type) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setSuccess(`${type} copied to clipboard!`);
    setTimeout(() => {
      setCopied(false);
      setSuccess('');
    }, 2000);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getApiKeyDisplay = () => {
    if (!profile?.api_key) return '••••••••••••••••';
    if (showApiKey) return profile.api_key;
    return '••••••••••••••••••••••••••••••••';
  };

  if (loading) {
    return (
      <DashboardLayout
        title="Organization Profile"
        role="superadmin"
        label="Tenant Admin"
        abbr="TA"
        color="#a855f7"
        bgColor="rgba(168,85,247,0.15)"
      >
        <div className="skeleton-loader" style={{ maxWidth: '560px', margin: '0 auto' }}>
          <div style={{ background: 'var(--bg2)', borderRadius: '16px', height: '400px', animation: 'pulse 1.5s ease-in-out infinite' }}></div>
        </div>
        <style>{`@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }`}</style>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      title="Organization Profile"
      role="superadmin"
      label="Tenant Admin"
      abbr="TA"
      color="#a855f7"
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        .profile-card {
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
        .info-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 1rem 0;
          border-bottom: 1px solid var(--border);
        }
        .info-row:last-child {
          border-bottom: none;
        }
        .info-label {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.85rem;
          color: var(--text3);
          font-family: var(--mono);
        }
        .info-value {
          font-size: 0.95rem;
          font-weight: 500;
          color: var(--text);
          word-break: break-all;
          text-align: right;
        }
        .api-key-container {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
          justify-content: flex-end;
        }
        .api-key-value {
          font-family: var(--mono);
          font-size: 0.8rem;
          background: var(--bg3);
          padding: 4px 8px;
          border-radius: 6px;
          letter-spacing: 0.5px;
        }
        .icon-btn {
          background: none;
          border: none;
          cursor: pointer;
          padding: 4px;
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
          color: var(--text3);
        }
        .icon-btn:hover {
          background: var(--bg3);
          color: var(--text);
        }
        .success-toast {
          position: fixed;
          bottom: 24px;
          right: 24px;
          background: rgba(34,197,94,0.95);
          color: white;
          padding: 12px 20px;
          border-radius: 12px;
          z-index: 1000;
          animation: slideIn 0.3s ease;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .error-toast {
          position: fixed;
          bottom: 24px;
          right: 24px;
          background: rgba(239,68,68,0.95);
          color: white;
          padding: 12px 20px;
          border-radius: 12px;
          z-index: 1000;
          animation: slideIn 0.3s ease;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        .stat-card {
          transition: all 0.2s;
          cursor: pointer;
        }
        .stat-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 24px rgba(0,0,0,0.15);
        }
      `}</style>

      {success && (
        <div className="success-toast">
          <CheckCircle size={18} /> {success}
        </div>
      )}
      {error && (
        <div className="error-toast">
          <AlertCircle size={18} /> {error}
        </div>
      )}

      {/* Stats Overview */}
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-card purple">
          <div className="stat-label"><Building2 size={14} /> Organization</div>
          <div className="stat-value" style={{ fontSize: '1.2rem' }}>{profile?.name || 'N/A'}</div>
          <div className="stat-sub">Tenant ID: {profile?.id || 'N/A'}</div>
        </div>
        <div className="stat-card teal">
          <div className="stat-label"><Calendar size={14} /> Member Since</div>
          <div className="stat-value" style={{ fontSize: '1rem' }}>{formatDate(profile?.created_at).split(',')[0]}</div>
          <div className="stat-sub">Registered</div>
        </div>
        <div className="stat-card amber">
          <div className="stat-label"><Shield size={14} /> Role</div>
          <div className="stat-value" style={{ fontSize: '1.2rem' }}>Tenant Admin</div>
          <div className="stat-sub">Full access</div>
        </div>
      </div>

      {/* Profile Details Card */}
      <div className="card-box profile-card">
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '16px', 
          marginBottom: '1.5rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid var(--border)'
        }}>
          <div style={{
            width: '64px',
            height: '64px',
            borderRadius: '16px',
            background: 'rgba(168,85,247,0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Building2 size={32} style={{ color: '#a855f7' }} />
          </div>
          <div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '4px' }}>Organization Details</h3>
            <p style={{ color: 'var(--text3)', fontSize: '0.8rem' }}>
              Your organization's profile information
            </p>
          </div>
          <button 
            className="btn btn-ghost" 
            onClick={fetchProfile} 
            style={{ marginLeft: 'auto', padding: '6px 12px' }}
            title="Refresh"
          >
            <RefreshCw size={16} />
          </button>
        </div>

        <div className="info-row">
          <div className="info-label">
            <Building2 size={16} />
            Organization Name
          </div>
          <div className="info-value">{profile?.name || 'N/A'}</div>
        </div>

        <div className="info-row">
          <div className="info-label">
            <Shield size={16} />
            Tenant ID
          </div>
          <div className="info-value">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'flex-end' }}>
              <code style={{ background: 'var(--bg3)', padding: '4px 8px', borderRadius: '6px', fontSize: '0.8rem' }}>
                {profile?.id || 'N/A'}
              </code>
              {profile?.id && (
                <button 
                  className="icon-btn" 
                  onClick={() => copyToClipboard(profile.id.toString(), 'Tenant ID')}
                  title="Copy Tenant ID"
                >
                  <Copy size={14} />
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="info-row">
          <div className="info-label">
            <Key size={16} />
            API Key
          </div>
          <div className="info-value">
            <div className="api-key-container">
              <code className="api-key-value">
                {getApiKeyDisplay()}
              </code>
              <button 
                className="icon-btn" 
                onClick={() => setShowApiKey(!showApiKey)}
                title={showApiKey ? "Hide API Key" : "Show API Key"}
              >
                {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
              <button 
                className="icon-btn" 
                onClick={() => copyToClipboard(profile?.api_key, 'API Key')}
                title="Copy API Key"
              >
                <Copy size={14} />
              </button>
            </div>
          </div>
        </div>

        <div className="info-row">
          <div className="info-label">
            <Calendar size={16} />
            Registered On
          </div>
          <div className="info-value">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'flex-end' }}>
              <Clock size={14} style={{ color: 'var(--text3)' }} />
              {formatDate(profile?.created_at)}
            </div>
          </div>
        </div>
      </div>

      {/* Security Notice */}
      <div className="card-box profile-card" style={{ 
        marginTop: '1rem', 
        background: 'rgba(168,85,247,0.05)',
        borderColor: 'rgba(168,85,247,0.2)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Shield size={20} style={{ color: '#a855f7' }} />
          <div>
            <div style={{ fontWeight: 500, marginBottom: '4px' }}>Security Information</div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text3)', margin: 0 }}>
              Your API key is sensitive information. Keep it secure and never share it publicly.
              You can regenerate your API key from the settings panel if needed.
            </p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default TenantProfile;