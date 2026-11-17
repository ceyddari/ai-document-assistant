import { useEffect, useRef, useState } from "react";
import type { Source } from "../types";
import { Icon } from "./Icon";

export type SourceFocus = { index: number; nonce: number };

type Props = {
  sources: Source[];
  /** Set when a citation badge is clicked; the nonce lets the same badge re-trigger. */
  focus: SourceFocus | null;
  onOpenPdf: (source: Source) => void;
};

export function SourceList({ sources, focus, onOpenPdf }: Props) {
  const [openIndexes, setOpenIndexes] = useState<ReadonlySet<number>>(() => new Set());
  const [flashIndex, setFlashIndex] = useState<number | null>(null);
  const items = useRef<(HTMLDetailsElement | null)[]>([]);

  useEffect(() => {
    if (!focus) return;
    setOpenIndexes(current => new Set(current).add(focus.index));
    setFlashIndex(focus.index);
    const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    items.current[focus.index]?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
    const timer = window.setTimeout(() => setFlashIndex(null), 1600);
    return () => window.clearTimeout(timer);
  }, [focus]);

  if (!sources.length) return null;
  return <div className="sources">
    <p className="sources-label">Kaynaklar</p>
    {sources.map((source, index) => <details
      className={`source${flashIndex === index ? " flash" : ""}`}
      key={source.chunk_id}
      ref={element => { items.current[index] = element; }}
      open={openIndexes.has(index)}
      // Keeps state in sync when the user opens or closes it by hand.
      onToggle={event => {
        const isOpen = event.currentTarget.open;
        setOpenIndexes(current => {
          if (current.has(index) === isOpen) return current;
          const next = new Set(current);
          if (isOpen) next.add(index); else next.delete(index);
          return next;
        });
      }}
    >
      <summary>
        <span className="cite">{index + 1}</span>
        <span className="source-name" title={source.filename}>{source.filename}</span>
        <span className="source-page">s. {source.page_number}</span>
        <span className="source-score" title="Benzerlik">%{Math.round(source.similarity * 100)}</span>
      </summary>
      <blockquote>{source.content}</blockquote>
      <div className="source-actions">
        <button type="button" className="source-open" onClick={() => onOpenPdf(source)}>
          <Icon name="external" />PDF'te aç · s. {source.page_number}
        </button>
      </div>
    </details>)}
  </div>;
}
