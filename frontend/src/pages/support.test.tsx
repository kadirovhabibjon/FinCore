import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { setLang } from "../i18n";
import { USER, WALLET, fakeApi, json, noContent, problem, renderApp, signedInRoutes } from "../test/fakeApi";

const CUSTOMER_ID = "77777777-7777-4777-8777-777777777777";
const message = (id: string, sender: "CUSTOMER" | "STAFF", body: string) => ({
  id,
  sender,
  body,
  created_at: "2026-10-08T10:00:00Z",
});

/** A conversation the test's fake server keeps, as the real one would. */
function conversation(start: ReturnType<typeof message>[] = [], unread = 0) {
  const state = { items: [...start], unread, status: "OPEN" };
  return {
    state,
    routes: {
      "GET /api/v1/support/messages": () =>
        json({ status: state.status, unread_count: state.unread, items: state.items }),
      "POST /api/v1/support/messages": (request: { body?: unknown }) => {
        const sent = message(`m${state.items.length + 1}`, "CUSTOMER", (request.body as { body: string }).body);
        state.items.push(sent);
        return json(sent, 201);
      },
      "POST /api/v1/support/read": () => {
        state.unread = 0;
        return noContent();
      },
    },
  };
}

const customerPage = (extra: Parameters<typeof fakeApi>[0]) =>
  fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([WALLET]), ...extra });

describe("writing to an operator", () => {
  it("hands a question the assistant didn't settle over to a person", async () => {
    const chat = conversation();
    const { requests } = customerPage({
      ...chat.routes,
      "POST /api/v1/assistant/chat": () => json({ reply: "I can't help with that here." }),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: /Ask FinCore/ }));
    // Nothing asked yet: no need to offer a person.
    expect(screen.queryByRole("button", { name: "Write to an operator" })).toBeNull();
    await userEvent.type(screen.getByLabelText("Message"), "My refund never arrived");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("I can't help with that here.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Write to an operator" }));
    // The question came along; it is sent only when the customer says so.
    expect(screen.getByLabelText("Message")).toHaveValue("My refund never arrived");
    expect(screen.getByText(/A person reads it and answers in this chat/)).toBeInTheDocument();
    expect(requests.some((r) => r.method === "POST" && r.path === "/api/v1/support/messages")).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    const log = screen.getByRole("log", { name: "FinCore operator" });
    expect(await within(log).findByText("My refund never arrived")).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toHaveValue("");
    expect(
      requests.find((r) => r.method === "POST" && r.path === "/api/v1/support/messages")?.body,
    ).toEqual({ body: "My refund never arrived" });
  });

  it("offers a person when the assistant is unavailable", async () => {
    customerPage({
      ...conversation().routes,
      "POST /api/v1/assistant/chat": () => problem(503, "Assistant Unavailable"),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: /Ask FinCore/ }));
    await userEvent.type(screen.getByLabelText("Message"), "Hello?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    await userEvent.click(await screen.findByRole("button", { name: "Write to an operator" }));
    expect(screen.getByLabelText("Message")).toHaveValue("Hello?");
  });

  it("shows a reply on the launcher, opens on it and marks it read", async () => {
    const chat = conversation(
      [message("m1", "CUSTOMER", "Where is my money?"), message("m2", "STAFF", "It is on its way.")],
      1,
    );
    const { requests } = customerPage(chat.routes);
    renderApp("/");

    const launcher = await screen.findByRole("button", { name: /Ask FinCore/ });
    expect(await within(launcher).findByLabelText("1 new")).toBeInTheDocument();
    await userEvent.click(launcher);

    // Straight to the operator's side, where the news is.
    const log = await screen.findByRole("log", { name: "FinCore operator" });
    expect(within(log).getByText("It is on its way.")).toBeInTheDocument();
    expect(within(log).getByText("Operator")).toBeInTheDocument();
    await waitFor(() =>
      expect(requests.some((r) => r.path === "/api/v1/support/read")).toBe(true),
    );
  });

  it("opens from the bell's 'Support replied'", async () => {
    const chat = conversation([message("m2", "STAFF", "Please check now.")]);
    customerPage({
      ...chat.routes,
      "GET /api/v1/notifications": () =>
        json({
          unread_count: 1,
          items: [
            {
              id: "n1",
              type: "support.reply",
              title: "Support replied",
              body: "Please check now.",
              params: { preview: "Please check now." },
              created_at: "2026-10-08T10:00:00Z",
              read: false,
            },
          ],
        }),
      "POST /api/v1/notifications/read": () => noContent(),
    });
    setLang("uz");
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: /Bildirishnomalar/ }));
    // The title is translated; the operator's own words are not.
    await userEvent.click(await screen.findByRole("button", { name: "Operator javob berdi" }));

    const log = await screen.findByRole("log", { name: "FinCore operatori" });
    expect(within(log).getByText("Please check now.")).toBeInTheDocument();
  });

  it("says when too many messages were sent, and keeps the text", async () => {
    customerPage({
      ...conversation().routes,
      "POST /api/v1/support/messages": () => problem(429, "Too Many Messages"),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: /Ask FinCore/ }));
    await userEvent.click(screen.getByRole("button", { name: "Operator" }));
    await userEvent.type(screen.getByLabelText("Message"), "again");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/Too many messages. Please wait a few minutes/)).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toHaveValue("again");
  });
});

