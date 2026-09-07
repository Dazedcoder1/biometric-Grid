import React, { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShieldCheck, Moon, Sun, ArrowRight } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';

const Gateway = () => {
  const { theme, toggleTheme } = useTheme();
  const { user, loading, autoLoginInProgress } = useAuth();
  const navigate = useNavigate();

  // Auto-redirect if already logged in
  useEffect(() => {
    if (!loading && !autoLoginInProgress && user) {
      console.log('🔄 User already logged in, redirecting to dashboard...');
      if (user.role === 'tenant_admin') {
        navigate('/super/dashboard', { replace: true });
      } else if (user.role === 'org_admin') {
        navigate('/org/dashboard', { replace: true });
      } else if (user.role === 'employee') {
        navigate('/emp/dashboard', { replace: true });
      }
    }
  }, [user, loading, autoLoginInProgress, navigate]);

  // Show loading spinner while checking auth or auto-login in progress
  if (loading || autoLoginInProgress) {
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
          <div style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>
            {autoLoginInProgress ? 'Signing you in...' : 'Loading...'}
          </div>
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

  return (
    <div id="landing">
      <div className="grid-bg"></div>
      
      <div style={{ position: 'absolute', top: '20px', right: '20px', zIndex: 50 }}>
        <button 
          className="tb-action-icon theme-toggle" 
          onClick={toggleTheme}
          style={{ fontSize: '1.4rem' }}
        >
          {theme === 'dark' ? <Sun size={24} /> : <Moon size={24} />}
        </button>
      </div>

      <div style={{ position: 'relative', zIndex: 1, width: '100%', maxWidth: '900px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div className="landing-logo">
          <div className="logo-icon">
            <ShieldCheck color="white" size={28} />
          </div>
          <div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: '1.5rem', fontWeight: 700, color: 'var(--text)' }}>The Sentinel</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text3)' }}>Biometric Orchestration Platform</div>
          </div>
        </div>

        <p className="landing-sub">Select your authorization level to continue to your dashboard</p>

        <div className="role-cards">
          <Link to="/login/tenant" className="role-card super">
            <div className="role-icon">⬡</div>
            <h3>Tenant Admin</h3>
            <p>Global hardware orchestration, multi-tenant governance, and core system telemetry</p>
            <div className="role-enter">Enter Command Center <ArrowRight size={14} style={{ marginLeft: '6px' }} /></div>
          </Link>

          <Link to="/login/org" className="role-card org">
            <div className="role-icon">◈</div>
            <h3>Org Admin</h3>
            <p>Manage organization-wide attendance protocols, local devices, and department biometric logs</p>
            <div className="role-enter">Access Dashboard <ArrowRight size={14} style={{ marginLeft: '6px' }} /></div>
          </Link>

          <Link to="/login/employee" className="role-card employee">
            <div className="role-icon">◉</div>
            <h3>Employee</h3>
            <p>Personal identity verification, attendance history, and mobile biometric credential management</p>
            <div className="role-enter" style={{ color: 'var(--amber)' }}>View Identity Hub <ArrowRight size={14} style={{ marginLeft: '6px' }} /></div>
          </Link>
        </div>

        <div className="status-bar">
          <div className="status-item"><div className="dot"></div>GLOBAL SYNC ACTIVE</div>
          <div className="status-item"><div className="dot" style={{ background: 'var(--blue)' }}></div>AES-256 ENCRYPTED</div>
          <div className="status-item"><div className="dot" style={{ background: '#a855f7' }}></div>FIDO2 COMPLIANT</div>
        </div>
      </div>
    </div>
  );
};

export default Gateway;