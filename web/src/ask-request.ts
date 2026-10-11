// The JSON body of a question. `focus` rides beside the plain question text
// when the visitor asked from something they clicked; the visible transcript
// holds only the question.
import type { AskFocus } from "./types";

// What a card calls to ask Deadbot something; `focus` says what was clicked.
export type FollowUp = (question: string, focus?: AskFocus) => void;

export function askRequestBody({
  question,
  threadId,
  conversation,
  focus,
}: {
  question: string;
  threadId: string;
  conversation: { role: "user" | "assistant"; text: string }[];
  focus?: AskFocus;
}): string {
  return JSON.stringify({ question, thread_id: threadId, conversation, ...(focus ? { focus } : {}) });
}
