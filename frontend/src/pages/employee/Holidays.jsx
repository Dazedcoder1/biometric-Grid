// src/pages/employee/Holidays.jsx
import React, { useState, useEffect } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { employeeApi } from '../../services/api';

const Holidays = () => {
  const [holidays, setHolidays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchHolidays();
  }, []);

  const fetchHolidays = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await employeeApi.getHolidays();
      console.log('Holidays API response:', data);
      
      // Handle the response - data is directly an array
      let holidaysArray = [];
      if (Array.isArray(data)) {
        holidaysArray = data;
      } else if (data && typeof data === 'object') {
        // If response is wrapped in an object
        if (data.data && Array.isArray(data.data)) {
          holidaysArray = data.data;
        } else if (data.holidays && Array.isArray(data.holidays)) {
          holidaysArray = data.holidays;
        } else {
          holidaysArray = [data];
        }
      }
      
      setHolidays(holidaysArray);
    } catch (err) {
      console.error('Failed to fetch holidays:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Invalid Date';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', { 
        day: 'numeric', 
        month: 'short', 
        year: 'numeric' 
      });
    } catch (e) {
      return dateStr;
    }
  };

  const getDayOfWeek = (dateStr) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', { weekday: 'long' });
    } catch (e) {
      return '';
    }
  };

  // Helper to safely get holiday name from the response
  const getHolidayName = (holiday) => {
    return holiday.name || holiday.holiday_name || holiday.title || 'Unnamed Holiday';
  };

  // Helper to safely get holiday date
  const getHolidayDate = (holiday) => {
    return holiday.holiday_date || holiday.date || null;
  };

  if (loading) {
    return (
      <DashboardLayout 
        title="Holidays" 
        role="user" 
        label="Employee" 
        abbr="EM" 
        color="#f59e0b" 
        bgColor="rgba(245,158,11,0.15)"
      >
        <div className="card-box" style={{ textAlign: 'center', padding: '4rem' }}>
          <p>Loading holidays...</p>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout 
        title="Holidays" 
        role="user" 
        label="Employee" 
        abbr="EM" 
        color="#f59e0b" 
        bgColor="rgba(245,158,11,0.15)"
      >
        <div className="card-box" style={{ textAlign: 'center', padding: '4rem' }}>
          <p style={{ color: 'var(--red)' }}>Error: {error}</p>
          <button className="btn btn-teal" onClick={fetchHolidays} style={{ marginTop: '1rem' }}>
            Retry
          </button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout 
      title="Holidays" 
      role="user" 
      label="Employee" 
      abbr="EM" 
      color="#f59e0b" 
      bgColor="rgba(245,158,11,0.15)"
    >
      <div className="table-wrap">
        <div className="table-header">
          <span className="table-title">Company Holidays {new Date().getFullYear()}</span>
        </div>
        <table style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Holiday</th>
              <th>Date</th>
              <th>Day</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {holidays.length === 0 ? (
              <tr>
                <td colSpan="4" style={{ textAlign: 'center', padding: '2rem' }}>
                  No holidays found for this year
                </td>
              </tr>
            ) : (
              holidays.map((holiday) => {
                const holidayName = getHolidayName(holiday);
                const holidayDate = getHolidayDate(holiday);
                
                return (
                  <tr key={holiday.holiday_id || holiday.id || Math.random()}>
                    <td style={{ fontWeight: 500 }}>{holidayName}</td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>
                      {holidayDate ? formatDate(holidayDate) : 'Date not set'}
                    </td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>
                      {holidayDate ? getDayOfWeek(holidayDate) : '-'}
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text2)' }}>
                      {holiday.description || '-'}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </DashboardLayout>
  );
};

export default Holidays;