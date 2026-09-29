import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import { RedirectIfAuthenticated, RequireAuth, RequireRole } from "./auth/guards";
import { Layout } from "./components/Layout";
import { AdminReviewsPage } from "./pages/admin/AdminReviewsPage";
import { AdminTransactionsPage } from "./pages/admin/AdminTransactionsPage";
import { AdminUsersPage } from "./pages/admin/AdminUsersPage";
import { AdminWebhooksPage } from "./pages/admin/AdminWebhooksPage";
import { LoginPage } from "./pages/LoginPage";
import { MerchantPage } from "./pages/MerchantPage";
import { MerchantsPage } from "./pages/MerchantsPage";
import { PayPage } from "./pages/PayPage";
import { RegisterPage } from "./pages/RegisterPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TransactionPage } from "./pages/TransactionPage";
import { TransactionsPage } from "./pages/TransactionsPage";
import { TransferPage } from "./pages/TransferPage";
import { WalletPage } from "./pages/WalletPage";
import { WalletsPage } from "./pages/WalletsPage";
import { createQueryClient } from "./queryClient";

function NotFound() {
  return (
    <section className="page">
      <h1>Page not found</h1>
      <Link to="/">Back to your wallets</Link>
    </section>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<RedirectIfAuthenticated />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route index element={<WalletsPage />} />
          <Route path="wallets/:walletId" element={<WalletPage />} />
          <Route path="transfer" element={<TransferPage />} />
          <Route path="pay" element={<PayPage />} />
          <Route path="transactions" element={<TransactionsPage />} />
          <Route path="transactions/:transactionId" element={<TransactionPage />} />
          <Route path="merchants" element={<MerchantsPage />} />
          <Route path="merchants/:merchantId" element={<MerchantPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="admin" element={<RequireRole roles={["SUPPORT", "ADMIN"]} />}>
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="reviews" element={<AdminReviewsPage />} />
            <Route path="transactions" element={<AdminTransactionsPage />} />
            <Route path="webhooks" element={<AdminWebhooksPage />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}

export function App() {
  const [queryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
