import { expect, it } from "vitest";

import type { ChatMessage } from "../api/endpoints";
import { conversationToSend } from "./chat";

const turns = (count: number): ChatMessage[] =>
  Array.from({ length: count }, (_, i) => ({
    role: i % 2 === 0 ? "user" : "assistant",
    content: `m${i}`,
  }));

it("sends a short conversation as is", () => {
  expect(conversationToSend(turns(3))).toEqual(turns(3));
});

it("keeps at most 20 messages, always starting with the customer", () => {
  const sent = conversationToSend(turns(25));
  expect(sent.length).toBeLessThanOrEqual(20);
  expect(sent[0]?.role).toBe("user");
  expect(sent.at(-1)?.content).toBe("m24");
});
