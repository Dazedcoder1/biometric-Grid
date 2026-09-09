// src/components/PersistentToast.jsx
import React, { useEffect } from 'react';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle, Copy } from 'lucide-react';

const PersistentToast = ({ message, type = 'success', onClose, autoClose = false, duration = 5000 }) => {
  useEffect(() => {
    if (autoClose) {
      const timer = setTimeout(() => {
        onClose();
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [autoClose, duration, onClose]);

  const getIcon = () => {
    switch (type) {
      case 'success':
        return <CheckCircle size={20} />;
      case 'error':
        return <AlertCircle size={20} />;
      case 'warning':
        return <AlertTriangle size={20} />;
      case 'info':
        return <Info size={20} />;
      default:
        return <CheckCircle size={20} />;
    }
  };

  const getBgColor = () => {
    switch (type) {
      case 'success':
        return 'linear-gradient(135deg, rgba(34,197,94,0.95), rgba(22,163,74,0.95))';
      case 'error':
        return 'linear-gradient(135deg, rgba(239,68,68,0.95), rgba(220,38,38,0.95))';
      case 'warning':
        return 'linear-gradient(135deg, rgba(245,158,11,0.95), rgba(217,119,6,0.95))';
      case 'info':
        return 'linear-gradient(135deg, rgba(59,130,246,0.95), rgba(37,99,235,0.95))';
      default:
        return 'linear-gradient(135deg, rgba(34,197,94,0.95), rgba(22,163,74,0.95))';
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    // Optional: show a small tooltip or secondary notification
  };

  // Parse message to check if it contains password
  const hasPassword = message.includes('🔑') || message.toLowerCase().includes('password');
  const passwordMatch = message.match(/Password: (\S+)/);
  const password = passwordMatch ? passwordMatch[1] : null;

  return (
    <div className="persistent-toast" style={{
      position: 'fixed',
      bottom: '24px',
      right: '24px',
      zIndex: 10000,
      animation: 'slideInRight 0.3s ease',
    }}>
      <div style={{
        background: getBgColor(),
        backdropFilter: 'blur(8px)',
        borderRadius: '16px',
        padding: '16px 20px',
        minWidth: '280px',
        maxWidth: '420px',
        boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
        border: '1px solid rgba(255,255,255,0.2)',
        position: 'relative',
      }}>
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '12px',
            right: '12px',
            background: 'rgba(0,0,0,0.2)',
            border: 'none',
            borderRadius: '8px',
            padding: '4px',
            cursor: 'pointer',
            color: 'white',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(0,0,0,0.4)'}
          onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(0,0,0,0.2)'}
        >
          <X size={16} />
        </button>

        <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', paddingRight: '24px' }}>
          <div style={{ flexShrink: 0 }}>{getIcon()}</div>
          <div style={{ flex: 1, fontSize: '0.85rem', lineHeight: 1.5, whiteSpace: 'pre-line', wordBreak: 'break-word' }}>
            {message.split('\n').map((line, idx) => {
              // Check if line contains password for special styling
              if (line.includes('🔑') || line.toLowerCase().includes('password')) {
                const passwordMatch = line.match(/Password: (\S+)/);
                const pwd = passwordMatch ? passwordMatch[1] : null;
                return (
                  <div key={idx} style={{ marginTop: idx > 0 ? '8px' : 0 }}>
                    {line.split('Password:')[0]}
                    {pwd && (
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '8px',
                        background: 'rgba(0,0,0,0.2)',
                        padding: '4px 8px',
                        borderRadius: '6px',
                        fontFamily: 'var(--mono)',
                        fontSize: '0.8rem',
                        marginLeft: '4px',
                      }}>
                        <code style={{ color: '#fbbf24' }}>{pwd}</code>
                        <button
                          onClick={() => copyToClipboard(pwd)}
                          style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            color: 'white',
                            padding: '2px',
                            display: 'flex',
                            alignItems: 'center',
                            borderRadius: '4px',
                          }}
                          title="Copy password"
                        >
                          <Copy size={12} />
                        </button>
                      </span>
                    )}
                  </div>
                );
              }
              return <div key={idx}>{line}</div>;
            })}
          </div>
        </div>

        {hasPassword && (
          <div style={{
            marginTop: '12px',
            paddingTop: '8px',
            borderTop: '1px solid rgba(255,255,255,0.2)',
            fontSize: '0.7rem',
            opacity: 0.8,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}>
            <span>⚠️ Please save this password. It won't be shown again.</span>
          </div>
        )}
      </div>

      <style>{`
        @keyframes slideInRight {
          from {
            transform: translateX(100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
};

export default PersistentToast;