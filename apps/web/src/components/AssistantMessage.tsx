import { useCallback, useState } from "react";
import type { Feedback, Message, Source } from "../types";
import { Icon } from "./Icon";
import { MessageContent } from "./MessageContent";
import { type SourceFocus, SourceList } from "./SourceList";

type Props = {
  message: Message;
  /** True while the answer is still arriving: citations are not final, so no clicks or votes. */
  streaming?: boolean;
  onOpenPdf: (source: Source) => void;
  onFeedback?: (message: Message, value: Feedback) => void;
};

export function AssistantMessage({ message, streaming = false, onOpenPdf, onFeedback }: Props) {
  const [focus, setFocus] = useState<SourceFocus | null>(null);
  const cite = useCallback((number: number) => setFocus({ index: number - 1, nonce: Date.now() }), []);
  const vote = message.feedback ?? null;

  return <>
    <MessageContent content={message.content} sourceCount={message.sources.length} onCite={streaming ? undefined : cite} />
    {streaming && <span className="stream-caret" aria-hidden="true" />}
    <SourceList sources={message.sources} focus={focus} onOpenPdf={onOpenPdf} />
    {!streaming && onFeedback && <div className="feedback" role="group" aria-label="Cevabı değerlendirin">
      <button type="button" className={`feedback-button${vote === 1 ? " active" : ""}`} aria-pressed={vote === 1} title="Faydalı" aria-label="Faydalı" onClick={() => onFeedback(message, vote === 1 ? null : 1)}><Icon name="thumbUp" /></button>
      <button type="button" className={`feedback-button${vote === -1 ? " active" : ""}`} aria-pressed={vote === -1} title="Faydalı değil" aria-label="Faydalı değil" onClick={() => onFeedback(message, vote === -1 ? null : -1)}><Icon name="thumbDown" /></button>
    </div>}
  </>;
}
