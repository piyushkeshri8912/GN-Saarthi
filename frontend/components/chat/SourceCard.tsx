import { useState } from "react";
import { FileText, ChevronDown, ChevronUp } from "lucide-react";
import { SourceChunk } from "../../types";

export default function SourceCard({ source }: { source: SourceChunk }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/20 transition-all duration-200 hover:border-zinc-300 dark:hover:border-zinc-700 hover:shadow-sm dark:hover:shadow-zinc-950/20">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between p-2.5 text-left text-xs font-semibold text-zinc-700 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-white cursor-pointer"
      >
        <div className="flex items-center gap-2 truncate">
          <FileText className="h-3.5 w-3.5 shrink-0 text-zinc-500 dark:text-zinc-400" />
          <span className="truncate max-w-[150px] sm:max-w-[220px]" title={source.source}>
            {source.source}
          </span>
          <span className="shrink-0 rounded bg-zinc-200 dark:bg-zinc-950/80 px-1.5 py-0.5 text-[9px] font-bold text-zinc-600 dark:text-zinc-300 border border-zinc-300 dark:border-zinc-800/40">
            Page {source.page}
          </span>
        </div>
        {isOpen ? (
          <ChevronUp className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
        )}
      </button>

      {isOpen && (
        <div className="border-t border-zinc-200 dark:border-zinc-800 bg-zinc-100/50 dark:bg-zinc-950/40 p-2.5 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap selection:bg-zinc-200 dark:selection:bg-zinc-700/30 max-h-[160px] overflow-y-auto">
          {source.text_content}
        </div>
      )}
    </div>
  );
}
