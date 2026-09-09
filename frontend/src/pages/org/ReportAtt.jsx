import React, { useState } from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import { orgApi } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { Calendar, RefreshCw, AlertCircle, FileText, Download } from 'lucide-react';
import html2pdf from 'html2pdf.js';

const ReportAtt = () => {
  const { logout } = useAuth();
  const today = new Date().toISOString().split("T")[0];
  const [fromDate, setFromDate] = useState(today);
  const [toDate, setToDate] = useState(today);
  const [summary, setSummary] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [generated, setGenerated] = useState(false);
  const [departmentName, setDepartmentName] = useState("");

  const isCheckInLate = (checkInTime, officeStartHour = 9, officeStartMinute = 15) => {
    if (!checkInTime) return false;
    const checkIn = new Date(checkInTime);
    const hours = checkIn.getHours();
    const minutes = checkIn.getMinutes();
    
    // Office starts at 9:00 AM, late after 9:15 AM (configurable)
    if (hours > officeStartHour) return true;
    if (hours === officeStartHour && minutes > officeStartMinute) return true;
    return false;
  };

  const generateReport = async () => {
    setLoading(true);
    setError("");
    setGenerated(false);
    setSummary([]);
    
    try {
      // 1. Fetch employees and department info
      const [employees, deptInfo] = await Promise.all([
        orgApi.getEmployees(),
        orgApi.getDashboard()
      ]);
      
      console.log("Employees fetched:", employees);
      console.log("Department info:", deptInfo);
      
      if (!employees || !Array.isArray(employees)) {
        throw new Error("No employees data received");
      }
      
      setDepartmentName(deptInfo?.department || deptInfo?.department_name || "Department");

      // 2. Generate date range
      const dates = [];
      let current = new Date(fromDate);
      const last = new Date(toDate);
      while (current <= last) {
        dates.push(new Date(current).toISOString().split("T")[0]);
        current.setDate(current.getDate() + 1);
      }
      
      console.log(`Processing ${dates.length} days from ${fromDate} to ${toDate}`);

      // 3. Initialize Report Map
      const reportMap = {};
      employees.forEach(emp => { 
        reportMap[emp.id] = { 
          id: emp.id,
          name: emp.name, 
          present: 0, 
          late: 0, 
          absent: 0, 
          employee_code: emp.employee_code,
          department: emp.department_name || deptInfo?.department || 'N/A'
        }; 
      });

      // 4. Process each date
      for (const d of dates) {
        console.log(`Processing date: ${d}`);
        
        try {
          const attendanceData = await orgApi.getAttendanceByDate(d);
          console.log(`Attendance data for ${d}:`, attendanceData);
          
          // Handle the new API response structure { summary: {...}, employees: [...] }
          let records = [];
          if (attendanceData && attendanceData.employees && Array.isArray(attendanceData.employees)) {
            records = attendanceData.employees;
          } else if (Array.isArray(attendanceData)) {
            records = attendanceData;
          } else {
            console.warn(`Unexpected data format for date ${d}:`, attendanceData);
            records = [];
          }
          
          // Create lookup maps for both ID and Code
          const idToRecord = {};
          const codeToRecord = {};
          
          records.forEach(r => { 
            if (r.id) idToRecord[r.id] = r;
            if (r.employee_code) codeToRecord[r.employee_code] = r;
          });
          
          // Process each employee for this date
          employees.forEach(emp => {
            // Find record by ID or Code
            const record = idToRecord[emp.id] || codeToRecord[emp.employee_code];
            
            if (record && record.status === "present") {
              // Check if employee was late
              if (record.check_in && isCheckInLate(record.check_in)) {
                reportMap[emp.id].late++;
              } else {
                reportMap[emp.id].present++;
              }
            } else {
              // Treat as absent
              reportMap[emp.id].absent++;
            }
          });
          
        } catch (dateErr) {
          console.error(`Error processing date ${d}:`, dateErr);
          // Continue with other dates
        }
      }

      // 5. Calculate final results
      const result = Object.values(reportMap).map(r => {
        const totalDays = r.present + r.late + r.absent;
        const attended = r.present + r.late;
        const percent = totalDays > 0 ? ((attended / totalDays) * 100).toFixed(1) : "0.0";
        return { 
          ...r, 
          percent: percent + "%",
          attendance_rate: parseFloat(percent)
        };
      });
      
      // Sort by name
      result.sort((a, b) => a.name.localeCompare(b.name));
      
      console.log("Final report:", result);
      setSummary(result);
      setGenerated(true);
      
    } catch (err) {
      console.error("Report generation error:", err);
      if (err?.response?.status === 401) logout();
      setError(err.message || "Failed to fetch records. Check console for details.");
    } finally {
      setLoading(false);
    }
  };

  const downloadPDF = () => {
    if (summary.length === 0) return;
    
    const pdfContent = document.createElement('div');
    Object.assign(pdfContent.style, {
      padding: '40px',
      fontFamily: 'Helvetica, Arial, sans-serif',
      backgroundColor: 'white',
      color: '#1a1a1a'
    });
    
    const stats = summary.reduce((acc, s) => {
      acc.p += s.present;
      acc.l += s.late;
      acc.a += s.absent;
      return acc;
    }, { p: 0, l: 0, a: 0 });

    const totalDays = stats.p + stats.l + stats.a;
    const overallRate = totalDays > 0 ? (((stats.p + stats.l) / totalDays) * 100).toFixed(1) : 0;
    
    pdfContent.innerHTML = `
      <div style="text-align: center; margin-bottom: 30px; border-bottom: 3px solid #00d4aa; padding-bottom: 20px;">
        <h1 style="color: #00d4aa; margin: 0; font-size: 28px;">Attendance Summary Report</h1>
        <p style="color: #666; margin: 5px 0;">${departmentName}</p>
        <p style="color: #888; font-size: 12px;">Period: ${fromDate} to ${toDate}</p>
        <p style="color: #888; font-size: 12px;">Generated: ${new Date().toLocaleString()}</p>
      </div>
      
      <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 40px;">
        <div style="background: #f0fdf4; padding: 20px; border-radius: 12px; text-align: center; border: 1px solid #dcfce7;">
          <div style="color: #166534; font-size: 24px; font-weight: 800;">${stats.p}</div>
          <div style="color: #166534; font-size: 11px; text-transform: uppercase;">On Time</div>
        </div>
        <div style="background: #fffbeb; padding: 20px; border-radius: 12px; text-align: center; border: 1px solid #fef3c7;">
          <div style="color: #92400e; font-size: 24px; font-weight: 800;">${stats.l}</div>
          <div style="color: #92400e; font-size: 11px; text-transform: uppercase;">Late</div>
        </div>
        <div style="background: #fef2f2; padding: 20px; border-radius: 12px; text-align: center; border: 1px solid #fee2e2;">
          <div style="color: #991b1b; font-size: 24px; font-weight: 800;">${stats.a}</div>
          <div style="color: #991b1b; font-size: 11px; text-transform: uppercase;">Absent</div>
        </div>
        <div style="background: #eff6ff; padding: 20px; border-radius: 12px; text-align: center; border: 1px solid #dbeafe;">
          <div style="color: #1e40af; font-size: 24px; font-weight: 800;">${overallRate}%</div>
          <div style="color: #1e40af; font-size: 11px; text-transform: uppercase;">Net Efficiency</div>
        </div>
      </div>
      
      <table style="width: 100%; border-collapse: collapse;">
        <thead>
          <tr style="background: #f8fafc; border-bottom: 2px solid #e2e8f0;">
            <th style="padding: 12px; text-align: left; font-size: 12px;">Employee</th>
            <th style="padding: 12px; text-align: left; font-size: 12px;">Code</th>
            <th style="padding: 12px; text-align: left; font-size: 12px;">Department</th>
            <th style="padding: 12px; text-align: center; font-size: 12px;">Present</th>
            <th style="padding: 12px; text-align: center; font-size: 12px;">Late</th>
            <th style="padding: 12px; text-align: center; font-size: 12px;">Absent</th>
            <th style="padding: 12px; text-align: center; font-size: 12px;">Attendance %</th>
           </tr>
        </thead>
        <tbody>
          ${summary.map(s => `
            <tr style="border-bottom: 1px solid #f1f5f9;">
              <td style="padding: 12px; font-size: 13px;">${s.name}</td>
              <td style="padding: 12px; font-size: 13px; color: #64748b;">${s.employee_code || '-'}</td>
              <td style="padding: 12px; font-size: 13px; color: #64748b;">${s.department}</td>
              <td style="padding: 12px; text-align: center; color: #22c55e; font-weight: 600;">${s.present}</td>
              <td style="padding: 12px; text-align: center; color: #f59e0b; font-weight: 600;">${s.late}</td>
              <td style="padding: 12px; text-align: center; color: #ef4444; font-weight: 600;">${s.absent}</td>
              <td style="padding: 12px; text-align: center; font-weight: bold;">${s.percent}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      
      <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 10px; color: #94a3b8;">
        <p>This is a system-generated report from ScholarFlow Attendance System</p>
      </div>
    `;
    
    document.body.appendChild(pdfContent);
    const opt = {
      margin: 10,
      filename: `Attendance_Report_${fromDate}_to_${toDate}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
    };
    
    html2pdf().set(opt).from(pdfContent).save().then(() => {
      document.body.removeChild(pdfContent);
    }).catch(err => {
      console.error("PDF generation error:", err);
      document.body.removeChild(pdfContent);
      setError("Failed to generate PDF");
    });
  };

  return (
    <DashboardLayout title="Attendance Report" role="orgadmin" label="Department Admin" abbr="DA" color="#00d4aa" bgColor="rgba(0,212,170,0.15)">
      <style>{`
        .card-box { background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem; }
        .form-group { display: flex; flex-direction: column; gap: 0.5rem; }
        .form-label { font-size: 0.75rem; color: var(--text3); display: flex; align-items: center; gap: 6px; }
        .form-input { background: var(--bg3); border: 1px solid var(--border); border-radius: 8px; padding: 0.7rem; color: var(--text); }
        .table-wrap { background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
        .table-header { padding: 1.25rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }
        table { width: 100%; border-collapse: collapse; }
        th { padding: 1rem; background: var(--bg3); font-size: 0.7rem; text-transform: uppercase; color: var(--text3); text-align: left; }
        td { padding: 1rem; border-bottom: 1px solid var(--border); font-size: 0.85rem; color: var(--text2); }
        .btn-teal { background: var(--teal); color: white; border: none; padding: 0.7rem 1.2rem; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 8px; font-weight: 500; }
        .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); padding: 0.7rem 1.2rem; border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 8px; }
        .btn-teal:disabled, .btn-ghost:disabled { opacity: 0.5; cursor: not-allowed; }
        .animate-spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>

      <div className="card-box">
        <h4>Analytics & Reporting</h4>
        <p style={{ color: 'var(--text3)', fontSize: '0.8rem', marginBottom: '1.5rem' }}>Generate PDF summaries for department-wide attendance</p>
        
        {error && (
          <div style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171', padding: '12px', borderRadius: '8px', marginBottom: '1rem', display: 'flex', gap: '8px' }}>
            <AlertCircle size={16} /> {error}
          </div>
        )}
        
        <div className="form-grid">
          <div className="form-group">
            <label className="form-label"><Calendar size={14} /> Start Date</label>
            <input className="form-input" type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label"><Calendar size={14} /> End Date</label>
            <input className="form-input" type="date" value={toDate} onChange={e => setToDate(e.target.value)} />
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <button className="btn-teal" onClick={generateReport} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> 
            {loading ? 'Processing...' : 'Analyze Records'}
          </button>
          <button className="btn-ghost" onClick={downloadPDF} disabled={!generated || summary.length === 0}>
            <Download size={16} /> Export PDF
          </button>
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <FileText size={18} color="var(--teal)" />
            <span style={{ fontWeight: 600 }}>Performance Data</span>
          </div>
          {generated && (
            <span style={{ fontSize: '0.75rem', opacity: 0.6 }}>
              {summary.length} employees · {fromDate} to {toDate}
            </span>
          )}
        </div>
        
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Employee</th>
                <th>Code</th>
                <th>Department</th>
                <th style={{ textAlign: 'center' }}>Present</th>
                <th style={{ textAlign: 'center' }}>Late</th>
                <th style={{ textAlign: 'center' }}>Absent</th>
                <th style={{ textAlign: 'center' }}>Attendance %</th>
              </tr>
            </thead>
            <tbody>
              {summary.length > 0 ? summary.map((s, i) => (
                <tr key={i}>
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--text)' }}>{s.name}</div>
                  </td>
                  <td style={{ fontSize: '0.75rem', color: 'var(--text3)' }}>{s.employee_code || '-'}</td>
                  <td style={{ fontSize: '0.75rem', color: 'var(--text3)' }}>{s.department}</td>
                  <td style={{ textAlign: 'center', color: '#22c55e', fontWeight: 600 }}>{s.present}</td>
                  <td style={{ textAlign: 'center', color: '#f59e0b', fontWeight: 600 }}>{s.late}</td>
                  <td style={{ textAlign: 'center', color: '#ef4444', fontWeight: 600 }}>{s.absent}</td>
                  <td style={{ textAlign: 'center', fontFamily: 'monospace', fontWeight: 600 }}>{s.percent}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text3)' }}>
                    {loading ? "Aggregating data points..." : "No report generated yet. Click 'Analyze Records' to start."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default ReportAtt;