import { useState } from "react";
import { FileText, ExternalLink, Loader2 } from "lucide-react";
import { SourceChunk } from "../../types";
import api from "../../lib/api";

export default function SourceCard({ source }: { source: SourceChunk }) {
  const [downloading, setDownloading] = useState(false);

  const handleClick = async () => {
    if (downloading || !source.doc_id) return;
    setDownloading(true);
    try {
      const response = await api.get(`/documents/${source.doc_id}/download`, {
        responseType: "blob",
      });
      
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
        link.setAttribute("download", source.source);
        document.body.appendChild(link);
        link.click();
        link.parentNode?.removeChild(link);
        setTimeout(() => window.URL.revokeObjectURL(url), 100);
      }
    } catch (error) {
      console.error("Failed to view source document:", error);
      alert("Failed to view source document. Please try again.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="group rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/20 transition-all duration-200 hover:border-zinc-300 dark:hover:border-zinc-700 hover:shadow-sm dark:hover:shadow-zinc-950/20">
      <button
        onClick={handleClick}
        disabled={downloading}
        className="flex w-full items-center justify-between p-2.5 text-left text-xs font-semibold text-zinc-700 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-white cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <div className="flex items-center gap-2 truncate">
          <FileText className="h-3.5 w-3.5 shrink-0 text-zinc-500 dark:text-zinc-400" />
          <span className="truncate max-w-[150px] sm:max-w-[220px]" title={source.source}>
            {source.source}
          </span>
        </div>
        {downloading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-zinc-500 shrink-0" />
        ) : (
          <ExternalLink className="h-3.5 w-3.5 text-zinc-400 dark:text-zinc-500 shrink-0 group-hover:text-zinc-600 dark:group-hover:text-zinc-300 transition-colors" />
        )}
      </button>
    </div>
  );
}
