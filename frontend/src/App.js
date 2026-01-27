import React, { useState } from "react";
import "@/App.css";

import Login from "@/views/Login";
import Layout from "@/components/Layout";
import UserWorkspace from "@/views/UserWorkspace";
import AdminDashboard from "@/views/AdminDashboard";
import PatientRecords from "@/views/PatientRecords";
import DoctorList from "@/views/DoctorList";
import LabList from "@/views/LabList";
import Settings from "@/views/Settings";

import { AuthService } from "@/services/api";
import { Role } from "@/types";

const App = () => {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeView, setActiveView] = useState("workspace");

  const [selectedLabId, setSelectedLabId] = useState(undefined);
  const [selectedLabName, setSelectedLabName] = useState(undefined);
  const [selectedDoctorId, setSelectedDoctorId] = useState(undefined);
  const [selectedDoctorName, setSelectedDoctorName] = useState(undefined);

  const resetSelection = () => {
    setSelectedLabId(undefined);
    setSelectedLabName(undefined);
    setSelectedDoctorId(undefined);
    setSelectedDoctorName(undefined);
  };

  const handleLogin = async (u, p) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await AuthService.login(u, p);
      
      // Check if MFA is required
      if (result.mfaRequired) {
        setIsLoading(false);
        return result; // Return the result so Login component can handle MFA
      }
      
      // Normal login success
      setUser(result);
      setActiveView(result.role === Role.ADMIN ? "admin_dashboard" : "workspace");
      return result;
    } catch (err) {
      setError("Invalid username or password");
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const handleMFASuccess = (authenticatedUser) => {
    setUser(authenticatedUser);
    setActiveView(authenticatedUser.role === Role.ADMIN ? "admin_dashboard" : "workspace");
  };

  const handleLogout = () => {
    AuthService.logout();
    setUser(null);
    setActiveView("workspace");
    resetSelection();
  };

  const handleSelectLab = (labId, labName) => {
    setSelectedLabId(labId);
    setSelectedLabName(labName);
    setActiveView("lab_doctors");
  };

  const handleSelectDoctor = (doctorId, doctorName) => {
    setSelectedDoctorId(doctorId);
    setSelectedDoctorName(doctorName);
    setActiveView("records");
  };

  const handleBackToLabs = () => {
    resetSelection();
    setActiveView("admin_labs");
  };

  const handleBackToDoctors = () => {
    setSelectedDoctorId(undefined);
    setSelectedDoctorName(undefined);
    setActiveView("lab_doctors");
  };

  const renderView = () => {
    if (!user) {
      return (
        <Login 
          onLogin={handleLogin} 
          onMFARequired={handleMFASuccess}
          isLoading={isLoading} 
          error={error} 
        />
      );
    }

    switch (activeView) {
      case "admin_dashboard":
        if (user.role !== Role.ADMIN) return <div className="p-8 text-red-600" data-testid="access-denied">Access Denied</div>;
        return <AdminDashboard />;

      case "admin_labs":
        if (user.role !== Role.ADMIN) return <div className="p-8 text-red-600" data-testid="access-denied">Access Denied</div>;
        return <LabList onSelectLab={handleSelectLab} />;

      case "lab_doctors":
        if (user.role === Role.ADMIN) {
          if (!selectedLabId) return <div className="p-8" data-testid="select-lab-first">Please select a Lab first.</div>;
          return <DoctorList labId={selectedLabId} labName={selectedLabName} onSelectDoctor={handleSelectDoctor} onBack={handleBackToLabs} />;
        }
        return <DoctorList onSelectDoctor={handleSelectDoctor} />;

      case "records":
        if (user.role === Role.ADMIN) {
          return <PatientRecords doctorId={selectedDoctorId} doctorName={selectedDoctorName} onBack={handleBackToDoctors} />;
        }
        return <PatientRecords doctorId={selectedDoctorId} doctorName={selectedDoctorName} onBack={selectedDoctorId ? handleBackToDoctors : undefined} />;

      case "settings":
        return <Settings user={user} />;

      case "workspace":
      default:
        if (user.role === Role.ADMIN) return <div className="p-8 text-red-600" data-testid="admin-no-workspace">Access Denied. Please use Admin Dashboard.</div>;
        return <UserWorkspace />;
    }
  };

  return (
    <Layout
      user={user}
      onLogout={handleLogout}
      activeView={activeView}
      onChangeView={(view) => {
        if (view !== "records" && view !== "lab_doctors") {
          resetSelection();
        }
        if (user?.role === Role.LAB && view === "lab_doctors") {
          setSelectedDoctorId(undefined);
          setSelectedDoctorName(undefined);
        }
        if (user?.role === Role.LAB && view === "records") {
          setSelectedDoctorId(undefined);
          setSelectedDoctorName(undefined);
        }
        setActiveView(view);
      }}
    >
      {renderView()}
    </Layout>
  );
};

export default App;
