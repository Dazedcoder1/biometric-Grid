// src/pages/employee/Leaves.jsx
import React, { useState, useEffect } from 'react';
import { ArrowLeft } from 'lucide-react';
import DashboardLayout from '../../layouts/DashboardLayout';
import Badge from '../../components/Badge';
import { employeeApi } from '../../services/api';

const Leaves = () => {
  const [view, setView] = useState('list');
  const [leaves, setLeaves] = useState([]);
  const [balance, setBalance] = useState({
    sick: { total: 12, taken: 0, remaining: 12 },
    casual: { total: 12, taken: 0, remaining: 12 },
    earned: { total: 15, taken: 0, remaining: 15 },
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  
  // New leave form state
  const [newLeave, setNewLeave] = useState({
    leave_type: 'casual',
    start_date: new Date().toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0],
    reason: '',
  });

  useEffect(() => {
    fetchLeavesData();
  }, []);

  const fetchLeavesData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [leavesData, balanceData] = await Promise.all([
        employeeApi.getLeaves(),
        employeeApi.getLeaveBalance(),
      ]);
      
      console.log('Leaves data:', leavesData);
      console.log('Balance data:', balanceData);
      
      setLeaves(leavesData || []);
      setBalance(balanceData || {
        sick: { total: 12, taken: 0, remaining: 12 },
        casual: { total: 12, taken: 0, remaining: 12 },
        earned: { total: 15, taken: 0, remaining: 15 },
      });
    } catch (err) {
      console.error('Failed to fetch leaves:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyLeave = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccessMessage('');
    
    // Validate dates
    if (newLeave.start_date > newLeave.end_date) {
      setError('Start date cannot be after end date');
      setSubmitting(false);
      return;
    }
    
    try {
      // Send request in the format backend expects
      const requestData = {
        leave_type: newLeave.leave_type,
        start_date: newLeave.start_date,
        end_date: newLeave.end_date,
        reason: newLeave.reason || '',
      };
      
      console.log('Sending leave request:', requestData);
      
      const response = await employeeApi.applyLeave(requestData);
      console.log('Leave response:', response);
      
      setSuccessMessage('Leave applied successfully!');
      
      // Refresh the leaves list
      await fetchLeavesData();
      
      // Reset form and go back to list view after 1 second
      setTimeout(() => {
        setView('list');
        setSuccessMessage('');
        // Reset form
        setNewLeave({
          leave_type: 'casual',
          start_date: new Date().toISOString().split('T')[0],
          end_date: new Date().toISOString().split('T')[0],
          reason: '',
        });
      }, 1500);
      
    } catch (err) {
      console.error('Failed to apply leave:', err);
      setError(err.message || 'Failed to apply leave. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelLeave = async (leaveId) => {
    if (!window.confirm('Are you sure you want to cancel this leave request?')) return;
    
    try {
      await employeeApi.cancelLeave(leaveId);
      await fetchLeavesData(); // Refresh the list
      setSuccessMessage('Leave cancelled successfully!');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      console.error('Failed to cancel leave:', err);
      setError(err.message);
      setTimeout(() => setError(null), 3000);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setNewLeave(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
  };

  const getLeaveStatus = (status) => {
    if (status === 'approved' || status === 'approved_by_dept') return 'approved';
    if (status === 'pending') return 'pending';
    if (status === 'rejected') return 'rejected';
    if (status === 'cancelled') return 'rejected';
    return 'pending';
  };

  const getLeaveStatusText = (status) => {
    if (status === 'approved' || status === 'approved_by_dept') return 'Approved';
    if (status === 'pending') return 'Pending';
    if (status === 'rejected') return 'Rejected';
    if (status === 'cancelled') return 'Cancelled';
    return status;
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Leave List" 
        role="user" 
        label="Employee" 
        abbr="EM" 
        color="#f59e0b" 
        bgColor="rgba(245,158,11,0.15)"
      >
        <div className="card-box" style={{ textAlign: 'center', padding: '4rem' }}>
          <p>Loading leave data...</p>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Leave List" 
      role="user" 
      label="Employee" 
      abbr="EM" 
      color="#f59e0b" 
      bgColor="rgba(245,158,11,0.15)"
    >
      {/* Success Message */}
      {successMessage && (
        <div style={{ 
          background: 'rgba(34,197,94,0.1)', 
          border: '1px solid rgba(34,197,94,0.3)',
          borderRadius: '8px',
          padding: '0.75rem',
          marginBottom: '1rem',
          color: '#4ade80',
          fontSize: '0.85rem',
          textAlign: 'center'
        }}>
          {successMessage}
        </div>
      )}

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

      {/* Leave Balance Cards */}
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-card purple">
          <div className="stat-label">Sick Leave</div>
          <div className="stat-value" style={{ fontSize: '1.2rem' }}>
            {balance.sick?.remaining || 0} / {balance.sick?.total || 12}
          </div>
          <div className="stat-sub">Taken: {balance.sick?.taken || 0}</div>
        </div>
        <div className="stat-card amber">
          <div className="stat-label">Casual Leave</div>
          <div className="stat-value" style={{ fontSize: '1.2rem' }}>
            {balance.casual?.remaining || 0} / {balance.casual?.total || 12}
          </div>
          <div className="stat-sub">Taken: {balance.casual?.taken || 0}</div>
        </div>
        <div className="stat-card teal">
          <div className="stat-label">Earned Leave</div>
          <div className="stat-value" style={{ fontSize: '1.2rem' }}>
            {balance.earned?.remaining || 0} / {balance.earned?.total || 15}
          </div>
          <div className="stat-sub">Taken: {balance.earned?.taken || 0}</div>
        </div>
      </div>

      {view === 'list' && (
        <div id="leaves-list-view">
          <div className="table-wrap">
            <div className="table-header">
              <span className="table-title">My Leaves</span>
              <button className="btn btn-teal" onClick={() => setView('apply')}>+ Apply Leave</button>
            </div>
            <table style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>From</th>
                  <th>To</th>
                  <th>Reason</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {leaves.length === 0 ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '2rem' }}>
                      No leave requests found
                    </td>
                  </tr>
                ) : (
                  leaves.map((leave) => (
                    <tr key={leave.leave_id || leave.id}>
                      <td style={{ textTransform: 'capitalize' }}>{leave.leave_type || leave.type}</td>
                      <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>
                        {formatDate(leave.start_date)}
                      </td>
                      <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>
                        {formatDate(leave.end_date)}
                      </td>
                      <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {leave.reason || '-'}
                      </td>
                      <td>
                        <Badge type={getLeaveStatus(leave.status)}>
                          {getLeaveStatusText(leave.status)}
                        </Badge>
                      </td>
                      <td>
                        {(leave.status === 'pending' || leave.status === 'Pending') && (
                          <button 
                            className="btn btn-red" 
                            style={{ padding: '3px 10px', fontSize: '0.75rem' }}
                            onClick={() => handleCancelLeave(leave.leave_id || leave.id)}
                          >
                            Cancel
                          </button>
                        )}
                        {(leave.status === 'cancelled' || leave.status === 'rejected') && (
                          <span style={{ fontSize: '0.7rem', color: 'var(--text3)' }}>-</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {view === 'apply' && (
        <div id="leaves-apply-view">
          <div style={{ marginBottom: '1.5rem' }}>
            <button 
              className="btn btn-ghost" 
              onClick={() => setView('list')} 
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <ArrowLeft size={18} />
              Back to My Leaves
            </button>
          </div>
          
          <div className="card-box" style={{ maxWidth: '480px' }}>
            <h4>Apply for Leave</h4>
            <form onSubmit={handleApplyLeave}>
              <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
                <div className="form-group">
                  <label className="form-label">Leave Type *</label>
                  <select 
                    className="form-select" 
                    name="leave_type"
                    value={newLeave.leave_type}
                    onChange={handleInputChange}
                    required
                  >
                    <option value="sick">Sick Leave</option>
                    <option value="casual">Casual Leave</option>
                    <option value="earned">Earned Leave</option>
                  </select>
                </div>
                
                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">Start Date *</label>
                    <input 
                      className="form-input" 
                      type="date" 
                      name="start_date"
                      value={newLeave.start_date}
                      onChange={handleInputChange}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">End Date *</label>
                    <input 
                      className="form-input" 
                      type="date" 
                      name="end_date"
                      value={newLeave.end_date}
                      onChange={handleInputChange}
                      required
                    />
                  </div>
                </div>
                
                <div className="form-group">
                  <label className="form-label">Reason</label>
                  <textarea 
                    className="form-input" 
                    name="reason"
                    rows="3" 
                    placeholder="Reason for leave (optional)..."
                    value={newLeave.reason}
                    onChange={handleInputChange}
                  />
                </div>
                
                <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
                  <button 
                    type="submit" 
                    className="btn btn-teal" 
                    disabled={submitting}
                  >
                    {submitting ? 'Submitting...' : 'Submit Request'}
                  </button>
                  <button 
                    type="button" 
                    className="btn btn-ghost" 
                    onClick={() => setView('list')}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default Leaves;