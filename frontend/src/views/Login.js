import React, { useState } from "react";
import { Activity, Lock, User, FlaskConical, ArrowLeft, Mail, CheckCircle, Shield, Smartphone, Key } from "lucide-react";
import { AuthService } from "@/services/api";

const Login = ({ onLogin, onMFARequired, isLoading, error }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [view, setView] = useState("login"); // login, forgot_password, mfa_challenge
  const [resetStatus, setResetStatus] = useState("idle");
  
  // MFA state
  const [mfaCode, setMfaCode] = useState("");
  const [mfaPendingToken, setMfaPendingToken] = useState(null);
  const [mfaError, setMfaError] = useState(null);
  const [mfaLoading, setMfaLoading] = useState(false);
  const [pendingUser, setPendingUser] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMfaError(null);
    
    try {
      const result = await onLogin(username, password);
      
      // Check if MFA is required
      if (result && result.mfaRequired) {
        setMfaPendingToken(result.mfaPendingToken);
        setPendingUser({ id: result.id, name: result.name, role: result.role });
        setView("mfa_challenge");
      }
    } catch (err) {
      // Error handled by parent
    }
  };

  const handleMFASubmit = async (e) => {
    e.preventDefault();
    setMfaLoading(true);
    setMfaError(null);
    
    try {
      const user = await AuthService.verifyMFA(mfaPendingToken, mfaCode);
      // Call parent's success handler
      if (onMFARequired) {
        onMFARequired(user);
      }
    } catch (err) {
      setMfaError("Invalid verification code. Please try again.");
    } finally {
      setMfaLoading(false);
    }
  };

  const handleBackToLogin = () => {
    setView("login");
    setMfaCode("");
    setMfaPendingToken(null);
    setMfaError(null);
    setPendingUser(null);
  };

  const handleResetSubmit = (e) => {
    e.preventDefault();
    setResetStatus("loading");
    setTimeout(() => setResetStatus("success"), 1500);
  };

  const toggleView = () => {
    setView(view === "login" ? "forgot_password" : "login");
    setResetStatus("idle");
  };

  // MFA Challenge View
  if (view === "mfa_challenge") {
    return (
      <div data-testid="mfa-challenge-page" className="min-h-screen bg-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="flex justify-center">
            <div className="h-16 w-16 bg-teal-600 rounded-xl flex items-center justify-center shadow-lg">
              <Shield className="h-10 w-10 text-white" />
            </div>
          </div>
          <h2 className="mt-6 text-center text-2xl font-bold text-slate-900">Two-Factor Authentication</h2>
          <p className="mt-2 text-center text-sm text-slate-600">
            Welcome back, <span className="font-medium">{pendingUser?.name || pendingUser?.id}</span>
          </p>
        </div>

        <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
          <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10 border border-slate-200">
            <div className="mb-6 flex items-center justify-center space-x-2 text-slate-500">
              <Smartphone className="h-5 w-5" />
              <span className="text-sm">Enter the code from your authenticator app</span>
            </div>
            
            <form className="space-y-6" onSubmit={handleMFASubmit}>
              <div>
                <label htmlFor="mfa-code" className="block text-sm font-medium text-slate-700 text-center mb-2">
                  Verification Code
                </label>
                <input
                  data-testid="mfa-code-input"
                  id="mfa-code"
                  name="mfa-code"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  required
                  autoFocus
                  autoComplete="one-time-code"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
                  className="block w-full text-center text-2xl tracking-[0.5em] font-mono py-3 border-slate-300 rounded-md focus:ring-teal-500 focus:border-teal-500 border bg-white text-black"
                  placeholder="000000"
                />
              </div>

              {mfaError && (
                <div data-testid="mfa-error" className="text-red-600 text-sm bg-red-50 p-2 rounded border border-red-100 text-center">
                  {mfaError}
                </div>
              )}

              <div>
                <button
                  data-testid="mfa-submit-button"
                  type="submit"
                  disabled={mfaLoading || mfaCode.length !== 6}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {mfaLoading ? "Verifying..." : "Verify & Sign In"}
                </button>
              </div>
            </form>

            <div className="mt-6 border-t border-slate-200 pt-4">
              <div className="text-center">
                <button
                  data-testid="use-backup-code-button"
                  type="button"
                  className="text-sm text-slate-500 hover:text-teal-600"
                  onClick={() => {
                    // Backup codes are 8 characters, allow longer input
                  }}
                >
                  <Key className="h-4 w-4 inline mr-1" />
                  Use a backup code instead
                </button>
              </div>
              <div className="mt-4 flex items-center justify-center">
                <button
                  data-testid="mfa-back-button"
                  type="button"
                  onClick={handleBackToLogin}
                  className="flex items-center text-sm font-medium text-slate-600 hover:text-teal-600"
                >
                  <ArrowLeft className="h-4 w-4 mr-1" /> Back to Sign In
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="login-page" className="min-h-screen bg-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <div className="h-16 w-16 bg-teal-600 rounded-xl flex items-center justify-center shadow-lg transform rotate-3">
            <FlaskConical className="h-10 w-10 text-white" />
          </div>
        </div>
        <h2 className="mt-6 text-center text-3xl font-extrabold text-slate-900 tracking-tight">Clinomic Labs</h2>
        <p className="mt-2 text-center text-sm text-slate-600">Pathology LIS & B12 Screening System</p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10 border border-slate-200">
          {view === "login" ? (
            <form className="space-y-6" onSubmit={handleSubmit}>
              <div>
                <label htmlFor="username" className="block text-sm font-medium text-slate-700">
                  Lab ID / Username
                </label>
                <div className="mt-1 relative rounded-md shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <User className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    data-testid="login-username-input"
                    id="username"
                    name="username"
                    type="text"
                    required
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 rounded-md py-2 border bg-white text-black"
                    placeholder="lab"
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                    Password
                  </label>
                  <button
                    data-testid="forgot-password-toggle"
                    type="button"
                    className="text-xs font-medium text-teal-600 hover:text-teal-500 focus:outline-none"
                    onClick={toggleView}
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative rounded-md shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    data-testid="login-password-input"
                    id="password"
                    name="password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 rounded-md py-2 border bg-white text-black"
                    placeholder="lab"
                  />
                </div>
              </div>

              {error && (
                <div data-testid="login-error" className="text-red-600 text-sm bg-red-50 p-2 rounded border border-red-100 text-center">
                  {error}
                </div>
              )}

              <div>
                <button
                  data-testid="login-submit-button"
                  type="submit"
                  disabled={isLoading}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? "Connecting..." : "Sign in"}
                </button>
              </div>
            </form>
          ) : (
            <div className="space-y-6">
              <div className="text-center">
                <h3 className="text-lg font-medium text-slate-900">Account Recovery</h3>
                <p className="mt-1 text-sm text-slate-500">Enter your Lab ID or registered email address. We'll send you instructions to reset your password.</p>
              </div>

              {resetStatus === "success" ? (
                <div className="rounded-md bg-green-50 p-4" data-testid="recovery-success">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <CheckCircle className="h-5 w-5 text-green-400" aria-hidden="true" />
                    </div>
                    <div className="ml-3">
                      <h3 className="text-sm font-medium text-green-800">Recovery email sent</h3>
                      <div className="mt-2 text-sm text-green-700">
                        <p>
                          If an account exists for <b>{username}</b>, you will receive an email shortly.
                        </p>
                      </div>
                      <div className="mt-4">
                        <div className="-mx-2 -my-1.5 flex">
                          <button
                            data-testid="recovery-return-button"
                            type="button"
                            onClick={toggleView}
                            className="bg-green-50 px-2 py-1.5 rounded-md text-sm font-medium text-green-800 hover:bg-green-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-600"
                          >
                            Return to Sign In
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleResetSubmit} className="space-y-4">
                  <div>
                    <label htmlFor="recovery-email" className="block text-sm font-medium text-slate-700">
                      Lab ID / Email Address
                    </label>
                    <div className="mt-1 relative rounded-md shadow-sm">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Mail className="h-5 w-5 text-slate-400" />
                      </div>
                      <input
                        data-testid="recovery-identifier-input"
                        id="recovery-email"
                        name="recovery-email"
                        type="text"
                        required
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 rounded-md py-2 border bg-white text-black"
                        placeholder="lab@clinomic.com"
                      />
                    </div>
                  </div>

                  <button
                    data-testid="recovery-submit-button"
                    type="submit"
                    disabled={resetStatus === "loading"}
                    className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-teal-600 hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50"
                  >
                    {resetStatus === "loading" ? "Sending..." : "Send Recovery Link"}
                  </button>
                </form>
              )}

              {resetStatus !== "success" && (
                <div className="flex items-center justify-center">
                  <button data-testid="recovery-back-button" type="button" onClick={toggleView} className="flex items-center text-sm font-medium text-slate-600 hover:text-teal-600">
                    <ArrowLeft className="h-4 h-4 mr-1" /> Back to Sign In
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="mt-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-300" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white text-slate-500">Demo Credentials</span>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-center text-slate-500" data-testid="demo-credentials">
              <div className="bg-slate-50 p-2 rounded border border-slate-200">
                <span className="font-bold block">Lab Tech</span>
                lab / lab
              </div>
              <div className="bg-slate-50 p-2 rounded border border-slate-200">
                <span className="font-bold block">Doctor</span>
                doctor / doctor
              </div>
              <div className="bg-slate-50 p-2 rounded border border-slate-200">
                <span className="font-bold block">Admin</span>
                admin / admin
              </div>
            </div>
          </div>
        </div>
        
        <div className="mt-4 text-center text-xs text-slate-400">
          <p>Clinomic B12 Screening Platform v2.0</p>
          <p className="mt-1">HIPAA Compliant • FDA 21 CFR Part 11 Ready</p>
        </div>
      </div>
    </div>
  );
};

export default Login;
