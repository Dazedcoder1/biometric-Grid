// src/pages/org/Leaves.jsx
import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import ConfirmationModal from '../../components/ConfirmationModal';
import { orgApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { CheckCircle, XCircle, RefreshCw, AlertCircle, Bell } from 'lucide-react';

const Leaves = () => {
  const { logout } = useAuth();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("pending");
  const [showRejectModal, setShowRejectModal] = useState(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [toast, setToast] = useState(null);
  const [processingId, setProcessingId] = useState(null);

  // Fetch leaves from API
  const fetchLeaves = useCallback(async () => {
    setLoading(true);
    try {
      const data = await orgApi.getLeaveRequests();
      console.log("Fetched leaves:", data);
      setRequests(data || []);
    } catch (err) {
      if (err?.response?.status === 401) logout();
      showToast("Failed to load leave requests", "error");
    } finally {
      setLoading(false);
    }
  }, [logout]);

  useEffect(() => { 
    fetchLeaves(); 
  }, [fetchLeaves]);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const approveLeave = async (id, employeeName) => {
    setProcessingId(id);
    try {
      await orgApi.approveLeave(id);
      showToast(`✅ Leave request for ${employeeName} approved!`, 'success');
      // Immediately update local state by removing the approved leave
      setRequests(prev => prev.filter(r => r.leave_id !== id));
    } catch (err) {
      showToast(err.message || "Failed to approve leave", "error");
    } finally {
      setProcessingId(null);
    }
  };

  const rejectLeave = async () => {
    if (!showRejectModal) return;
    setRejecting(true);
    const leaveId = showRejectModal.leave_id;
    const employeeName = showRejectModal.employee_name;
    setProcessingId(leaveId);
    try {
      await orgApi.rejectLeave(leaveId, rejectReason);
      showToast(`❌ Leave request for ${employeeName} rejected.`, 'error');
      // Immediately update local state by removing the rejected leave
      setRequests(prev => prev.filter(r => r.leave_id !== leaveId));
      setShowRejectModal(null);
      setRejectReason("");
    } catch (err) {
      showToast(err.message || "Failed to reject leave", "error");
    } finally {
      setRejecting(false);
      setProcessingId(null);
    }
  };

  // Filter based on selected filter
  const filteredRequests = requests.filter(r => {
    if (filter === "all") return true;
    if (filter === "pending") return r.status === "pending";
    if (filter === "approved") return r.status === "approved";
    if (filter === "rejected") return r.status === "rejected";
    return true;
  });
  
  // Calculate stats
  const stats = {
    pending: requests.filter(r => r.status === "pending").length,
  };

  const getStatusBadgeType = (status) => {
    if (status === 'approved') return 'approved';
    if (status === 'pending') return 'pending';
    if (status === 'rejected') return 'rejected';
    return 'pending';
  };

  const getStatusText = (status) => {
    if (status === 'approved') return 'Approved';
    if (status === 'pending') return 'Pending';
    if (status === 'rejected') return 'Rejected';
    return status;
  };

  if (loading) {
    return (
      <DashboardLayout title="Leave Requests" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '400px' }}>
          Loading leave requests...
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Leave Requests" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <style>{`
        .toast-notification {
          position: fixed;
          bottom: 24px;
          right: 24px;
          z-index: 1000;
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px 20px;
          border-radius: 12px;
          color: white;
          font-size: 0.9rem;
          font-weight: 500;
          animation: slideInRight 0.3s ease;
          box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        }
        
        .toast-notification.success {
          background: linear-gradient(135deg, #22c55e, #16a34a);
        }
        
        .toast-notification.error {
          background: linear-gradient(135deg, #ef4444, #dc2626);
        }
        
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
        
        .empty-state {
          text-align: center;
          padding: 4rem 2rem;
        }
        
        .empty-icon {
          width: 80px;
          height: 80px;
          background: rgba(0,212,170,0.1);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 1rem;
          color: var(--teal);
        }
      `}</style>

      {/* Toast Notification */}
      {toast && (
        <div className={`toast-notification ${toast.type}`}>
          {toast.type === 'success' ? <CheckCircle size={20} /> : <AlertCircle size={20} />}
          {toast.message}
        </div>
      )}

      <ConfirmationModal
        isOpen={!!showRejectModal}
        onClose={() => { setShowRejectModal(null); setRejectReason(""); }}
        onConfirm={rejectLeave}
        title="Reject Leave Request"
        message={`Are you sure you want to reject ${showRejectModal?.employee_name}'s leave request?${rejectReason ? `\nReason: "${rejectReason}"` : ''}`}
        confirmText="Reject"
        cancelText="Cancel"
        type="danger"
        confirmVariant="danger"
        loading={rejecting}
      />

      {/* Filter Bar */}
      <div className="table-wrap">
        <div className="table-header">
          <span className="table-title">
            Leave Requests
            {stats.pending > 0 && (
              <span style={{ 
                marginLeft: '12px', 
                fontSize: '0.7rem', 
                color: 'var(--amber)',
                background: 'rgba(245,158,11,0.1)',
                padding: '2px 8px',
                borderRadius: '20px'
              }}>
                {stats.pending} pending
              </span>
            )}
          </span>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <select 
              className="form-select" 
              value={filter} 
              onChange={(e) => setFilter(e.target.value)} 
              style={{ width: '140px' }}
            >
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="all">All Requests</option>
            </select>
            <button 
              className="btn btn-ghost" 
              onClick={fetchLeaves} 
              style={{ padding: '6px 12px' }}
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </div>

        {/* Leave Requests Table */}
        {filteredRequests.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Bell size={40} />
            </div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              No Leave Requests
            </h3>
            <p style={{ color: 'var(--text3)', maxWidth: '300px', margin: '0 auto' }}>
              {filter === 'pending' 
                ? "All leave requests have been processed. No pending approvals needed."
                : `No leave requests found with status: ${filter}`}
            </p>
          </div>
        ) : (
          <table style={{ width: '100%' }}>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Type</th>
                <th>Duration</th>
                <th>Reason</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRequests.map((r) => (
                <tr key={r.leave_id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{r.employee_name}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>{r.employee_code}</div>
                  </td>
                  <td style={{ textTransform: 'capitalize' }}>{r.leave_type}</td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>
                    {new Date(r.start_date).toLocaleDateString()} → {new Date(r.end_date).toLocaleDateString()}
                  </td>
                  <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {r.reason || '-'}
                  </td>
                  <td>
                    <Badge type={getStatusBadgeType(r.status)}>
                      {getStatusText(r.status)}
                    </Badge>
                  </td>
                  <td>
                    {r.status === "pending" && (
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button 
                          className="btn btn-teal" 
                          onClick={() => approveLeave(r.leave_id, r.employee_name)}
                          disabled={processingId === r.leave_id}
                          style={{ 
                            padding: '6px 12px', 
                            fontSize: '0.75rem',
                            opacity: processingId === r.leave_id ? 0.6 : 1
                          }}
                        >
                          <CheckCircle size={14} style={{ marginRight: '4px' }} />
                          {processingId === r.leave_id ? 'Processing...' : 'Approve'}
                        </button>
                        <button 
                          className="btn btn-red" 
                          onClick={() => setShowRejectModal(r)}
                          disabled={processingId === r.leave_id}
                          style={{ 
                            padding: '6px 12px', 
                            fontSize: '0.75rem',
                            opacity: processingId === r.leave_id ? 0.6 : 1
                          }}
                        >
                          <XCircle size={14} style={{ marginRight: '4px' }} />
                          Reject
                        </button>
                      </div>
                    )}
                    {r.status !== "pending" && (
                      <span style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>
                        {r.status === "approved" ? "✓ Approved" : "✗ Rejected"}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </DashboardLayout>
  );
};

export default Leaves;