describe("the staff's support inbox", () => {
  const STAFF = { ...USER, roles: ["USER", "SUPPORT"] };
  const customer = {
    ...USER,
    id: CUSTOMER_ID,
    first_name: "Aziza",
    last_name: "Karimova",
    email: "aziza@example.com",
    phone: "+998901112244",
  };

  function staffPage() {
    const thread = {
      user_id: CUSTOMER_ID,
      status: "OPEN",
      last_message_at: "2026-10-08T10:00:00Z",
      last_sender: "CUSTOMER",
      last_body: "My transfer is stuck.",
      unread_count: 1,
    };
    const items = [message("m1", "CUSTOMER", "My transfer is stuck.")];
    const base = `/api/v1/admin/support/threads/${CUSTOMER_ID}`;
    return fakeApi({
      ...signedInRoutes(STAFF),
      [`GET /api/v1/admin/users/${CUSTOMER_ID}`]: () => json(customer),
      "GET /api/v1/admin/support/threads": () =>
        json({
          waiting_count: thread.last_sender === "CUSTOMER" && thread.status === "OPEN" ? 1 : 0,
          items: [thread],
        }),
      [`GET ${base}`]: () => json({ ...thread, items }),
      [`POST ${base}/read`]: () => {
        thread.unread_count = 0;
        return json(thread);
      },
      [`POST ${base}/messages`]: (request) => {
        const sent = message("m2", "STAFF", (request.body as { body: string }).body);
        items.push(sent);
        Object.assign(thread, { last_sender: "STAFF", last_body: sent.body });
        return json(sent, 201);
      },
      [`POST ${base}/resolve`]: () => json(Object.assign(thread, { status: "RESOLVED" })),
      [`POST ${base}/reopen`]: () => json(Object.assign(thread, { status: "OPEN" })),
    });
  }

  it("lists who is waiting, and lets staff read, answer and resolve", async () => {
    const { requests } = staffPage();
    renderApp("/admin/support");

    expect(await screen.findByText(/1 waiting for an answer/)).toBeInTheDocument();
    const inbox = screen.getByRole("list", { name: "Conversations" });
    await userEvent.click(await within(inbox).findByRole("button", { name: /Aziza Karimova/ }));

    const log = await screen.findByRole("log", { name: "Messages" });
    expect(within(log).getByText("My transfer is stuck.")).toBeInTheDocument();
    expect(await screen.findByText(/aziza@example.com · \+998901112244/)).toBeInTheDocument();
    // On screen is read.
    await waitFor(() => expect(requests.some((r) => r.path.endsWith("/read"))).toBe(true));

    await userEvent.type(screen.getByLabelText("Reply"), "  We are on it.  ");
    await userEvent.click(screen.getByRole("button", { name: "Send reply" }));
    expect(await within(log).findByText("We are on it.")).toBeInTheDocument();
    expect(requests.find((r) => r.path.endsWith("/messages") && r.method === "POST")?.body).toEqual({
      body: "We are on it.",
    });
    expect(screen.getByLabelText("Reply")).toHaveValue("");
    expect(await screen.findByText(/Nobody is waiting for an answer/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Mark resolved" }));
    expect(await screen.findByRole("button", { name: "Reopen" })).toBeInTheDocument();
  });

  it("is not for customers", async () => {
    fakeApi({ ...signedInRoutes(), "GET /api/v1/wallets": () => json([WALLET]) });
    renderApp("/admin/support");

    expect(await screen.findByRole("heading", { name: "No admin access" })).toBeInTheDocument();
  });
});
