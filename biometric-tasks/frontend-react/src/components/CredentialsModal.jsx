// src/components/CredentialsModal.jsx
import React from 'react';
import { X, Copy, CheckCircle, User, Fingerprint, Key, Mail, Building2 } from 'lucide-react';

const CredentialsModal = ({ isOpen, onClose, credentials, title, type }) => {
  const [copiedField, setCopiedField] = React.useState(null);

  if (!isOpen || !credentials) return null;

  const copyToClipboard = (text, fieldName) => {
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const getFieldIcon = (field) => {
    switch (field) {
      case 'name': return <User size={16} />;
      case 'employee_code': return <Fingerprint size={16} />;
      case 'finger_id': return <Fingerprint size={16} />;
      case 'email': return <Mail size={16} />;
      case 'password': return <Key size={16} />;
      case 'department': return <Building2 size={16} />;
      default: return null;
    }
  };

  const getFieldLabel = (field) => {
    const labels = {
      name: 'Full Name',
      employee_code: 'Employee Code',
      finger_id: 'Fingerprint ID',
      email: 'Email Address',
      password: 'Password',
      department: 'Department',
      dept_name: 'Department'
    };
    return labels[field] || field;
  };

  const isEmployee = type === 'employee';
  const isOrgAdmin = type === 'org_admin';

  // Define which fields to show based on type
  const fieldsToShow = isEmployee 
    ? ['name', 'employee_code', 'finger_id', 'password']
    : ['name', 'email', 'dept_name', 'password'];

  return (
    <div className="credentials-modal-overlay" onClick={onClose}>
      <div className="credentials-modal" onClick={(e) => e.stopPropagation()}>
        <button className="credentials-modal-close" onClick={onClose}>
          <X size={20} />
        </button>

        <div className="credentials-modal-header">
          <div className="credentials-modal-icon">
            <CheckCircle size={32} />
          </div>
          <h3>{title || (isEmployee ? 'Employee Created Successfully!' : 'Org Admin Created Successfully!')}</h3>
          <p>Please save these credentials. They will not be shown again.</p>
        </div>

        <div className="credentials-modal-body">
          {fieldsToShow.map((field) => {
            const value = credentials[field];
            if (!value) return null;
            
            return (
              <div key={field} className="credential-row">
                <div className="credential-label">
                  {getFieldIcon(field)}
                  <span>{getFieldLabel(field)}</span>
                </div>
                <div className="credential-value-wrapper">
                  <code className="credential-value">{value}</code>
                  <button 
                    className="credential-copy-btn"
                    onClick={() => copyToClipboard(value, field)}
                    title="Copy to clipboard"
                  >
                    {copiedField === field ? <CheckCircle size={14} /> : <Copy size={14} />}
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        <div className="credentials-modal-footer">
          <button className="credentials-modal-btn" onClick={onClose}>
            I've Saved These Credentials
          </button>
        </div>
      </div>

      <style>{`
        .credentials-modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0,0,0,0.85);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 10000;
          backdrop-filter: blur(8px);
          animation: fadeIn 0.2s ease;
        }
        
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        
        .credentials-modal {
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 24px;
          max-width: 480px;
          width: 90%;
          position: relative;
          animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
          box-shadow: 0 25px 50px rgba(0,0,0,0.3);
        }
        
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(30px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        
        .credentials-modal-close {
          position: absolute;
          top: 16px;
          right: 16px;
          background: var(--bg3);
          border: none;
          color: var(--text3);
          cursor: pointer;
          padding: 6px;
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
          z-index: 10;
        }
        
        .credentials-modal-close:hover {
          background: var(--bg4);
          color: var(--text);
        }
        
        .credentials-modal-header {
          text-align: center;
          padding: 28px 28px 16px 28px;
          border-bottom: 1px solid var(--border);
        }
        
        .credentials-modal-icon {
          width: 64px;
          height: 64px;
          background: rgba(34,197,94,0.15);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 16px;
          color: #22c55e;
        }
        
        .credentials-modal-header h3 {
          font-size: 1.3rem;
          font-weight: 600;
          margin-bottom: 8px;
          color: var(--text);
        }
        
        .credentials-modal-header p {
          font-size: 0.8rem;
          color: var(--text3);
          margin: 0;
        }
        
        .credentials-modal-body {
          padding: 20px 28px;
          max-height: 400px;
          overflow-y: auto;
        }
        
        .credential-row {
          margin-bottom: 16px;
          padding-bottom: 16px;
          border-bottom: 1px solid var(--border);
        }
        
        .credential-row:last-child {
          border-bottom: none;
          margin-bottom: 0;
          padding-bottom: 0;
        }
        
        .credential-label {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.7rem;
          font-family: var(--mono);
          color: var(--text3);
          text-transform: uppercase;
          margin-bottom: 8px;
        }
        
        .credential-value-wrapper {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
        }
        
        .credential-value {
          font-size: 0.9rem;
          font-family: var(--mono);
          color: var(--teal);
          background: var(--bg3);
          padding: 8px 12px;
          border-radius: 8px;
          flex: 1;
          word-break: break-all;
          white-space: pre-wrap;
        }
        
        .credential-copy-btn {
          background: var(--bg3);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 6px 10px;
          cursor: pointer;
          color: var(--text2);
          transition: all 0.2s;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        
        .credential-copy-btn:hover {
          background: var(--bg4);
          color: var(--text);
          border-color: var(--teal);
        }
        
        .credentials-modal-footer {
          padding: 16px 28px 28px 28px;
          border-top: 1px solid var(--border);
        }
        
        .credentials-modal-btn {
          width: 100%;
          padding: 12px;
          background: var(--teal);
          border: none;
          border-radius: 12px;
          color: white;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
          font-size: 0.85rem;
        }
        
        .credentials-modal-btn:hover {
          background: var(--teal2);
          transform: translateY(-1px);
        }
        
        @media (max-width: 768px) {
          .credentials-modal-body {
            padding: 16px 20px;
          }
          .credential-value {
            font-size: 0.75rem;
          }
        }
      `}</style>
    </div>
  );
};

export default CredentialsModal;