"use client";

import { useState, useEffect, useRef } from "react";
import Navbar from "../../../components/layout/Navbar";
import PDFUploader from "../../../components/admin/PDFUploader";
import api from "../../../lib/api";
import { DocumentMeta, QuickLink } from "../../../types";
import { FileText, Trash2, Calendar, HardDrive, RefreshCw, Layers, Link as LinkIcon, Plus, FileEdit } from "lucide-react";

export default function DocumentManagementPage() {
  const topRef = useRef<HTMLDivElement>(null);
  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Tabs management
  const [activeTab, setActiveTab] = useState<"catalog" | "links">("catalog");

  // Quick Links states
  const [quickLinks, setQuickLinks] = useState<QuickLink[]>([]);
  const [linksLoading, setLinksLoading] = useState(false);
  const [isEditing, setIsEditing] = useState<string | null>(null); // "new", ID, or null
  const [editService, setEditService] = useState("");
  const [editLink, setEditLink] = useState("");
  const [editPurpose, setEditPurpose] = useState("");
  const [savingLink, setSavingLink] = useState(false);
  const [deletingLinkId, setDeletingLinkId] = useState<string | null>(null);

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

  const fetchQuickLinks = async () => {
    setLinksLoading(true);
    try {
      const response = await api.get<QuickLink[]>("/quick_links");
      setQuickLinks(response.data);
    } catch (error) {
      console.error("Failed to fetch quick links:", error);
    } finally {
      setLinksLoading(false);
    }
  };

  const handleSaveLink = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editService.trim() || !editLink.trim()) return;

    setSavingLink(true);
    try {
      if (isEditing === "new") {
        const response = await api.post<QuickLink>("/quick_links", {
          service: editService,
          link: editLink,
          purpose: editPurpose,
        });
        setQuickLinks((prev) => [...prev, response.data].sort((a, b) => a.service.localeCompare(b.service)));
      } else {
        const response = await api.put<QuickLink>(`/quick_links/${isEditing}`, {
          service: editService,
          link: editLink,
          purpose: editPurpose,
        });
        setQuickLinks((prev) =>
          prev.map((link) => (link.id === isEditing ? response.data : link)).sort((a, b) => a.service.localeCompare(b.service))
        );
      }
      setIsEditing(null);
      setEditService("");
      setEditLink("");
      setEditPurpose("");
    } catch (error) {
      console.error("Failed to save quick link:", error);
      alert("Failed to save quick link. Please check inputs and try again.");
    } finally {
      setSavingLink(false);
    }
  };

  const handleDeleteLink = async (linkId: string) => {
    if (!confirm("Are you sure you want to delete this quick link?")) {
      return;
    }

    setDeletingLinkId(linkId);
    try {
      await api.delete(`/quick_links/${linkId}`);
      setQuickLinks((prev) => prev.filter((link) => link.id !== linkId));
    } catch (error) {
      console.error("Failed to delete quick link:", error);
      alert("Failed to delete quick link. Please try again.");
    } finally {
      setDeletingLinkId(null);
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm("Are you sure you want to delete this document? This will remove all associated RAG index vectors from Qdrant and backing files from GCS.")) {
      return;
    }

    setDeletingId(docId);
    try {
      await api.delete(`/documents/${docId}`);
      setDocuments((prev) => prev.filter((doc) => doc.doc_id !== docId));
    } catch (error) {
      console.error("Failed to delete document:", error);
      alert("Failed to delete document. Please try again.");
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    fetchDocuments();
    fetchQuickLinks();
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

      <main className="flex-1 px-4 py-8 sm:px-6 lg:px-8 max-w-7xl mx-auto w-full space-y-8">
        <div ref={topRef} />
        
        {/* Header Block */}
        <div>
          <div className="flex items-center justify-between gap-4">
            <div>
              <span className="flex items-center gap-1 text-[10px] uppercase font-black tracking-widest text-zinc-500 dark:text-zinc-400">
                <Layers className="h-3.5 w-3.5" /> Database Console
              </span>
              <h1 className="text-3xl font-extrabold tracking-tight text-zinc-900 dark:text-white sm:text-4xl">
                Docs Ingestion
              </h1>
            </div>
            <button
              onClick={fetchDocuments}
              disabled={loading}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/40 text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200 disabled:opacity-50 cursor-pointer shadow-sm transition-all duration-200"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
          <p className="text-xs text-zinc-500 dark:text-slate-450 mt-3 max-w-2xl leading-relaxed">
            Upload PDF documents or images
          </p>
        </div>

        {/* Tabs Selection */}
        <div className="flex border-b border-zinc-200 dark:border-zinc-800 gap-1.5 shrink-0">
          <button
            onClick={() => setActiveTab("catalog")}
            className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider border-b-2 transition-all cursor-pointer ${
              activeTab === "catalog"
                ? "border-zinc-900 dark:border-zinc-200 text-zinc-900 dark:text-zinc-150"
                : "border-transparent text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300"
            }`}
          >
            Docs
          </button>
          <button
            onClick={() => setActiveTab("links")}
            className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider border-b-2 transition-all cursor-pointer ${
              activeTab === "links"
                ? "border-zinc-900 dark:border-zinc-200 text-zinc-900 dark:text-zinc-150"
                : "border-transparent text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300"
            }`}
          >
            Quick Links
          </button>
        </div>

        {activeTab === "catalog" ? (
          /* 2-Column Desktop Grid */
          <div className="grid gap-4 sm:gap-6 lg:gap-8 lg:grid-cols-3 w-full min-w-0">
            
            {/* Uploader Column */}
            <div className="lg:col-span-1 space-y-6 w-full min-w-0">
              <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/10 p-4 sm:p-6 backdrop-blur-xl space-y-4 w-full min-w-0">
                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  Index Reference Docs
                </h3>
                <PDFUploader onUploadSuccess={fetchDocuments} />
              </div>
            </div>

            {/* Document list Column */}
            <div className="lg:col-span-2 space-y-4 w-full min-w-0">
              <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/10 p-4 sm:p-6 backdrop-blur-xl space-y-4 w-full min-w-0">
                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  Indexed File
                </h3>

                {loading && documents.length === 0 ? (
                  /* Skeletons */
                  <div className="space-y-3">
                    {[1, 2, 3].map((n) => (
                      <div
                        key={n}
                        className="flex h-16 w-full animate-pulse items-center justify-between rounded-xl bg-zinc-100/50 dark:bg-zinc-950/20 p-4 border border-zinc-200 dark:border-zinc-900"
                      />
                    ))}
                  </div>
                ) : documents.length === 0 ? (
                  /* Empty state */
                  <div className="flex min-h-[200px] flex-col items-center justify-center text-center p-8 rounded-xl border border-dashed border-zinc-200 dark:border-zinc-800 bg-zinc-50/20 dark:bg-zinc-950/10">
                    <FileText className="h-10 w-10 text-zinc-400 dark:text-zinc-600 mb-3" />
                    <h4 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">No reference catalogs uploaded</h4>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-sm mt-1 leading-relaxed">
                      Upload official academic regulations, bus charts, or guidelines to initialize the RAG knowledge bank.
                    </p>
                  </div>
                ) : (
                  /* Document list table */
                  <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                    {documents.map((doc) => (
                      <div
                        key={doc.doc_id}
                        className="flex items-center justify-between rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/40 dark:bg-zinc-950/20 p-4 transition duration-150 hover:border-zinc-300 dark:hover:border-zinc-700 hover:bg-zinc-100/50 dark:hover:bg-zinc-900/20 shadow min-w-0 gap-3"
                      >
                        <div className="flex items-center gap-3.5 truncate flex-1 min-w-0">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-100 dark:bg-zinc-900 text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-800">
                            <FileText className="h-4.5 w-4.5" />
                          </div>
                          <div className="truncate space-y-0.5 flex-1 min-w-0">
                            <h4
                              className="text-sm font-bold text-zinc-800 dark:text-zinc-200 truncate pr-6"
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

                        <button
                          onClick={() => handleDelete(doc.doc_id)}
                          disabled={deletingId === doc.doc_id}
                          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-zinc-500 hover:bg-red-500/10 hover:text-red-400 transition-all border border-zinc-200 dark:border-zinc-800 hover:border-red-500/20 disabled:opacity-50 cursor-pointer"
                        >
                          {deletingId === doc.doc_id ? (
                            <div className="h-4 w-4 animate-spin rounded-full border-2 border-red-500/30 border-t-red-500"></div>
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          /* Quick Links Manager Section */
          <div className="space-y-6 w-full min-w-0">
            <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/10 p-4 sm:p-6 backdrop-blur-xl space-y-6 w-full min-w-0">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                  <h3 className="text-base font-bold text-zinc-900 dark:text-white">
                    Fallback Quick Links Directory
                  </h3>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                    RAG bot refers to when query context is not found in Reference Docs.
                  </p>
                </div>
                {isEditing === null && (
                  <button
                    onClick={() => {
                      setIsEditing("new");
                      setEditService("");
                      setEditLink("");
                      setEditPurpose("");
                      topRef.current?.scrollIntoView({ behavior: "smooth" });
                    }}
                    className="inline-flex items-center justify-center rounded-xl bg-zinc-900 dark:bg-zinc-800 text-white border border-zinc-950 dark:border-zinc-700 px-4 py-2 text-xs font-bold hover:bg-zinc-800 dark:hover:bg-zinc-700 transition cursor-pointer shadow-sm"
                  >
                    <Plus className="h-4 w-4 mr-1.5" /> Add New Link
                  </button>
                )}
              </div>

              {/* Edit Form Card */}
              {isEditing !== null && (
                <form onSubmit={handleSaveLink} className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950/20 p-4 space-y-4 shadow-inner">
                  <h4 className="text-xs font-extrabold uppercase tracking-wider text-zinc-800 dark:text-zinc-200">
                    {isEditing === "new" ? "Add New Quick Link" : "Edit Quick Link"}
                  </h4>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400">Service Name *</label>
                      <input
                        type="text"
                        required
                        value={editService}
                        onChange={(e) => setEditService(e.target.value)}
                        placeholder="e.g. Health Centre Slot Booking"
                        className="w-full rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 px-3.5 py-2.5 text-xs text-zinc-900 dark:text-white focus:outline-none focus:border-zinc-400 dark:focus:border-zinc-700 shadow-sm"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400">Link URL / Contact details *</label>
                      <input
                        type="text"
                        required
                        value={editLink}
                        onChange={(e) => setEditLink(e.target.value)}
                        placeholder="e.g. https://hcrs.iitgn.ac.in/slotbooking/"
                        className="w-full rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 px-3.5 py-2.5 text-xs text-zinc-900 dark:text-white focus:outline-none focus:border-zinc-400 dark:focus:border-zinc-700 shadow-sm"
                      />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-black uppercase tracking-wider text-zinc-500 dark:text-zinc-400">Purpose / Description</label>
                    <textarea
                      value={editPurpose}
                      onChange={(e) => setEditPurpose(e.target.value)}
                      placeholder="Describe when this link should be used (e.g. for medical emergencies, appointment booking...)"
                      rows={2}
                      className="w-full rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 px-3.5 py-2.5 text-xs text-zinc-900 dark:text-white focus:outline-none focus:border-zinc-400 dark:focus:border-zinc-700 shadow-sm resize-none"
                    />
                  </div>
                  <div className="flex justify-end gap-2.5">
                    <button
                      type="button"
                      onClick={() => setIsEditing(null)}
                      className="rounded-xl border border-zinc-200 dark:border-zinc-800 px-4 py-2 text-xs font-bold text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-900/40 cursor-pointer transition"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={savingLink}
                      className="inline-flex items-center rounded-xl bg-zinc-900 dark:bg-zinc-800 text-white border border-zinc-950 dark:border-zinc-700 px-4 py-2 text-xs font-bold hover:bg-zinc-800 dark:hover:bg-zinc-700 disabled:opacity-50 cursor-pointer transition shadow-sm"
                    >
                      {savingLink ? "Saving..." : "Save Link"}
                    </button>
                  </div>
                </form>
              )}

              {/* Quick links list table */}
              {linksLoading && quickLinks.length === 0 ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((n) => (
                    <div key={n} className="flex h-16 w-full animate-pulse items-center justify-between rounded-xl bg-zinc-100/50 dark:bg-zinc-950/20 p-4 border border-zinc-200 dark:border-zinc-900" />
                  ))}
                </div>
              ) : quickLinks.length === 0 ? (
                <div className="flex min-h-[200px] flex-col items-center justify-center text-center p-8 rounded-xl border border-dashed border-zinc-200 dark:border-zinc-800 bg-zinc-50/20 dark:bg-zinc-950/10">
                  <LinkIcon className="h-10 w-10 text-zinc-400 dark:text-zinc-600 mb-3" />
                  <h4 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">No quick links configured</h4>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 max-w-sm mt-1 leading-relaxed">
                    Add contact endpoints or system directories to help GN Saarthi guide students when direct catalog answers aren't available.
                  </p>
                </div>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {quickLinks.map((link) => (
                    <div
                      key={link.id}
                      className="flex flex-col justify-between rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50/40 dark:bg-zinc-955/20 p-4 transition duration-150 hover:border-zinc-300 dark:hover:border-zinc-700 hover:bg-zinc-100/50 dark:hover:bg-zinc-900/20 shadow gap-3.5 min-w-0"
                    >
                      <div className="space-y-1.5 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="inline-flex items-center rounded-lg bg-zinc-100 dark:bg-zinc-900 px-2.5 py-1 text-[10px] font-bold text-zinc-700 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-800 whitespace-normal break-words text-left">
                            {link.service}
                          </span>
                        </div>
                        <a
                          href={link.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline block truncate"
                          title={link.link}
                        >
                          {link.link}
                        </a>
                        <p className="text-[11px] text-zinc-500 dark:text-zinc-400 leading-relaxed line-clamp-2" title={link.purpose}>
                          {link.purpose || "No description provided."}
                        </p>
                      </div>
                      <div className="flex justify-end gap-1.5 pt-2 border-t border-zinc-200/50 dark:border-zinc-800/40">
                        <button
                          onClick={() => {
                            setIsEditing(link.id);
                            setEditService(link.service);
                            setEditLink(link.link);
                            setEditPurpose(link.purpose);
                            topRef.current?.scrollIntoView({ behavior: "smooth" });
                          }}
                          className="flex h-7.5 w-7.5 items-center justify-center rounded-lg text-zinc-500 hover:bg-zinc-200/50 dark:hover:bg-zinc-850 hover:text-zinc-800 dark:hover:text-white transition-all border border-zinc-200 dark:border-zinc-800 cursor-pointer"
                        >
                          <FileEdit className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => handleDeleteLink(link.id)}
                          disabled={deletingLinkId === link.id}
                          className="flex h-7.5 w-7.5 items-center justify-center rounded-lg text-zinc-500 hover:bg-red-500/10 hover:text-red-400 transition-all border border-zinc-200 dark:border-zinc-800 hover:border-red-500/20 disabled:opacity-50 cursor-pointer"
                        >
                          {deletingLinkId === link.id ? (
                            <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-red-500/30 border-t-red-500"></div>
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
