import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { DateTime, Empty, ErrorAlert, Loading, StatusBadge } from "../components/ui";

export function MerchantsPage() {
  const queryClient = useQueryClient();
  const merchants = useQuery({ queryKey: ["merchants"], queryFn: api.listMerchants });
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: api.createMerchant,
    onSuccess: () => {
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["merchants"] });
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate(name.trim());
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Merchants</h1>
          <p className="muted">Accept payments, issue refunds and receive webhooks.</p>
        </div>
        <form className="inline-form" onSubmit={onSubmit}>
          <input
            aria-label="Merchant name"
            placeholder="Shop name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={255}
          />
          <button type="submit" className="button" disabled={create.isPending}>
            Create merchant
          </button>
        </form>
      </header>
      <ErrorAlert error={create.error ?? merchants.error} />
      {merchants.isPending ? (
        <Loading what="Loading merchants" />
      ) : merchants.data?.length === 0 ? (
        <Empty>You don&apos;t own any merchants yet.</Empty>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {merchants.data?.map((merchant) => (
              <tr key={merchant.id}>
                <td>
                  <Link to={`/merchants/${merchant.id}`}>{merchant.name}</Link>
                </td>
                <td>
                  <StatusBadge status={merchant.status} />
                </td>
                <td>
                  <DateTime value={merchant.created_at} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
