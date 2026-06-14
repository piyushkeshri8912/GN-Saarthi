import { useState, useCallback } from "react";
import { UploadCloud, FileText, CheckCircle, AlertTriangle, Loader2 } from "lucide-react";
import api from "../../lib/api";

interface PDFUploaderProps {
  onUploadSuccess: () => void;
}

export default function PDFUploader({ onUploadSuccess }: PDFUploaderProps) {
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const uploadFile = async (file: File) => {
    const allowedExtensions = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"];
    const fileExtension = "." + file.name.toLowerCase().split(".").pop();
    const isImage = file.type.startsWith("image/") && allowedExtensions.includes(fileExtension);
    const isPdf = file.type === "application/pdf" || fileExtension === ".pdf";

    if (!isPdf && !isImage) {
      setError("Only PDF and common image files (.png, .jpg, .jpeg, .webp, .tiff) are supported.");
      return;
    }

    setError(null);
    setSuccess(null);
    setUploading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await api.post("/documents/upload", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      if (response.data.success) {
        setSuccess(`Successfully indexed "${file.name}"`);
        onUploadSuccess();
      } else {
        setError("Failed to parse and index document. Check format.");
      }
    } catch (err: any) {
      console.error("Upload error:", err);
      const detail = err?.response?.data?.detail || "An internal error occurred during vector ingestion.";
      setError(detail);
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadFile(e.dataTransfer.files[0]);
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      uploadFile(e.target.files[0]);
    }
  };

  return (
    <div className="w-full space-y-4">
      {/* Drag & Drop zone */}
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        className={`relative flex min-h-[220px] w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed p-4 sm:p-6 text-center transition-all duration-200 ${
          dragActive
            ? "border-zinc-500 bg-zinc-800/10"
            : "border-slate-800 bg-slate-950/20 hover:border-slate-700/80 hover:bg-slate-900/10"
        }`}
      >
        <input
          type="file"
          id="pdf-file-upload"
          multiple={false}
          accept=".pdf,.png,.jpg,.jpeg,.webp,.tiff,.tif"
          onChange={handleChange}
          disabled={uploading}
          className="hidden"
        />

        <label
          htmlFor="pdf-file-upload"
          className="flex h-full w-full max-w-full min-w-0 flex-col items-center justify-center cursor-pointer p-2"
        >
          {uploading ? (
            <div className="flex flex-col items-center gap-3 w-full max-w-full min-w-0">
              <Loader2 className="h-10 w-10 animate-spin text-zinc-400" />
              <p className="text-sm font-bold text-zinc-700 dark:text-zinc-300 text-center break-words">Extracting and embedding document...</p>
              <p className="text-[10px] text-zinc-500 dark:text-slate-500 max-w-[200px] leading-relaxed text-center">
                Splitting into token chunks and indexing to Qdrant Cloud.
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 w-full max-w-full min-w-0">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-zinc-100 dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 text-zinc-500 dark:text-zinc-400 shrink-0">
                <UploadCloud className="h-6 w-6 text-zinc-500 dark:text-zinc-400 animate-bounce" />
              </div>
              <p className="text-xs font-bold text-zinc-700 dark:text-zinc-300 text-center break-words max-w-full">
                Drag and drop your document here, or <span className="text-zinc-600 dark:text-zinc-400 hover:underline">browse</span>
              </p>
              <p className="text-[10px] text-zinc-500 dark:text-slate-500 text-center">Supports PDF and common images up to 25MB</p>
            </div>
          )}
        </label>
      </div>

      {/* Notifications */}
      {error && (
        <div className="flex items-start gap-2.5 rounded-xl border border-red-500/20 bg-red-500/10 p-3.5 text-xs text-red-400 leading-normal">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" />
          <div>
            <span className="font-bold uppercase tracking-wider text-[9px] block mb-0.5 text-red-500">Ingestion Error</span>
            {error}
          </div>
        </div>
      )}

      {success && (
        <div className="flex items-start gap-2.5 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3.5 text-xs text-emerald-400 leading-normal">
          <CheckCircle className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" />
          <div>
            <span className="font-bold uppercase tracking-wider text-[9px] block mb-0.5 text-emerald-500">Ingestion Success</span>
            {success}
          </div>
        </div>
      )}
    </div>
  );
}
