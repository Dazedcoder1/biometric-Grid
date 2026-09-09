// src/components/ConfirmationModal.jsx
import React from 'react';
import { AlertTriangle, X, CheckCircle, AlertCircle, Info } from 'lucide-react';

const ConfirmationModal = ({ 
  isOpen, 
  onClose, 
  onConfirm, 
  title, 
  message, 
  confirmText = "Confirm", 
  cancelText = "Cancel",
  type = "warning",
  confirmVariant = "danger",
  loading = false
}) => {
  if (!isOpen) return null;

  const getIcon = () => {
    switch (type) {
      case 'danger':
        return <AlertTriangle size={48} style={{ color: '#ef4444' }} />;
      case 'success':
        return <CheckCircle size={48} style={{ color: '#22c55e' }} />;
      case 'info':
        return <Info size={48} style={{ color: '#3b82f6' }} />;
      default:
        return <AlertCircle size={48} style={{ color: '#f59e0b' }} />;
    }
  };

  const getConfirmButtonClass = () => {
    switch (confirmVariant) {
      case 'danger':
        return 'btn-red';
      case 'success':
        return 'btn-teal';
      default:
        return 'btn-teal';
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>
          <X size={20} />
        </button>
        
        <div className="modal-icon">{getIcon()}</div>
        
        <h3 className="modal-title">{title}</h3>
        <p className="modal-message">{message}</p>
        
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose} disabled={loading}>
            {cancelText}
          </button>
          <button className={`btn ${getConfirmButtonClass()}`} onClick={onConfirm} disabled={loading}>
            {loading ? 'Processing...' : confirmText}
          </button>
        </div>
      </div>

      <style>{`
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0,0,0,0.8);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 2000;
          backdrop-filter: blur(8px);
          animation: fadeIn 0.2s ease;
        }
        .modal-content {
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 24px;
          max-width: 420px;
          width: 90%;
          padding: 2rem;
          position: relative;
          text-align: center;
          animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .modal-close {
          position: absolute;
          top: 1rem;
          right: 1rem;
          background: none;
          border: none;
          color: var(--text3);
          cursor: pointer;
          padding: 4px;
          border-radius: 8px;
          transition: all 0.2s;
        }
        .modal-close:hover {
          background: var(--bg3);
          color: var(--text);
        }
        .modal-icon {
          margin-bottom: 1.25rem;
        }
        .modal-title {
          font-size: 1.3rem;
          font-weight: 600;
          margin-bottom: 0.5rem;
          color: var(--text);
        }
        .modal-message {
          color: var(--text2);
          font-size: 0.9rem;
          line-height: 1.5;
          margin-bottom: 1.5rem;
        }
        .modal-actions {
          display: flex;
          gap: 1rem;
          justify-content: center;
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
};

export default ConfirmationModal;