import React, { useState } from "react";
import { Upload, FileText, Play, RotateCcw, Activity, Stethoscope, FileCheck, CheckCircle } from "lucide-react";

import { INITIAL_CBC_ROWS } from "../constants";
import CBCTable from "../components/CBCTable";
import ResultPanel from "../components/ResultPanel";
import ConsentCapture from "../components/ConsentCapture";
import { LisService, ConsentService } from "../services/api";

const UserWorkspace = () => {
  const [patient, setPatient] = useState({
    id: "",
    name: "",
    age: 0,
    sex: "F",
    date: new Date().toISOString().split("T")[0],
    labId: "LAB-2024-001",
    referringDoctor: "",
  });

  const [rows, setRows] = useState(INITIAL_CBC_ROWS);
  const [activeTab, setActiveTab] = useState("manual");
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const [screeningError, setScreeningError] = useState(null);
  
  // Consent state
  const [showConsentCapture, setShowConsentCapture] = useState(false);
  const [consentId, setConsentId] = useState(null);
  const [hasValidConsent, setHasValidConsent] = useState(false);

  const handleCBCChange = (key, value) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, value } : r)));
  };

  const handlePDFUpload = async (e) => {
    if (e.target.files && e.target.files[0]) {
      setUploadStatus("Scanning PDF...");
      setIsProcessing(true);
      setScreeningError(null);
      try {
        const data = await LisService.uploadPdf(e.target.files[0]);
        setRows((prev) =>
          prev.map((r) => ({
            ...r,
            value: data[r.key] !== undefined ? String(data[r.key]) : r.value,
          }))
        );
        setUploadStatus("Extraction Complete. Please verify values below.");
        setActiveTab("manual");
      } catch (err) {
        setUploadStatus("Error reading PDF.");
      } finally {
        setIsProcessing(false);
      }
    }
  };

  const checkExistingConsent = async () => {
    if (!patient.id) return false;
    try {
      const status = await ConsentService.getStatus(patient.id);
      if (status.hasConsent) {
        setConsentId(status.consentId);
        setHasValidConsent(true);
        return true;
      }
    } catch (err) {
      console.error("Failed to check consent:", err);
    }
    return false;
  };

  const handleConsentCaptured = async (consentData) => {
    const result = await ConsentService.record(patient.id, consentData);
    setConsentId(result.id);
    setHasValidConsent(true);
    setShowConsentCapture(false);
    // Automatically run screening after consent
    runScreeningWithConsent(result.id);
  };

  const runScreeningWithConsent = async (consentIdToUse) => {
    setIsProcessing(true);
    setScreeningError(null);
    try {
      const cbcData = {};
      rows.forEach((r) => {
        const val = parseFloat(r.value);
        if (!Number.isNaN(val)) cbcData[r.key] = val;
      });

      const res = await LisService.predictB12(cbcData, patient, consentIdToUse);
      setResult(res);
    } catch (err) {
      console.error("Screening Error:", err);
      setResult(null);
      setScreeningError("Screening failed. Please verify inputs and try again.");
    } finally {
      setIsProcessing(false);
    }
  };

  const runScreening = async () => {
    setScreeningError(null);
    
    if (!patient.id) {
      setScreeningError("Patient ID is required to run screening.");
      return;
    }

    // Check for existing consent
    const hasConsent = await checkExistingConsent();
    
    if (hasConsent) {
      // Run with existing consent
      runScreeningWithConsent(consentId);
    } else {
      // Show consent capture
      setShowConsentCapture(true);
    }
  };

  const resetForm = () => {
    setResult(null);
    setScreeningError(null);
    setRows(INITIAL_CBC_ROWS.map((r) => ({ ...r, value: "" })));
    setPatient((prev) => ({ ...prev, id: "", name: "" }));
    setConsentId(null);
    setHasValidConsent(false);
    setShowConsentCapture(false);
  };

  // Show consent capture modal
  if (showConsentCapture) {
    return (
      <div className="max-w-2xl mx-auto" data-testid="consent-capture-view">
        <ConsentCapture
          patient={patient}
          onConsentCaptured={handleConsentCaptured}
          onCancel={() => setShowConsentCapture(false)}
        />
      </div>
    );
  }

  return (
    <div data-testid="workspace-page" className="max-w-7xl mx-auto space-y-6">
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-5 space-y-6">
          <section className="bg-white border border-slate-300 rounded-sm shadow-sm overflow-hidden">
            <div className="bg-slate-50 border-b border-slate-200 px-4 py-3 flex items-center justify-between">
              <h3 className="font-bold text-slate-700 text-sm uppercase tracking-wide">Patient Registration</h3>
              <span className="text-xs font-mono text-slate-500">{patient.labId}</span>
            </div>
            <div className="p-4 grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-xs font-semibold text-slate-500 mb-1">Full Name</label>
                <input
                  data-testid="patient-name-input"
                  type="text"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm focus:ring-1 focus:ring-teal-500 focus:border-teal-500 bg-white text-black"
                  placeholder="Doe, Jane"
                  value={patient.name}
                  onChange={(e) => setPatient({ ...patient, name: e.target.value })}
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-semibold text-slate-500 mb-1">Referring Doctor</label>
                <div className="relative">
                  <Stethoscope className="w-4 h-4 absolute left-2 top-2 text-slate-400" />
                  <select
                    data-testid="referring-doctor-select"
                    className="w-full border border-slate-300 rounded pl-8 pr-2 py-1.5 text-sm bg-white text-black"
                    value={patient.referringDoctor}
                    onChange={(e) => setPatient({ ...patient, referringDoctor: e.target.value })}
                  >
                    <option value="">Select Physician...</option>
                    <option value="DOC-DEMO-001">Dr. Sarah Chen (Hematology)</option>
                    <option value="DOC-DEMO-002">Dr. Michael Ross (Internal Medicine)</option>
                    <option value="DOC-DEMO-003">Dr. Emily Watson (General Practice)</option>
                    <option value="DOC-DEMO-004">Dr. Robert Chase (Critical Care)</option>
                    <option value="DOC-DEMO-005">Dr. Lisa House (Neurology)</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Age</label>
                <input
                  data-testid="patient-age-input"
                  type="number"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm bg-white text-black"
                  value={patient.age || ""}
                  onChange={(e) => setPatient({ ...patient, age: parseInt(e.target.value || "0", 10) })}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Sex</label>
                <select
                  data-testid="patient-sex-select"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm bg-white"
                  value={patient.sex}
                  onChange={(e) => setPatient({ ...patient, sex: e.target.value })}
                >
                  <option value="F">Female</option>
                  <option value="M">Male</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Patient ID</label>
                <input
                  data-testid="patient-id-input"
                  type="text"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm font-mono bg-white text-black"
                  value={patient.id}
                  onChange={(e) => {
                    setPatient({ ...patient, id: e.target.value });
                    setHasValidConsent(false);
                    setConsentId(null);
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Date</label>
                <input
                  data-testid="patient-date-input"
                  type="date"
                  className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm bg-white text-black"
                  value={patient.date}
                  onChange={(e) => setPatient({ ...patient, date: e.target.value })}
                />
              </div>
              
              {/* Consent Status Indicator */}
              {patient.id && (
                <div className="col-span-2">
                  {hasValidConsent ? (
                    <div className="flex items-center p-2 bg-green-50 border border-green-100 rounded text-sm text-green-700">
                      <CheckCircle className="h-4 w-4 mr-2" />
                      <span>Consent recorded (ID: {consentId?.slice(0, 8)}...)</span>
                    </div>
                  ) : (
                    <div className="flex items-center p-2 bg-slate-50 border border-slate-200 rounded text-sm text-slate-600">
                      <FileCheck className="h-4 w-4 mr-2" />
                      <span>Consent will be captured before screening</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

          <div className="bg-white border border-slate-300 rounded-sm shadow-sm overflow-hidden">
            <div className="border-b border-slate-200 flex">
              <button
                data-testid="tab-manual"
                onClick={() => setActiveTab("manual")}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center ${
                  activeTab === "manual" ? "text-teal-700 border-b-2 border-teal-600 bg-teal-50/50" : "text-slate-500 hover:bg-slate-50"
                }`}
              >
                <FileText className="w-4 h-4 mr-2" />
                Manual Entry
              </button>
              <button
                data-testid="tab-pdf"
                onClick={() => setActiveTab("pdf")}
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center ${
                  activeTab === "pdf" ? "text-teal-700 border-b-2 border-teal-600 bg-teal-50/50" : "text-slate-500 hover:bg-slate-50"
                }`}
              >
                <Upload className="w-4 h-4 mr-2" />
                Import PDF Report
              </button>
            </div>

            {activeTab === "pdf" && (
              <div className="p-6 bg-slate-50">
                <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-teal-500 transition-colors bg-white cursor-pointer relative">
                  <input data-testid="pdf-file-input" type="file" accept=".pdf" onChange={handlePDFUpload} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
                  <Upload className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                  <p className="text-sm text-slate-600 font-medium">Click to upload Hospital CBC Report (PDF)</p>
                  <p className="text-xs text-slate-400 mt-1">Supports Siemens, Abbott, Roche formats</p>
                </div>
                {uploadStatus && (
                  <div data-testid="pdf-upload-status" className="mt-4 flex items-center text-sm text-teal-700 bg-teal-50 border border-teal-100 p-2 rounded">
                    {isProcessing && <div className="animate-spin h-3 w-3 border-2 border-teal-600 border-t-transparent rounded-full mr-2" />}
                    {uploadStatus}
                  </div>
                )}
              </div>
            )}

            <div className={`${activeTab === "manual" ? "block" : "hidden"}`}>
              <CBCTable rows={rows} patientSex={patient.sex} onValueChange={handleCBCChange} />
            </div>

            {screeningError && (
              <div data-testid="screening-error" className="px-4 py-3 bg-red-50 border-t border-red-100 text-sm text-red-700">
                {screeningError}
              </div>
            )}

            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-between">
              <button data-testid="reset-form-button" onClick={resetForm} className="px-4 py-2 border border-slate-300 rounded bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 flex items-center">
                <RotateCcw className="w-4 h-4 mr-2" /> Reset
              </button>
              <button
                data-testid="run-screening-button"
                onClick={runScreening}
                disabled={isProcessing}
                className="px-6 py-2 bg-teal-700 rounded text-white text-sm font-bold hover:bg-teal-800 shadow-sm flex items-center disabled:opacity-50"
              >
                {isProcessing ? (
                  "Analyzing..."
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-2 fill-current" /> Run B12 Screening
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        <div className="xl:col-span-7">
          {result ? (
            <ResultPanel result={result} patient={patient} cbcRows={rows} />
          ) : (
            <div className="h-full min-h-[500px] border-2 border-dashed border-slate-300 rounded-sm bg-slate-50 flex flex-col items-center justify-center text-slate-400" data-testid="no-results-empty">
              <div className="bg-white p-6 rounded-full shadow-sm mb-4">
                <Activity className="w-12 h-12 text-slate-300" />
              </div>
              <h3 className="text-lg font-medium text-slate-500">No Analysis Results Yet</h3>
              <p className="max-w-xs text-center text-sm mt-2">Enter CBC values manually or upload a report, then click "Run Screening" to see B12 deficiency risk analysis.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default UserWorkspace;
