import React from "react";
import {
  FlaskConical,
  Activity,
  LogOut,
  LayoutDashboard,
  Users,
  FileText,
  Building2,
  Settings,
  Shield,
} from "lucide-react";
import { Role } from "@/types";

const NavItem = ({ icon: Icon, label, active, onClick, badge }) => (
  <button
    onClick={onClick}
    className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${active
        ? "bg-teal-50 text-teal-700 border border-teal-100"
        : "text-slate-600 hover:bg-slate-50 hover:text-slate-800"
      }`}
  >
    <Icon className={`h-5 w-5 ${active ? "text-teal-600" : "text-slate-400"}`} />
    <span className="flex-1 text-left">{label}</span>
    {badge && (
      <span className="px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 rounded-full">
        {badge}
      </span>
    )}
  </button>
);

const Layout = ({ user, onLogout, activeView, onChangeView, children }) => {
  if (!user) {
    return <>{children}</>;
  }

  const isAdmin = user.role === Role.ADMIN;
  const isLab = user.role === Role.LAB;
  const isDoctor = user.role === Role.DOCTOR;

  return (
    <div className="flex h-screen bg-slate-100">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-slate-200 flex flex-col shadow-sm">
        {/* Logo */}
        <div className="p-4 border-b border-slate-200">
          <div className="flex items-center space-x-3">
            <img src="/logo.png" alt="Clinomic Logo" className="h-10 w-10 object-contain" />
            <div>
              <h1 className="font-bold text-slate-800 text-lg">Clinomic</h1>
              <p className="text-xs text-slate-500">B12 Screening Platform</p>
            </div>
          </div>
        </div>

        {/* User Info */}
        <div className="p-4 border-b border-slate-200">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 bg-slate-100 rounded-full flex items-center justify-center">
              <span className="text-lg font-semibold text-slate-600">
                {user.name?.charAt(0) || user.id?.charAt(0) || "U"}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-800 truncate">{user.name || user.id}</p>
              <span
                className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${isAdmin
                    ? "bg-purple-100 text-purple-700"
                    : isDoctor
                      ? "bg-blue-100 text-blue-700"
                      : "bg-teal-100 text-teal-700"
                  }`}
              >
                {user.role}
              </span>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {isAdmin && (
            <>
              <NavItem
                icon={LayoutDashboard}
                label="Dashboard"
                active={activeView === "admin_dashboard"}
                onClick={() => onChangeView("admin_dashboard")}
              />
              <NavItem
                icon={Building2}
                label="Labs"
                active={activeView === "admin_labs"}
                onClick={() => onChangeView("admin_labs")}
              />
              <NavItem
                icon={Users}
                label="Doctors"
                active={activeView === "lab_doctors"}
                onClick={() => onChangeView("lab_doctors")}
              />
              <NavItem
                icon={FileText}
                label="Records"
                active={activeView === "records"}
                onClick={() => onChangeView("records")}
              />
            </>
          )}

          {isLab && (
            <>
              <NavItem
                icon={Activity}
                label="Screening"
                active={activeView === "workspace"}
                onClick={() => onChangeView("workspace")}
              />
              <NavItem
                icon={Users}
                label="Doctors"
                active={activeView === "lab_doctors"}
                onClick={() => onChangeView("lab_doctors")}
              />
              <NavItem
                icon={FileText}
                label="Records"
                active={activeView === "records"}
                onClick={() => onChangeView("records")}
              />
            </>
          )}

          {isDoctor && (
            <>
              <NavItem
                icon={Activity}
                label="Screening"
                active={activeView === "workspace"}
                onClick={() => onChangeView("workspace")}
              />
              <NavItem
                icon={FileText}
                label="My Patients"
                active={activeView === "records"}
                onClick={() => onChangeView("records")}
              />
            </>
          )}

          <div className="pt-4 mt-4 border-t border-slate-200">
            <NavItem
              icon={Settings}
              label="Settings"
              active={activeView === "settings"}
              onClick={() => onChangeView("settings")}
            />
          </div>
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-slate-200">
          <button
            onClick={onLogout}
            className="w-full flex items-center justify-center space-x-2 px-4 py-2 text-sm font-medium text-slate-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            <LogOut className="h-4 w-4" />
            <span>Sign Out</span>
          </button>

          <div className="mt-3 text-center">
            <p className="text-xs text-slate-400">v2.0 • Milestone 4</p>
            <div className="flex items-center justify-center space-x-1 mt-1">
              <Shield className="h-3 w-3 text-green-500" />
              <span className="text-xs text-green-600">Secure</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
};

export default Layout;
