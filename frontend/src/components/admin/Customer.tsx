import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import * as api from "../../api/endpoints";

/** Other services know a customer only by id; identity-service knows
 * who that is. Asked once per customer and kept for a while, so a table
 * full of the same person costs one request. */
function useCustomer(userId: string) {
  return useQuery({
    queryKey: ["admin", "user", userId],
    queryFn: () => api.adminGetUser(userId),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/** A customer's name, or the start of their id while it is unknown. */
export function CustomerName({ userId }: { userId: string }) {
  const user = useCustomer(userId);
  if (!user.data) {
    return (
      <code className="short-id" title={userId}>
        {userId.slice(0, 8)}
      </code>
    );
  }
  return (
    <>
      {user.data.first_name} {user.data.last_name}
    </>
  );
}

/** The name as a link to that customer on the Users page. */
export function CustomerLink({ userId }: { userId: string }) {
  return (
    <Link to={`/admin/users?q=${userId}`} title={userId}>
      <CustomerName userId={userId} />
    </Link>
  );
}

/** How to reach the customer: email and phone. */
export function CustomerContact({ userId }: { userId: string }) {
  const user = useCustomer(userId);
  if (!user.data) return null;
  return (
    <>
      {user.data.email} · {user.data.phone}
    </>
  );
}
