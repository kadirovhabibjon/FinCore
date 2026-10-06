import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import * as api from "../api/endpoints";
import { useAuth } from "../auth/context";
import { ErrorAlert, Notice } from "./ui";
import { PasswordInput } from "./PasswordInput";

/** Phone numbers compare by their digits: "+998 90 123 45 67" typed with
 * spaces is still the number on the account. */
function samePhone(a: string, b: string): boolean {
  return a.replace(/\D/g, "") === b.replace(/\D/g, "");
}

/** Edits the signed-in customer's name, email address and phone number.
 * The email and phone are how the account is signed in to and
 * recovered, so changing either asks for the current password; the
 * field only appears once one of them differs. */
export function EditProfileForm({ user }: { user: api.CurrentUser }) {
  const { refreshUser } = useAuth();
  const [firstName, setFirstName] = useState(user.first_name);
  const [lastName, setLastName] = useState(user.last_name);
  const [email, setEmail] = useState(user.email);
  const [phone, setPhone] = useState(user.phone);
  const [password, setPassword] = useState("");

  const contactChanged =
    email.trim().toLowerCase() !== user.email.toLowerCase() || !samePhone(phone, user.phone);
  const changed =
    contactChanged || firstName.trim() !== user.first_name || lastName.trim() !== user.last_name;

  const save = useMutation({
    mutationFn: () =>
      api.updateProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        phone: phone.trim(),
        current_password: contactChanged ? password : null,
      }),
    onSuccess: async (saved) => {
      // Show what the server stored (a phone number comes back normalized).
      setFirstName(saved.first_name);
      setLastName(saved.last_name);
      setEmail(saved.email);
      setPhone(saved.phone);
      setPassword("");
      await refreshUser();
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (changed) save.mutate();
  }

  function edited(setter: (value: string) => void) {
    return (value: string) => {
      setter(value);
      if (save.isSuccess || save.isError) save.reset();
    };
  }

  return (
    <form className="card form" onSubmit={onSubmit}>
      {save.isSuccess && <Notice>Your details have been saved.</Notice>}
      <ErrorAlert error={save.error} />
      <div className="row">
        <label>
          First name
          <input
            value={firstName}
            onChange={(e) => edited(setFirstName)(e.target.value)}
            autoComplete="given-name"
            required
            maxLength={100}
          />
        </label>
        <label>
          Last name
          <input
            value={lastName}
            onChange={(e) => edited(setLastName)(e.target.value)}
            autoComplete="family-name"
            required
            maxLength={100}
          />
        </label>
      </div>
      <div className="row">
        <label>
          Email
          <input
            value={email}
            onChange={(e) => edited(setEmail)(e.target.value)}
            type="email"
            autoComplete="email"
            required
          />
        </label>
        <label>
          Phone number
          <input
            value={phone}
            onChange={(e) => edited(setPhone)(e.target.value)}
            type="tel"
            autoComplete="tel"
            required
            maxLength={32}
          />
        </label>
      </div>
      {contactChanged && (
        <div className="field">
          <label>
            Current password
            <PasswordInput
              value={password}
              onChange={(e) => edited(setPassword)(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <span className="muted small">
            Needed to change your email or phone number: you sign in with them, and password reset
            codes go to the email.
          </span>
        </div>
      )}
      <div className="actions">
        <button type="submit" className="button" disabled={!changed || save.isPending}>
          {save.isPending ? "Saving…" : "Save changes"}
        </button>
      </div>
    </form>
  );
}
