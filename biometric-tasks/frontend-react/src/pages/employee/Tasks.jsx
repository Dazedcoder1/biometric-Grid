// src/pages/employee/Tasks.jsx
import React from 'react';
import DashboardLayout from '../../layouts/DashboardLayout';
import TaskBoard from '../../components/TaskBoard';
import { employeeTaskApi } from '../../services/api';

// Employees see only their own tasks and may change status only —
// readOnlyMeta routes status changes through the PATCH endpoint that
// enforces that on the server too.
const Tasks = () => (
  <DashboardLayout
    title="My Tasks"
    role="user"
    label="Employee"
    abbr="EM"
    color="#f59e0b"
    bgColor="rgba(245,158,11,0.15)"
  >
    <TaskBoard api={employeeTaskApi} readOnlyMeta />
  </DashboardLayout>
);

export default Tasks;
