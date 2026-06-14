"use client";

import { useState, useEffect } from "react";
import Navbar from "../../components/layout/Navbar";
import api from "../../lib/api";
import { DocumentMeta } from "../../types";
import { FileText, Calendar, HardDrive, RefreshCw, Layers } from "lucide-react";

export default function ReferenceDocsPage() {
  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const fetchDocuments = async () => {
    setLoading(true);
    try {
      const response = await api.get<DocumentMeta[]>("/documents");
      setDocuments(response.data);
    } catch (error) {
      console.error("Failed to fetch documents:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (docId: string, filename: string) => {
    setDownloadingId(docId);
    try {
      const response = await api.get(`/documents/${docId}/download`, {
        responseType: "blob",
      });
      
      // Use the returned blob directly. Axios automatically sets its type based on response headers.
      const blob = response.data as Blob;
      const contentType = blob.type || "application/pdf";
      const url = window.URL.createObjectURL(blob);
      
      const isPdfOrImage = contentType.includes("pdf") || contentType.startsWith("image/");
      
      if (isPdfOrImage) {
        // Open PDF or image inline in a new tab
        window.open(url, "_blank");
        // Keep the URL alive for a while to let the browser tab load the blob before revoking.
        setTimeout(() => window.URL.revokeObjectURL(url), 60000);
      } else {
        // Trigger download
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", filename);
        document.body.appendChild(link);
        link.click();
        link.parentNode?.removeChild(link);
        setTimeout(() => window.URL.revokeObjectURL(url), 100);
      }
    } catch (error) {
      console.error("Failed to download file:", error);
      alert("Failed to view or download file. Please try again.");
    } finally {
      setDownloadingId(null);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
      });
    } catch (e) {
      return dateStr;
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 pb-16 transition-colors duration-200">
      <Navbar />

      <main className="flex-1 px-4 py-8 sm:px-6 lg:px-8 max-w-4xl mx-auto w-full space-y-8">
        
        {/* Header Block */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-zinc-200 dark:border-zinc-800 pb-6">
          <div>
            <span className="flex items-center gap-1 text-[10px] uppercase font-black tracking-widest text-zinc-500 dark:text-zinc-400">
              <Layers className="h-3.5 w-3.5" /> Campus Reference Library
            </span>
            <h1 className="text-3xl font-extrabold tracking-tight text-zinc-900 dark:text-white sm:text-4xl">
              Reference Docs
            </h1>
            <p className="text-xs text-zinc-500 dark:text-slate-450 mt-1.5 max-w-2xl leading-relaxed">
              Read-only index of official college documents, coursework regulations, and bus timings. Click any document to view or download.
            </p>
          </div>
          <button
            onClick={fetchDocuments}
            disabled={loading}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/40 text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200 disabled:opacity-50 cursor-pointer shadow-sm transition-all duration-200"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Documents list */}
        <div className="space-y-4">
          {loading && documents.length === 0 ? (
            /* Skeletons */
            <div className="space-y-3">
              {[1, 2, 3, 4].map((n) => (
                <div
                  key={n}
                  className="flex h-18 w-full animate-pulse items-center justify-between rounded-xl bg-zinc-100/50 dark:bg-zinc-950/20 p-4 border border-zinc-200 dark:border-zinc-900"
                />
              ))}
            </div>
          ) : documents.length === 0 ? (
            /* Empty state */
            <div className="flex min-h-[220px] flex-col items-center justify-center text-center p-8 rounded-xl border border-dashed border-zinc-200 dark:border-zinc-800 bg-zinc-50/20 dark:bg-zinc-950/10">
              <FileText className="h-10 w-10 text-zinc-400 dark:text-zinc-650 mb-3" />
              <h4 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">No reference sheets found</h4>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-sm mt-1 leading-relaxed">
                There are no official regulations or guides indexed in the database catalog at this time.
              </p>
            </div>
          ) : (
            /* Document list */
            <div className="grid gap-2.5 sm:gap-3">
              {documents.map((doc) => (
                <button
                  key={doc.doc_id}
                  onClick={() => handleDownload(doc.doc_id, doc.filename)}
                  disabled={downloadingId !== null}
                  className="w-full flex items-center justify-between rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/40 dark:bg-zinc-950/20 p-3.5 sm:p-4 transition duration-150 hover:border-zinc-300 dark:hover:border-zinc-700 hover:bg-zinc-100/50 dark:hover:bg-zinc-900/20 shadow-sm text-left cursor-pointer disabled:opacity-80 disabled:cursor-not-allowed group min-w-0 gap-3"
                >
                  <div className="flex items-center gap-3.5 truncate flex-1 min-w-0">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-100 dark:bg-zinc-900 text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-800 group-hover:bg-zinc-200 dark:group-hover:bg-zinc-800/80 transition-colors">
                      {downloadingId === doc.doc_id ? (
                        <div className="h-4.5 w-4.5 animate-spin rounded-full border-2 border-zinc-500/30 border-t-zinc-500"></div>
                      ) : (
                        <FileText className="h-4.5 w-4.5" />
                      )}
                    </div>
                    <div className="truncate space-y-0.5 flex-1 min-w-0">
                      <h4
                        className="text-sm font-bold text-zinc-800 dark:text-zinc-200 truncate pr-6 group-hover:text-zinc-950 dark:group-hover:text-white transition-colors"
                        title={doc.filename}
                      >
                        {doc.filename}
                      </h4>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 text-[10px] text-zinc-500 dark:text-zinc-400 font-semibold uppercase tracking-wider">
                        <span className="flex items-center gap-1">
                          <HardDrive className="h-3 w-3 text-zinc-400" />
                          {formatBytes(doc.size_bytes)}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3 text-zinc-400" />
                          {formatDate(doc.uploaded_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  {/* Subtle right indicator telling users it is clickable */}
                  <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-400 dark:text-zinc-500 opacity-0 group-hover:opacity-100 transition-opacity duration-150 pr-2 hidden sm:block">
                    {downloadingId === doc.doc_id ? "Loading..." : "Open"}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
