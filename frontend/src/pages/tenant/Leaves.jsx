// src/pages/tenant/Leaves.jsx
import React, { useState, useEffect } from 'react';
import { Search, RefreshCw, AlertCircle, CheckCircle, XCircle, Clock, Filter } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { tenantApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const Leaves = () => {
  const { logout } = useAuth();
  const [leaves, setLeaves] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [selectedDept, setSelectedDept] = useState('');
  const [stats, setStats] = useState({ total: 0, pending: 0, approved: 0, rejected: 0 });
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(null);

  useEffect(() => {
    fetchLeaves();
    fetchDepartments();
    fetchStats();
  }, [selectedStatus, selectedDept]);

  const fetchLeaves = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await tenantApi.getLeaveRequests(selectedStatus || undefined, selectedDept || undefined);
      setLeaves(data || []);
    } catch (err) {
      console.error('Fetch leaves error:', err);
      if (err?.response?.status === 401) logout();
      setError('Failed to load leave requests');
    } finally {
      setLoading(false);
    }
  };

  const fetchDepartments = async () => {
    try {
      const data = await tenantApi.getDepartments();
      setDepartments(data || []);
    } catch (err) {
      console.error('Fetch departments error:', err);
    }
  };

  const fetchStats = async () => {
    try {
      const data = await tenantApi.getLeaveStats();
      setStats(data || { total: 0, pending: 0, approved: 0, rejected: 0 });
    } catch (err) {
      console.error('Fetch stats error:', err);
    }
  };

  const handleApprove = async (leaveId) => {
    try {
      await tenantApi.approveLeave(leaveId);
      await fetchLeaves();
      await fetchStats();
    } catch (err) {
      setError(err.message || 'Failed to approve leave');
      setTimeout(() => setError(''), 3000);
    }
  };

  const handleReject = async (leaveId) => {
    try {
      await tenantApi.rejectLeave(leaveId, rejectReason);
      setShowRejectModal(null);
      setRejectReason('');
      await fetchLeaves();
      await fetchStats();
    } catch (err) {
      setError(err.message || 'Failed to reject leave');
      setTimeout(() => setError(''), 3000);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '--';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
  };

  const getStatusBadge = (status) => {
    if (status === 'approved' || status === 'approved_by_dept') return 'approved';
    if (status === 'pending') return 'pending';
    if (status === 'rejected') return 'rejected';
    return 'pending';
  };

  const getStatusText = (status) => {
    if (status === 'approved_by_dept') return 'Dept Approved';
    if (status === 'approved') return 'Approved';
    return status;
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Leaves" 
        role="superadmin" 
        label="Tenant Admin" 
        abbr="TA" 
        color="#a855f7" 
        bgColor="rgba(168,85,247,0.15)"
      >
        <div className="skeleton-loader">{/* Loading skeleton */}</div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Leave Management" 
      role="superadmin" 
      label="Tenant Admin" 
      abbr="TA" 
      color="#a855f7" 
      bgColor="rgba(168,85,247,0.15)"
    >
      <style>{`
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0,0,0,0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 2000;
          backdrop-filter: blur(4px);
        }
        .modal-content {
          background: var(--bg2);
          border: 1px solid var(--border);
          border-radius: 16px;
          max-width: 400px;
          width: 90%;
          padding: 1.5rem;
        }
      `}</style>

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card purple">
          <div className="stat-label">Total Requests</div>
          <div className="stat-value">{stats.total || 0}</div>
          <div className="stat-sub">All time</div>
        </div>
        <div className="stat-card amber">
          <div className="stat-label">Pending</div>
          <div className="stat-value">{stats.pending || 0}</div>
          <div className="stat-sub">Awaiting approval</div>
        </div>
        <div className="stat-card green">
          <div className="stat-label">Approved</div>
          <div className="stat-value">{stats.approved || 0}</div>
          <div className="stat-sub">+ {stats.dept_approved || 0} dept approved</div>
        </div>
        <div className="stat-card red">
          <div className="stat-label">Rejected</div>
          <div className="stat-value">{stats.rejected || 0}</div>
          <div className="stat-sub">Declined requests</div>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <select 
            className="form-select" 
            style={{ width: '140px' }}
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
          >
            <option value="">All Status</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="approved_by_dept">Dept Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          <select 
            className="form-select" 
            style={{ width: '160px' }}
            value={selectedDept}
            onChange={(e) => setSelectedDept(e.target.value)}
          >
            <option value="">All Departments</option>
            {departments.filter(d => d.is_active).map(dept => (
              <option key={dept.department_id} value={dept.department_id}>
                {dept.department_name}
              </option>
            ))}
          </select>
          <button className="btn btn-ghost" onClick={fetchLeaves}>
            <RefreshCw size={16} style={{ marginRight: '4px' }} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '8px', padding: '12px', marginBottom: '1rem', color: '#f87171' }}>
          <AlertCircle size={16} style={{ display: 'inline', marginRight: '8px' }} /> {error}
        </div>
      )}

      {/* Leaves Table */}
      <div className="table-wrap">
        <div className="table-header">
          <span className="table-title">Leave Requests</span>
        </div>
        <table style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Employee</th>
              <th>Department</th>
              <th>Type</th>
              <th>From</th>
              <th>To</th>
              <th>Reason</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {leaves.length === 0 ? (
              <tr>
                <td colSpan="8" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text3)' }}>
                  No leave requests found
                </td>
              </tr>
            ) : (
              leaves.map((leave) => (
                <tr key={leave.leave_id}>
                  <td style={{ fontWeight: 500 }}>{leave.employee_name}</td>
                  <td>{leave.department_name || '—'}</td>
                  <td style={{ textTransform: 'capitalize' }}>{leave.leave_type}</td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>{formatDate(leave.start_date)}</td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>{formatDate(leave.end_date)}</td>
                  <td style={{ maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{leave.reason || '—'}</td>
                  <td><Badge type={getStatusBadge(leave.status)}>{getStatusText(leave.status)}</Badge></td>
                  <td>
                    {(leave.status === 'pending' || leave.status === 'approved_by_dept') && (
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button 
                          className="btn btn-teal" 
                          onClick={() => handleApprove(leave.leave_id)}
                          style={{ padding: '4px 10px', fontSize: '0.7rem' }}
                          title="Approve"
                        >
                          <CheckCircle size={14} />
                        </button>
                        <button 
                          className="btn btn-red" 
                          onClick={() => setShowRejectModal(leave)}
                          style={{ padding: '4px 10px', fontSize: '0.7rem' }}
                          title="Reject"
                        >
                          <XCircle size={14} />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="modal-overlay" onClick={() => setShowRejectModal(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h4 style={{ marginBottom: '0.5rem' }}>Reject Leave Request</h4>
            <p style={{ color: 'var(--text3)', marginBottom: '1rem' }}>
              Rejecting leave for <strong>{showRejectModal.employee_name}</strong>
            </p>
            <div className="form-group">
              <label className="form-label">Reason (Optional)</label>
              <textarea 
                className="form-input" 
                rows="3"
                placeholder="Enter reason for rejection..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem', justifyContent: 'flex-end' }}>
              <button className="btn btn-ghost" onClick={() => setShowRejectModal(null)}>Cancel</button>
              <button className="btn btn-red" onClick={() => handleReject(showRejectModal.leave_id)}>Confirm Reject</button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default Leaves;