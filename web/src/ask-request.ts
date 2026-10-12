// The JSON body of a question. `focus` rides beside the plain question text
// when the visitor asked from something they clicked; the visible transcript
// holds only the question. `notebook` is the signed research token the last
// answer returned; it rides back unchanged and is omitted when there is none.
import type { AskFocus } from "./types";

// What a card calls to ask Deadbot something; `focus` says what was clicked.
export type FollowUp = (question: string, focus?: AskFocus) => void;

export function askRequestBody({
  question,
  threadId,
  conversation,
  focus,
  notebook,
}: {
  question: string;
  threadId: string;
  conversation: { role: "user" | "assistant"; text: string }[];
  focus?: AskFocus;
  notebook?: string | null;
}): string {
  return JSON.stringify({ question, thread_id: threadId, conversation, ...(focus ? { focus } : {}), ...(notebook ? { notebook } : {}) });
}
